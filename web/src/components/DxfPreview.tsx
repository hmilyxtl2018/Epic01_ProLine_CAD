"use client";

// Real DXF preview powered by `dxf-viewer` (MIT, Three.js based).
// We isolate it in its own component because:
//   - it must NEVER run on the server (`window` / `document` accesses)
//   - dynamic import keeps Three.js out of the main route bundle
//   - exposes a tiny `src` prop API so the page just feeds it a URL

import { useEffect, useRef, useState } from "react";

export interface DxfPreviewProps {
  /** URL the browser will fetch with credentials. Server should respond with the raw DXF. */
  src: string;
  className?: string;
  /** Background color of the canvas. Default: #ffffff. */
  background?: string;
  /** Called when DXF can't be fetched/rendered (404, parse error, etc.). */
  onError?: (msg: string) => void;
  /** Called once the DXF is rendered. */
  onReady?: () => void;
}

export function DxfPreview({ src, className, background = "#ffffff", onError, onReady }: DxfPreviewProps) {  const hostRef = useRef<HTMLDivElement | null>(null);
  const viewerRef = useRef<any>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  // dxf-viewer's progressCbk(phase, processed, total) reports 4 phases:
  // "font" | "fetch" | "parse" | "prepare". We surface them as a single bar.
  const [phase, setPhase] = useState<string>("");
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [hint, setHint] = useState<string>("");

  useEffect(() => {
    let disposed = false;
    let viewer: any = null;
    const host = hostRef.current;
    if (!host) return;

    setStatus("loading");
    setError(null);
    setPhase("init");
    setProgress(null);
    setHint("");

    const progressCbk = (ph: string, processed: number, total: number) => {
      if (disposed) return;
      setPhase(ph);
      setProgress({ done: processed || 0, total: total || 0 });
    };

    // Resolve fonts via JSDelivr (dxf-viewer ships none by default; missing
    // fonts are rendered as filled boxes). Used by both initial Load and the
    // blob-URL fallback below.
    const FONTS = [
      "https://cdn.jsdelivr.net/npm/dxf-viewer@1.0.47/dist/fonts/Roboto-LightItalic.ttf",
      "https://cdn.jsdelivr.net/npm/dxf-viewer@1.0.47/dist/fonts/NotoSansDisplay-SemiCondensedLightItalic.ttf",
      "https://cdn.jsdelivr.net/npm/dxf-viewer@1.0.47/dist/fonts/HanaMinA.ttf",
      "https://cdn.jsdelivr.net/npm/dxf-viewer@1.0.47/dist/fonts/NanumGothic-Regular.ttf",
    ];

    (async () => {
      const log = (...a: any[]) => console.log("[DxfPreview]", ...a);
      const wireEvents = (v: any) => {
        try {
          v.Subscribe?.("message", (d: any) => {
            log("message:", d?.message, d?.level);
            if (d?.level === "warn" || d?.level === "error") {
              setHint(`${d.level}: ${d.message}`);
            }
          });
          v.Subscribe?.("loaded", () => {
            const b = v.GetBounds?.();
            const cs = v.GetCanvasSize?.();
            log("loaded; bounds=", b, "canvasSize=", cs, "host=", host?.getBoundingClientRect?.());
            setHint(b ? `bounds ${fmtNum(b.minX)},${fmtNum(b.minY)} → ${fmtNum(b.maxX)},${fmtNum(b.maxY)}` : "(empty bounds)");
          });
        } catch (err) {
          log("Subscribe failed", err);
        }
      };

      // Always pre-fetch as Blob so we control auth headers (the dev backend
      // accepts cookie OR X-Role/X-Actor; React Query's api.ts uses the
      // header path, so we mirror it here — otherwise this endpoint 401s
      // even though the rest of the dashboard works).
      const getRoleSafe = () => {
        try {
          const v = window.localStorage.getItem("proline.role");
          return v && /^(viewer|operator|reviewer|admin)$/.test(v) ? v : "viewer";
        } catch { return "viewer"; }
      };
      const getActorSafe = () => {
        try { return window.localStorage.getItem("proline.actor") || "anonymous@dev"; }
        catch { return "anonymous@dev"; }
      };

      try {
        const r = await fetch(src, {
          credentials: "include",
          headers: { "X-Role": getRoleSafe(), "X-Actor": getActorSafe() },
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const blob = await r.blob();
        const blobUrl = URL.createObjectURL(blob);

        const mod = await import("dxf-viewer");
        if (disposed) { URL.revokeObjectURL(blobUrl); return; }
        const { DxfViewer } = mod as any;

        log("host size at construct:", host.getBoundingClientRect(), "blob:", blob.size, "B");

        viewer = new DxfViewer(host, {
          clearColor: new (await import("three")).Color(background),
          autoResize: true,
          colorCorrection: true,
        });
        viewerRef.current = viewer;
        wireEvents(viewer);

        await viewer.Load({ url: blobUrl, fonts: FONTS, progressCbk });
        URL.revokeObjectURL(blobUrl);
        if (disposed) return;
        // Load() already calls FitView + Render internally. Re-fit after a tick
        // so the ResizeObserver has had a chance to set the real canvas size.
        setTimeout(() => { try { viewer?.FitView?.(); viewer?.Render?.(); } catch {} }, 50);
        setStatus("ready");
        onReady?.();
      } catch (e: any) {
        if (disposed) return;
        const msg = e?.message || "DXF load failed";
        console.error("[DxfPreview] failed:", e);
        setStatus("error");
        setError(msg);
        onError?.(msg);
      }
    })();

    return () => {
      disposed = true;
      try {
        viewerRef.current?.Destroy?.();
      } catch {
        /* noop */
      }
      viewerRef.current = null;
    };
  }, [src, background]);

  const pct = progress && progress.total > 0
    ? Math.min(100, Math.round((progress.done / progress.total) * 100))
    : phase === "init"
      ? 2
      : 0;

  return (
    <div className={"relative " + (className || "")}>
      <div ref={hostRef} className="absolute inset-0" />
      {status === "loading" && (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-2 bg-white/70">
          <div className="text-[12px] text-zinc-700">
            渲染 DXF 中… <span className="font-mono text-zinc-500">[{phaseLabel(phase)}]</span>
          </div>
          <div className="h-2 w-56 overflow-hidden rounded-full bg-zinc-200">
            <div
              className="h-full bg-blue-500 transition-[width] duration-150 ease-out"
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="font-mono text-[11px] text-zinc-500">
            {progress && progress.total > 0
              ? `${formatBytes(progress.done)} / ${formatBytes(progress.total)} (${pct}%)`
              : progress
                ? `${formatBytes(progress.done)}`
                : "准备中…"}
          </div>
        </div>
      )}
      {status === "error" && (
        <div className="absolute inset-0 flex items-center justify-center p-4">
          <div className="max-w-sm rounded border border-red-200 bg-red-50 p-3 text-[12px] text-red-700">
            <div className="font-semibold">DXF 渲染失败</div>
            <div className="mt-1 break-words font-mono text-[11px]">{error}</div>
          </div>
        </div>
      )}
      {hint && status !== "error" && (
        <div className="pointer-events-none absolute bottom-1 left-1 max-w-[60%] truncate rounded bg-black/60 px-1.5 py-0.5 font-mono text-[10px] text-white">
          {hint}
        </div>
      )}
    </div>
  );
}

export default DxfPreview;

function phaseLabel(phase: string): string {
  switch (phase) {
    case "font":
      return "加载字体";
    case "fetch":
      return "下载 DXF";
    case "parse":
      return "解析图元";
    case "prepare":
      return "构建场景";
    case "init":
      return "初始化";
    default:
      return phase || "…";
  }
}

function formatBytes(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${units[i]}`;
}

function fmtNum(n: number | undefined | null): string {
  if (n === undefined || n === null || !Number.isFinite(n)) return "?";
  const a = Math.abs(n);
  if (a >= 1000) return n.toFixed(0);
  if (a >= 1) return n.toFixed(2);
  return n.toFixed(4);
}
