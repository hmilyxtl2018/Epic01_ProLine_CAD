"use client";

import { useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { LLMEnrichment, RunDetail } from "@/lib/types";
import { Icon, type IconName } from "@/components/icons";
import { StatusBadge } from "@/components/StatusBadge";
import { ConstraintsPanel } from "@/components/constraints/ConstraintsPanel";

// ── Top workflow tabs ────────────────────────────────────────────────
const STAGES: { key: string; label: string; icon: IconName; enabled: boolean; desc: string }[] = [
  { key: "S1", label: "S1 图纸解析", icon: "file-text", enabled: true, desc: "CAD → SiteModel + LLM 富化" },
  { key: "S2", label: "S2 工艺约束", icon: "list-todo", enabled: true, desc: "施工工序、资源、时序约束建模" },
  { key: "S3", label: "S3 布局优化", icon: "workflow", enabled: true, desc: "设备与动线的多目标优化求解" },
  { key: "S4", label: "S4 仿真验证", icon: "play", enabled: true, desc: "离散事件仿真 · 指标回归" },
  { key: "S5", label: "S5 决策工作台", icon: "clipboard-check", enabled: true, desc: "方案对比 · 审批 · 交付" },
];

export default function SiteWorkspacePage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId;
  const [activeStage, setActiveStage] = useState("S1");
  // Selection: cluster_id from left tree → right panel; null = auto-pick first.
  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(null);

  const q = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.getRun(runId),
    enabled: !!runId,
  });

  if (q.isLoading) return <FullBleedMsg>加载工作台中…</FullBleedMsg>;
  if (q.isError || !q.data) return <FullBleedMsg error>加载失败：{String((q.error as any)?.message || "unknown")}</FullBleedMsg>;

  const run = q.data;

  return (
    <div className="flex h-[calc(100vh-65px)] flex-col bg-zinc-50">
      {/* Top stage tabs */}
      <nav className="flex items-center gap-1 border-b border-zinc-200 bg-white px-4">
        {STAGES.map((s) => {
          const active = s.key === activeStage;
          return (
            <button
              key={s.key}
              disabled={!s.enabled}
              onClick={() => s.enabled && setActiveStage(s.key)}
              className={[
                "inline-flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-[13px] transition",
                active
                  ? "border-violet-600 font-medium text-violet-700"
                  : s.enabled
                    ? "border-transparent text-zinc-600 hover:text-zinc-900"
                    : "cursor-not-allowed border-transparent text-zinc-300",
              ].join(" ")}
            >
              <Icon name={s.icon} size={14} />
              {s.label}
            </button>
          );
        })}
        <div className="ml-auto flex items-center gap-2 text-[11px] text-zinc-400">
          <Link href="/sites" className="hover:text-zinc-700">
            ← 返回 Sites
          </Link>
          <span>·</span>
          <Link href={`/runs/${runId}`} className="hover:text-zinc-700">
            技术视图
          </Link>
        </div>
      </nav>

      {/* Site header strip */}
      <SiteHeader run={run} />

      {/* Stage body */}
      {activeStage === "S1" ? (
        <div className="grid min-h-0 flex-1 grid-cols-[260px_1fr_320px] grid-rows-[1fr] gap-3 overflow-hidden p-3">
          <LeftSidebar run={run} selected={selectedClusterId} onSelect={setSelectedClusterId} />
          <CenterCanvas run={run} selected={selectedClusterId} onSelect={setSelectedClusterId} />
          <RightPanel run={run} selected={selectedClusterId} />
        </div>
      ) : activeStage === "S2" ? (
        run.site_model_id ? (
          <ConstraintsPanel siteModelId={run.site_model_id} />
        ) : (
          <div className="flex flex-1 items-center justify-center p-8 text-[12px] text-zinc-400">
            该 Run 尚未生成 site_model_id，无法编辑工艺约束。
          </div>
        )
      ) : (
        <StageComingSoon stage={STAGES.find((s) => s.key === activeStage)!} />
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Site header: ontology badge + sm_id + version + title + file hash
// ──────────────────────────────────────────────────────────────────────
function SiteHeader({ run }: { run: RunDetail }) {
  const enrich = getEnrichment(run);
  const title = enrich?.sections.J_site_describe?.title || "(未命名站点)";
  const smId = run.site_model_id || "—";
  const source = run.site_model_cad_source as any;
  const filename: string = source?.filename || (run.input_payload as any)?.filename || "未知文件";
  const sha: string = source?.fingerprint?.sha256 || "";
  const tags = enrich?.sections.J_site_describe?.suggested_tags || [];

  return (
    <div className="flex items-center gap-3 border-b border-zinc-200 bg-white px-4 py-2 text-[12px]">
      <span className="inline-flex items-center gap-1 rounded bg-violet-100 px-2 py-0.5 font-medium text-violet-700">
        <Icon name="database" size={12} /> ONT
      </span>
      <span className="font-medium text-zinc-900">SiteModel</span>
      <span className="font-mono text-[11px] text-zinc-500">{smId}</span>
      <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">DRAFT</span>
      <span className="text-zinc-400">v1.0.0</span>
      <span className="text-zinc-300">|</span>
      <span className="truncate font-medium text-zinc-800">{title}</span>
      {tags.slice(0, 3).map((t: string) => (
        <span key={t} className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-600">
          #{t}
        </span>
      ))}
      <span className="ml-auto flex items-center gap-2 text-[11px] text-zinc-500">
        <StatusBadge status={run.status} />
        <Icon name="file-text" size={12} />
        <span>{filename}</span>
        {sha && (
          <span className="font-mono text-[10px] text-zinc-400" title={sha}>
            {sha.slice(0, 8)}…
          </span>
        )}
      </span>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Left sidebar: file · layer tree · CP-A prerequisites · ontology stats
// ──────────────────────────────────────────────────────────────────────
function LeftSidebar({
  run,
  selected,
  onSelect,
}: {
  run: RunDetail;
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const enrich = getEnrichment(run);
  const A = enrich?.sections.A_normalize?.items || [];
  const C = enrich?.sections.C_arbiter;
  const D = enrich?.sections.D_cluster_proposals;
  const I = enrich?.sections.I_self_check;
  const stats = run.site_model_statistics as any;

  // Recognized = arbiter "promote"; review queue = not recognized yet.
  const recognized = C?.promotion_candidates || [];
  const unknownClusters = D?.proposals || [];

  return (
    <aside className="flex flex-col gap-3 overflow-y-auto">
      <Panel title="文件" icon="file-text">
        <div className="flex items-center gap-2 rounded bg-zinc-50 px-2 py-1.5 text-[12px]">
          <Icon name="file-text" size={14} className="text-zinc-400" />
          <span className="truncate">
            {(run.site_model_cad_source as any)?.filename ||
              (run.input_payload as any)?.filename ||
              "main.dwg"}
          </span>
        </div>
      </Panel>

      <Panel
        title="图层树"
        icon="layers"
        right={
          <span className="text-[10px] text-zinc-400">
            {recognized.length}识别 · {unknownClusters.length}待审
          </span>
        }
      >
        <TreeGroup label="已识别" count={recognized.length} tone="ok">
          {recognized.slice(0, 6).map((p: any, i: number) => (
            <TreeLeaf
              key={i}
              icon="check"
              tone="ok"
              label={p.candidate || p.best_match || `term_${i}`}
              meta={typeof p.best_sim === "number" ? p.best_sim.toFixed(2) : undefined}
            />
          ))}
          {recognized.length === 0 && <EmptyRow>暂无</EmptyRow>}
        </TreeGroup>
        <TreeGroup label="待人工确认" count={unknownClusters.length} tone="warn">
          {unknownClusters.slice(0, 8).map((p: any, i: number) => {
            const id = p.cluster_id || `cluster_${i}`;
            const isSel = selected === id || (selected === null && i === 0);
            return (
              <TreeLeaf
                key={id}
                icon="alert-triangle"
                tone="warn"
                label={p.suggested_term || p.asset_type_hint || id}
                meta={p.member_count != null ? `×${p.member_count}` : undefined}
                active={isSel}
                onClick={() => onSelect(id)}
              />
            );
          })}
          {unknownClusters.length === 0 && <EmptyRow>无待审</EmptyRow>}
        </TreeGroup>
      </Panel>

      <Panel title="CP-A 前置条件" icon="shield-check">
        <CheckRow ok={!I?.should_block} label="结构完整性通过" />
        <CheckRow ok={(A.length || 0) > 0} label={`术语归一化 ${A.length} 项`} />
        <CheckRow
          ok={(C?.counts?.promote || 0) > 0}
          label={`仲裁通过 ${C?.counts?.promote || 0} 条`}
        />
        {I?.blockers?.slice(0, 2).map((b: string, i: number) => (
          <div key={i} className="mt-1 flex items-start gap-1.5 rounded bg-red-50 px-2 py-1 text-[11px] text-red-700">
            <Icon name="alert-circle" size={12} className="mt-0.5 shrink-0" />
            <span>{b}</span>
          </div>
        ))}
      </Panel>

      <Panel title="ONTOLOGY 统计" icon="bar-chart">
        <StatRow label="资产数" value={run.site_model_assets_count} />
        <StatRow label="图层 (estimate)" value={stats?.layer_count ?? "—"} />
        <StatRow label="几何完整性" value={fmtPct(run.geometry_integrity_score)} />
        <StatRow label="LLM 步骤" value={enrich?.steps_run.length ?? "—"} />
      </Panel>
    </aside>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Center canvas — sub-tabs: 原始文件 (raw metadata) | AI 解析 (cluster map)
// ──────────────────────────────────────────────────────────────────────
function CenterCanvas({
  run,
  selected,
  onSelect,
}: {
  run: RunDetail;
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const [tab, setTab] = useState<"viewer" | "raw" | "parsed">("parsed");
  const enrich = getEnrichment(run);

  return (
    <main className="flex min-h-0 min-w-0 flex-col gap-2 overflow-hidden">
      {/* Sub-tabs */}
      <div className="flex items-center gap-1 rounded border border-zinc-200 bg-white px-1 py-1">
        <SubTab active={tab === "viewer"} onClick={() => setTab("viewer")} icon="layers" label="原始文件预览" />
        <SubTab active={tab === "raw"} onClick={() => setTab("raw")} icon="file-text" label="原始文件解析" />
        <SubTab active={tab === "parsed"} onClick={() => setTab("parsed")} icon="sparkles" label="AI 解析" />
        <span className="ml-2 text-[11px] text-zinc-400">
          沿管线左→右：原图 → 解析元数据 → LLM 洞察
        </span>
        <span className="ml-auto text-[11px] text-zinc-400">
          LLM pipeline · {enrich?.steps_run.length ?? 0}/13
        </span>
      </div>

      {tab === "viewer" && <ViewerView run={run} />}
      {tab === "raw" && <RawView run={run} />}
      {tab === "parsed" && <ParsedView run={run} selected={selected} onSelect={onSelect} />}
    </main>
  );
}

function SubTab({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: IconName;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={[
        "inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-[12px] transition",
        active
          ? "bg-violet-600 font-medium text-white"
          : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900",
      ].join(" ")}
    >
      <Icon name={icon} size={13} />
      {label}
    </button>
  );
}

// ── Viewer view: real DXF render via dxf-viewer, schematic as fallback
function ViewerView({ run }: { run: RunDetail }) {
  const stats = (run.site_model_statistics as any) || {};
  const cad = (run.site_model_cad_source as any) || {};
  const bbox = stats.bounding_box;
  const entityCounts: Record<string, number> = stats.entity_counts || {};
  const filename = cad.filename || (run.input_payload as any)?.filename || "未知文件";
  const previewUrl: string | null =
    cad.preview_url || cad.svg_preview_url || cad.png_preview_url || null;

  // Real-CAD path: backend persists a converted DXF for DWG inputs and
  // streams either it or the original DXF via /dashboard/runs/{id}/cad.
  const cadAvailable: boolean = Boolean(
    cad.converted_dxf_path ||
      String(cad.format || "").toLowerCase() === "dxf" ||
      String((run.input_payload as any)?.filename || "").toLowerCase().endsWith(".dxf") ||
      String((run.input_payload as any)?.filename || "").toLowerCase().endsWith(".dwg"),
  );
  const dxfUrl = `/api/dashboard/runs/${run.mcp_context_id}/cad`;
  // Renderer: MLightCAD (Vue 3 + WebAssembly) embedded as an iframe via
  // /mlight-viewer.html. We previously A/B'd against `dxf-viewer` (Three.js)
  // but it rendered blank on this dataset (#FFFFFF entities + colorCorrection
  // edge cases) and zoom-extents was unusable on outlier bboxes. MLightCAD
  // handles both cleanly, so we standardize on it.
  const cadReady = cadAvailable && !previewUrl;
  const useRealCad = cadReady;

  // Hand-rolled pan/zoom for the schematic viewport.
  const [view, setView] = useState({ tx: 0, ty: 0, k: 1 });
  const svgRef = useRef<SVGSVGElement | null>(null);
  const drag = useRef<{ sx: number; sy: number; stx: number; sty: number } | null>(null);
  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const r = svgRef.current?.getBoundingClientRect();
    if (!r) return;
    const mx = e.clientX - r.left;
    const my = e.clientY - r.top;
    const f = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    const nk = Math.max(0.2, Math.min(8, view.k * f));
    setView({
      tx: mx - (mx - view.tx) * (nk / view.k),
      ty: my - (my - view.ty) * (nk / view.k),
      k: nk,
    });
  };
  const onDown = (e: React.MouseEvent) => {
    drag.current = { sx: e.clientX, sy: e.clientY, stx: view.tx, sty: view.ty };
  };
  const onMove = (e: React.MouseEvent) => {
    if (!drag.current) return;
    setView((v) => ({
      ...v,
      tx: drag.current!.stx + (e.clientX - drag.current!.sx),
      ty: drag.current!.sty + (e.clientY - drag.current!.sy),
    }));
  };
  const reset = () => setView({ tx: 0, ty: 0, k: 1 });

  // Build a deterministic "density sketch" — pseudo-random sampling so that the
  // schematic at least visually conveys "this drawing has ~N entities of these
  // kinds", until the backend ships a real preview asset.
  const sketch = useMemo(() => {
    if (!bbox?.min || !bbox?.max) return null;
    const x0 = bbox.min[0], y0 = bbox.min[1], x1 = bbox.max[0], y1 = bbox.max[1];
    const W = x1 - x0, H = y1 - y0;
    if (W <= 0 || H <= 0) return null;
    // mulberry32 deterministic PRNG seeded by sha256[:8]
    const seed = (() => {
      const s = String((cad.fingerprint || cad)?.sha256 || filename);
      let h = 0;
      for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
      return h >>> 0;
    })();
    let a = seed || 0xdeadbeef;
    const rnd = () => {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    const cap = 800; // hard cap to keep DOM cheap
    const ents = Object.entries(entityCounts);
    const total = ents.reduce((s, [, n]) => s + n, 0) || 1;
    const items: { kind: string; type: "line" | "circle" | "rect"; xs: number[] }[] = [];
    for (const [kind, n] of ents) {
      const draw = Math.min(cap, Math.max(2, Math.round((n / total) * cap)));
      const t: "line" | "circle" | "rect" =
        kind.match(/LINE|POLY|ARC|SPLINE/i)
          ? "line"
          : kind.match(/CIRCLE|ELLIPSE/i)
            ? "circle"
            : kind.match(/INSERT|HATCH|SOLID|TEXT|MTEXT|DIM/i)
              ? "rect"
              : "line";
      for (let i = 0; i < draw; i++) {
        if (t === "line") {
          items.push({
            kind, type: t,
            xs: [x0 + rnd() * W, y0 + rnd() * H, x0 + rnd() * W, y0 + rnd() * H],
          });
        } else if (t === "circle") {
          items.push({
            kind, type: t,
            xs: [x0 + rnd() * W, y0 + rnd() * H, Math.min(W, H) * 0.005 * (1 + rnd() * 3)],
          });
        } else {
          const cx = x0 + rnd() * W, cy = y0 + rnd() * H;
          const w = Math.min(W, H) * 0.01 * (1 + rnd() * 4);
          const h = Math.min(W, H) * 0.01 * (1 + rnd() * 3);
          items.push({ kind, type: t, xs: [cx - w / 2, cy - h / 2, w, h] });
        }
      }
    }
    return { x0, y0, W, H, items };
  }, [bbox, entityCounts, cad, filename]);

  // Color by kind (deterministic).
  const colorOf = (k: string) => {
    let h = 0;
    for (let i = 0; i < k.length; i++) h = (h * 31 + k.charCodeAt(i)) >>> 0;
    return `hsl(${h % 360}, 55%, 45%)`;
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-2 rounded border border-zinc-200 bg-white px-2 py-1 text-[11px] text-zinc-500">
        <Icon name="file-text" size={13} className="text-zinc-400" />
        <span className="truncate">{filename}</span>
        {bbox?.min && bbox?.max && (
          <>
            <span className="text-zinc-300">·</span>
            <span className="font-mono text-[10px]">
              {fmtNum(bbox.max[0] - bbox.min[0])} × {fmtNum(bbox.max[1] - bbox.min[1])} {stats.units || ""}
            </span>
          </>
        )}
        <div className="ml-auto flex items-center gap-1">
          {cadReady && (
            <span className="mr-2 inline-flex items-center gap-1 rounded border border-zinc-200 bg-white px-2 py-0.5 text-[10px] text-zinc-600">
              <Icon name="layers" size={10} className="text-violet-500" />
              MLightCAD
            </span>
          )}
          <button onClick={() => setView((v) => ({ ...v, k: Math.min(8, v.k * 1.2) }))} className="rounded px-1.5 py-0.5 hover:bg-zinc-100">+</button>
          <span className="font-mono">{Math.round(view.k * 100)}%</span>
          <button onClick={() => setView((v) => ({ ...v, k: Math.max(0.2, v.k / 1.2) }))} className="rounded px-1.5 py-0.5 hover:bg-zinc-100">−</button>
          <button onClick={reset} className="rounded px-1.5 py-0.5 hover:bg-zinc-100">重置</button>
        </div>
      </div>

      {/* Viewer body */}
      <div className="relative flex-1 overflow-hidden rounded border border-zinc-200 bg-white">
        {useRealCad ? (
          // MLightCAD path: independent iframe (Vue 3 + WebAssembly).
          // Same-origin so cookies + module scripts + worker work; sandbox
          // intentionally NOT set.
          <iframe
            key={dxfUrl /* force reload if file changes */}
            src={`/mlight-viewer.html?url=${encodeURIComponent(dxfUrl)}`}
            className="h-full w-full border-0"
            title="MLightCAD viewer"
            allow="clipboard-write"
          />
        ) : previewUrl ? (
          // Real preview asset path (backend-provided SVG/PNG): direct render.
          <img src={previewUrl} alt="CAD preview" className="h-full w-full object-contain" />
        ) : sketch ? (
          <>
            {/* schematic SVG */}
            <svg
              ref={svgRef}
              className="h-full w-full cursor-grab active:cursor-grabbing"
              viewBox={`${sketch.x0 - sketch.W * 0.02} ${sketch.y0 - sketch.H * 0.02} ${sketch.W * 1.04} ${sketch.H * 1.04}`}
              preserveAspectRatio="xMidYMid meet"
              onWheel={onWheel}
              onMouseDown={onDown}
              onMouseMove={onMove}
              onMouseUp={() => (drag.current = null)}
              onMouseLeave={() => (drag.current = null)}
            >
              <g transform={`translate(${view.tx}, ${view.ty}) scale(${view.k})`}>
                {/* bounding box outline (drawing extents) */}
                <rect
                  x={sketch.x0}
                  y={sketch.y0}
                  width={sketch.W}
                  height={sketch.H}
                  fill="none"
                  stroke="#a1a1aa"
                  strokeWidth={Math.max(sketch.W, sketch.H) * 0.001}
                  strokeDasharray={`${sketch.W * 0.01} ${sketch.W * 0.005}`}
                />
                {sketch.items.map((it, i) => {
                  const col = colorOf(it.kind);
                  const sw = Math.max(sketch.W, sketch.H) * 0.0006;
                  if (it.type === "line") {
                    return (
                      <line
                        key={i}
                        x1={it.xs[0]} y1={it.xs[1]} x2={it.xs[2]} y2={it.xs[3]}
                        stroke={col} strokeWidth={sw} opacity={0.55}
                      />
                    );
                  }
                  if (it.type === "circle") {
                    return (
                      <circle
                        key={i}
                        cx={it.xs[0]} cy={it.xs[1]} r={it.xs[2]}
                        fill="none" stroke={col} strokeWidth={sw} opacity={0.55}
                      />
                    );
                  }
                  return (
                    <rect
                      key={i}
                      x={it.xs[0]} y={it.xs[1]} width={it.xs[2]} height={it.xs[3]}
                      fill={col} fillOpacity={0.18} stroke={col} strokeWidth={sw} opacity={0.7}
                    />
                  );
                })}
              </g>
            </svg>

            {/* honest disclaimer banner */}
            <div className="absolute left-2 top-2 max-w-md rounded border border-amber-300 bg-amber-50/95 px-2.5 py-1.5 text-[11px] text-amber-800 shadow-sm">
              <div className="flex items-start gap-1.5">
                <Icon name="info" size={12} className="mt-0.5 shrink-0" />
                <div>
                  <div className="font-semibold">示意图，非真实 CAD 渲染</div>
                  <div className="leading-snug">
                    基于 bounding_box + entity_counts 按类型概率撒点，仅用于"看出图纸有多大、密度高低"。后端未提供 DXF (旧 run / 非 CAD 输入) — 重新上传可启用真实渲染。
                  </div>
                </div>
              </div>
            </div>

            {/* legend by kind */}
            <div className="pointer-events-none absolute bottom-2 right-2 max-w-[260px] rounded bg-white/95 px-2 py-1.5 text-[10px] shadow-sm">
              <div className="mb-1 font-semibold uppercase tracking-wide text-zinc-500">实体类型图例</div>
              <div className="grid grid-cols-2 gap-x-2 gap-y-0.5">
                {Object.entries(entityCounts).slice(0, 10).map(([k, n]) => (
                  <div key={k} className="flex items-center gap-1.5 truncate">
                    <span className="inline-block h-2 w-2 rounded-sm" style={{ background: colorOf(k) }} />
                    <span className="truncate font-mono text-zinc-700">{k}</span>
                    <span className="ml-auto text-zinc-400">{n}</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : (
          <div className="flex h-full items-center justify-center p-6">
            <div className="max-w-sm rounded border border-dashed border-zinc-300 p-5 text-center text-[12px] text-zinc-500">
              <Icon name="alert-circle" size={20} className="mx-auto mb-2 text-zinc-400" />
              parser 未提供 bounding_box / entity_counts，无法生成示意图
            </div>
          </div>
        )}
      </div>

      {/* Status bar */}
      <div className="flex items-center gap-3 rounded border border-zinc-200 bg-white px-3 py-1.5 text-[11px] text-zinc-500">
        <Icon name="circle-dot" size={11} className={useRealCad ? "text-emerald-500" : "text-zinc-400"} />
        <span>
          {useRealCad
            ? "原始文件预览 · DXF (MLightCAD)"
            : "原始文件预览 · 示意图 (schematic)"}
        </span>
        <span>·</span>
        <span>实体 {stats.entity_total ?? "—"}</span>
        <span>·</span>
        <span>图层 {stats.layer_count ?? "—"}</span>
        <span className="ml-auto italic text-zinc-400">
          {useRealCad
            ? "MLightCAD · Vue 3 + WebAssembly · iframe 嵌入"
            : "滚轮缩放 · 拖拽平移"}
        </span>
      </div>
    </div>
  );
}

// ── Raw view: metadata + entity histogram + raw layer list ───────────
function RawView({ run }: { run: RunDetail }) {
  const enrich = getEnrichment(run);
  const stats = (run.site_model_statistics as any) || {};
  const cad = (run.site_model_cad_source as any) || {};
  const fp = cad.fingerprint || cad; // fingerprint may be merged
  const entityCounts: Record<string, number> = stats.entity_counts || {};
  const sortedEntities = Object.entries(entityCounts).sort((a, b) => b[1] - a[1]);
  const maxCnt = sortedEntities[0]?.[1] || 1;
  const A = enrich?.sections.A_normalize?.items || [];
  const bbox = stats.bounding_box;
  const filename = cad.filename || (run.input_payload as any)?.filename || "未知文件";

  return (
    <div className="grid flex-1 grid-cols-2 gap-2 overflow-hidden">
      {/* Left: file metadata + entity histogram */}
      <div className="flex flex-col gap-2 overflow-y-auto rounded border border-zinc-200 bg-white p-3">
        <header className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-700">
          <Icon name="file-text" size={13} className="text-zinc-500" />
          文件元信息
        </header>
        <div className="grid grid-cols-2 gap-1.5 text-[11.5px]">
          <KV k="文件名" v={<span className="truncate">{filename}</span>} />
          <KV k="DXF 版本" v={cad.dxf_version || cad.schema || "—"} />
          <KV k="单位" v={stats.units || "—"} />
          <KV k="实体总数" v={(stats.entity_total ?? "—").toLocaleString?.() ?? stats.entity_total} />
          <KV k="图层数" v={stats.layer_count ?? "—"} />
          <KV k="块定义数" v={stats.block_definition_count ?? "—"} />
          <KV k="文件大小" v={fp?.size_bytes ? `${(fp.size_bytes / 1024).toFixed(1)} KB` : "—"} />
          <KV
            k="SHA-256"
            v={
              <span className="font-mono text-[10px] text-zinc-500" title={fp?.sha256}>
                {fp?.sha256 ? `${String(fp.sha256).slice(0, 12)}…` : "—"}
              </span>
            }
          />
        </div>

        {bbox?.min && bbox?.max && (
          <>
            <header className="mt-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-700">
              <Icon name="ruler" size={13} className="text-zinc-500" />
              图纸范围 (bounding box)
            </header>
            <div className="rounded bg-zinc-50 p-2 font-mono text-[10.5px] text-zinc-700">
              <div>min: ({fmtNum(bbox.min[0])}, {fmtNum(bbox.min[1])})</div>
              <div>max: ({fmtNum(bbox.max[0])}, {fmtNum(bbox.max[1])})</div>
              <div className="mt-1 text-zinc-500">
                ≈ {fmtNum(bbox.max[0] - bbox.min[0])} × {fmtNum(bbox.max[1] - bbox.min[1])} {stats.units || ""}
              </div>
            </div>
          </>
        )}

        <header className="mt-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-700">
          <Icon name="bar-chart" size={13} className="text-zinc-500" />
          实体类型分布 ({sortedEntities.length})
        </header>
        {sortedEntities.length === 0 && <EmptyRow>无 entity_counts</EmptyRow>}
        <div className="space-y-1">
          {sortedEntities.slice(0, 14).map(([k, v]) => (
            <div key={k} className="flex items-center gap-2 text-[11px]">
              <span className="w-24 shrink-0 truncate font-mono text-zinc-700">{k}</span>
              <div className="relative h-3 flex-1 overflow-hidden rounded bg-zinc-100">
                <div
                  className="absolute inset-y-0 left-0 bg-zinc-400"
                  style={{ width: `${(v / maxCnt) * 100}%` }}
                />
              </div>
              <span className="w-12 shrink-0 text-right font-mono text-zinc-600">
                {v.toLocaleString()}
              </span>
            </div>
          ))}
        </div>
        {(stats.warnings || []).length > 0 && (
          <div className="mt-2 rounded border border-amber-200 bg-amber-50 p-2 text-[11px] text-amber-800">
            <div className="mb-1 font-semibold">解析告警 ({stats.warnings.length})</div>
            <ul className="list-disc space-y-0.5 pl-4">
              {stats.warnings.slice(0, 4).map((w: any, i: number) => (
                <li key={i}>{typeof w === "string" ? w : JSON.stringify(w)}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Right: raw vs normalized table */}
      <div className="flex flex-col overflow-hidden rounded border border-zinc-200 bg-white">
        <header className="flex items-center gap-1.5 border-b border-zinc-100 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-700">
          <Icon name="arrow-right" size={13} className="text-zinc-500" />
          原始命名 → A_normalize 归一化（前 {Math.min(A.length, 60)} 条）
        </header>
        {A.length === 0 && (
          <div className="p-4 text-[12px] text-zinc-500">无 A_normalize 输出</div>
        )}
        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-zinc-50 text-[10px] uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-2 py-1.5 text-left font-semibold">原始</th>
                <th className="px-2 py-1.5 text-left font-semibold">归一化</th>
                <th className="px-2 py-1.5 text-left font-semibold">语种</th>
                <th className="px-2 py-1.5 text-left font-semibold">动作</th>
              </tr>
            </thead>
            <tbody>
              {A.slice(0, 60).map((it: any, i: number) => {
                const changed = it.original !== it.normalized;
                return (
                  <tr key={i} className="border-t border-zinc-100 hover:bg-zinc-50">
                    <td className="max-w-[160px] truncate px-2 py-1 font-mono text-zinc-800" title={it.original}>
                      {it.original || "—"}
                    </td>
                    <td
                      className={[
                        "max-w-[160px] truncate px-2 py-1 font-mono",
                        changed ? "font-semibold text-violet-700" : "text-zinc-500",
                      ].join(" ")}
                      title={it.normalized}
                    >
                      {it.normalized || "—"}
                    </td>
                    <td className="px-2 py-1">
                      <span className="rounded bg-zinc-100 px-1 py-0.5 text-[10px] uppercase text-zinc-600">
                        {it.lang || "und"}
                      </span>
                    </td>
                    <td className="px-2 py-1 text-[10px] text-zinc-500" title={it.reason}>
                      {(it.reason || "").length > 28 ? (it.reason || "").slice(0, 28) + "…" : it.reason}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ── Parsed view: SVG viewport with synthesized rects per cluster proposal
function ParsedView({
  run,
  selected,
  onSelect,
}: {
  run: RunDetail;
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const enrich = getEnrichment(run);
  const D = enrich?.sections.D_cluster_proposals;
  const proposals: any[] = D?.proposals || [];
  const recognized: any[] = enrich?.sections.C_arbiter?.promotion_candidates || [];

  // Hand-rolled pan/zoom state (no d3 dep).
  const [view, setView] = useState({ tx: 0, ty: 0, k: 1 });
  const svgRef = useRef<SVGSVGElement | null>(null);
  const drag = useRef<{ sx: number; sy: number; stx: number; sty: number } | null>(null);

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    const nk = Math.max(0.2, Math.min(6, view.k * factor));
    const ntx = mx - (mx - view.tx) * (nk / view.k);
    const nty = my - (my - view.ty) * (nk / view.k);
    setView({ tx: ntx, ty: nty, k: nk });
  };
  const onMouseDown = (e: React.MouseEvent) => {
    drag.current = { sx: e.clientX, sy: e.clientY, stx: view.tx, sty: view.ty };
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (!drag.current) return;
    setView((v) => ({
      ...v,
      tx: drag.current!.stx + (e.clientX - drag.current!.sx),
      ty: drag.current!.sty + (e.clientY - drag.current!.sy),
    }));
  };
  const endDrag = () => {
    drag.current = null;
  };
  const reset = () => setView({ tx: 0, ty: 0, k: 1 });

  // Synthesize rectangles: grid-layout proposals into a 1200×800 world.
  const WORLD_W = 1200;
  const items = useMemo(() => {
    const cols = Math.max(4, Math.ceil(Math.sqrt(Math.max(1, proposals.length))));
    const cellW = WORLD_W / cols;
    const cellH = cellW * 0.65;
    return proposals.map((p, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const weight = Math.max(0.35, Math.min(0.9, ((p.member_count || 1) / 8) * 0.5 + 0.4));
      const w = cellW * weight;
      const h = cellH * weight;
      const x = col * cellW + (cellW - w) / 2;
      const y = 40 + row * (cellH + 20) + (cellH - h) / 2;
      return { id: p.cluster_id || `cluster_${i}`, x, y, w, h, p };
    });
  }, [proposals]);

  return (
    <div className="flex flex-1 flex-col gap-2 overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center gap-1 rounded border border-zinc-200 bg-white px-2 py-1">
        {(
          [
            ["target", "选择"],
            ["search", "框选 (TODO)"],
            ["ruler", "测距 (TODO)"],
            ["link", "关联 (TODO)"],
            ["layers", "图层 (TODO)"],
          ] as const
        ).map(([n, t]) => (
          <button
            key={n}
            title={t}
            className="inline-flex h-7 w-7 items-center justify-center rounded text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900"
          >
            <Icon name={n as IconName} size={15} />
          </button>
        ))}
        <span className="ml-2 text-[11px] text-zinc-400">
          {proposals.length} 待审 · {recognized.length} 已识别
        </span>
        <div className="ml-auto flex items-center gap-1 text-[11px]">
          <button
            onClick={() => setView((v) => ({ ...v, k: Math.min(6, v.k * 1.2) }))}
            className="rounded px-1.5 py-0.5 text-zinc-500 hover:bg-zinc-100"
            title="放大"
          >
            +
          </button>
          <span className="font-mono text-zinc-500">{Math.round(view.k * 100)}%</span>
          <button
            onClick={() => setView((v) => ({ ...v, k: Math.max(0.2, v.k / 1.2) }))}
            className="rounded px-1.5 py-0.5 text-zinc-500 hover:bg-zinc-100"
            title="缩小"
          >
            −
          </button>
          <button onClick={reset} className="rounded px-1.5 py-0.5 text-zinc-500 hover:bg-zinc-100">
            重置
          </button>
        </div>
      </div>

      {/* Canvas */}
      <div className="relative flex-1 overflow-hidden rounded border border-zinc-200 bg-white">
        <div className="absolute inset-0 [background-image:linear-gradient(#e5e7eb_1px,transparent_1px),linear-gradient(90deg,#e5e7eb_1px,transparent_1px)] [background-size:32px_32px] opacity-30" />
        <svg
          ref={svgRef}
          className="relative h-full w-full cursor-grab active:cursor-grabbing"
          onWheel={onWheel}
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={endDrag}
          onMouseLeave={endDrag}
          onClick={(e) => {
            if ((e.target as SVGElement).tagName === "svg") onSelect(null);
          }}
        >
          <g transform={`translate(${view.tx}, ${view.ty}) scale(${view.k})`}>
            {items.length === 0 && (
              <text x={40} y={60} className="fill-zinc-400" fontSize={14}>
                无聚类 proposal — quarantine 为空或已全部仲裁通过
              </text>
            )}
            {items.map((it) => {
              const active = selected === it.id || (selected === null && items[0]?.id === it.id);
              return (
                <g key={it.id} onClick={(e) => { e.stopPropagation(); onSelect(it.id); }} className="cursor-pointer">
                  <rect
                    x={it.x}
                    y={it.y}
                    width={it.w}
                    height={it.h}
                    rx={4}
                    className={
                      active
                        ? "fill-violet-100 stroke-violet-600"
                        : "fill-amber-50 stroke-amber-400 hover:fill-amber-100"
                    }
                    strokeWidth={active ? 2.5 : 1.5}
                  />
                  <text
                    x={it.x + it.w / 2}
                    y={it.y + it.h / 2 - 4}
                    textAnchor="middle"
                    className={active ? "fill-violet-800" : "fill-zinc-700"}
                    fontSize={Math.min(16, it.w / 10)}
                    fontWeight={600}
                  >
                    {String(it.p.suggested_term || it.p.asset_type_hint || it.id).slice(0, 18)}
                  </text>
                  <text
                    x={it.x + it.w / 2}
                    y={it.y + it.h / 2 + 12}
                    textAnchor="middle"
                    className="fill-zinc-500"
                    fontSize={Math.min(11, it.w / 14)}
                  >
                    ×{it.p.member_count || 0} · {it.p.asset_type_hint || "Other"}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>

        {/* Legend */}
        <div className="pointer-events-none absolute bottom-2 left-2 flex items-center gap-3 rounded bg-white/90 px-2 py-1 text-[10px] text-zinc-500 shadow-sm">
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-2 w-3 rounded-sm bg-amber-100 ring-1 ring-amber-400" />
            待审
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-2 w-3 rounded-sm bg-violet-100 ring-2 ring-violet-600" />
            已选中
          </span>
          <span>· 滚轮缩放 · 拖拽平移</span>
        </div>
      </div>

      {/* Status bar */}
      <div className="flex items-center gap-3 rounded border border-zinc-200 bg-white px-3 py-1.5 text-[11px] text-zinc-500">
        <span className="inline-flex items-center gap-1">
          <Icon name="circle-dot" size={11} className="text-emerald-500" />
          LLM pipeline · {enrich?.steps_run.length ?? 0}/13
        </span>
        <span>·</span>
        <span>几何完整性 {fmtPct(run.geometry_integrity_score)}</span>
        <span>·</span>
        <span>资产 {run.site_model_assets_count}</span>
        {selected && (
          <span className="ml-auto font-mono text-[10px] text-violet-600">selected: {selected}</span>
        )}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Right panel: selected object props · AI suggestion · trust · event log
// ──────────────────────────────────────────────────────────────────────
function RightPanel({ run, selected }: { run: RunDetail; selected: string | null }) {
  const enrich = getEnrichment(run);
  const proposals = enrich?.sections.D_cluster_proposals?.proposals || [];
  const pick = useMemo(() => {
    if (selected) return proposals.find((p: any) => p.cluster_id === selected) || proposals[0];
    return proposals[0];
  }, [proposals, selected]);

  return (
    <aside className="flex flex-col gap-3 overflow-y-auto">
      <SelectedObjectCard pick={pick} />
      <AISuggestionCard run={run} pick={pick} />
      <TrustTokenCard run={run} />
      <EventLogCard run={run} />
    </aside>
  );
}

function SelectedObjectCard({ pick }: { pick: any }) {
  if (!pick) {
    return (
      <Panel title="选中对象" icon="target">
        <p className="text-[12px] text-zinc-500">点击左侧「待人工确认」一项，或画布对象（P2）查看属性</p>
      </Panel>
    );
  }
  return (
    <Panel title="选中对象" icon="target">
      <div className="space-y-1 text-[12px]">
        <KV k="cluster_id" v={<span className="font-mono">{pick.cluster_id || "—"}</span>} />
        <KV k="成员数" v={pick.member_count ?? "—"} />
        <KV k="累计频次" v={pick.total_count ?? "—"} />
        <KV k="资产类型" v={pick.asset_type_hint || "—"} />
        <KV k="建议术语" v={<span className="font-medium">{pick.suggested_term || "—"}</span>} />
      </div>
    </Panel>
  );
}

function AISuggestionCard({ run, pick }: { run: RunDetail; pick: any }) {
  const enrich = getEnrichment(run);
  const [accepted, setAccepted] = useState<null | "accepted" | "ignored">(null);
  // Reset local decision when selection changes.
  const pickKey = pick?.cluster_id || "";
  useMemo(() => {
    setAccepted(null);
    return null;
  }, [pickKey]);

  if (!pick) {
    return (
      <Panel title="AI 建议" icon="sparkles" accent="violet">
        <p className="text-[12px] text-zinc-500">暂无待审项 — 所有图层均已识别或无 quarantine 残留。</p>
      </Panel>
    );
  }

  const signature = `embed:stub-64d + chat:${enrich?.version || "stub-v0"}`;
  // Timings for D + E (the two steps most relevant to this suggestion).
  const latency = Math.round((enrich?.timings_ms?.D_cluster_proposals || 0) + (enrich?.timings_ms?.E_block_kind || 0));

  // Confidence from real proposal signals (no backend "confidence" yet — synthesize transparently).
  const memberBoost = Math.min(0.35, (pick.member_count || 0) * 0.05);
  const freqBoost = Math.min(0.32, Math.log10((pick.total_count || 1) + 1) * 0.2);
  const typeBoost = pick.asset_type_hint && pick.asset_type_hint !== "Other" ? 0.2 : 0.1;
  const confidence = Math.min(0.99, 0.2 + memberBoost + freqBoost + typeBoost);
  const threshold = 0.75;
  const ok = confidence >= threshold;

  const evidenceList: any[] = Array.isArray(pick.evidence) ? pick.evidence : [];
  const steps: { label: string; note: string; weight: number }[] = [
    {
      label: "聚类规模",
      note: `${pick.member_count || 0} 条成员 · 累计 ${pick.total_count || 0} 次出现`,
      weight: memberBoost,
    },
    {
      label: "频次信号",
      note: evidenceList[0]?.mcp_context_id
        ? `首证来自 run ${String(evidenceList[0].mcp_context_id).slice(0, 8)}…`
        : "跨运行聚合",
      weight: freqBoost,
    },
    {
      label: "资产类型提示",
      note: `多数票 → ${pick.asset_type_hint || "Other"}`,
      weight: typeBoost,
    },
    {
      label: "基础先验",
      note: "术语归一化 + softmatch 未命中 gold",
      weight: 0.2,
    },
  ];

  return (
    <Panel title="AI 建议" icon="sparkles" accent="violet">
      <div className="space-y-3">
        <div className="rounded bg-violet-50 px-2 py-1.5 text-[11px] text-violet-700">
          <div className="flex items-center justify-between">
            <span className="font-mono">{signature}</span>
            <span>延迟 {latency}ms</span>
          </div>
        </div>

        <div>
          <div className="mb-1 text-[11px] font-medium text-zinc-600">建议标注</div>
          <div className="rounded border border-violet-200 bg-white px-2 py-1.5 font-medium text-violet-800">
            {pick.suggested_term || pick.asset_type_hint || pick.cluster_id}
          </div>
        </div>

        <div>
          <div className="mb-1.5 text-[11px] font-medium text-zinc-600">推理链</div>
          <ol className="space-y-1">
            {steps.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-[12px]">
                <span className="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-violet-100 text-[10px] font-semibold text-violet-700">
                  {i + 1}
                </span>
                <div className="flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-medium text-zinc-800">{s.label}</span>
                    {s.weight > 0 && <span className="text-[10px] text-zinc-400">+{s.weight.toFixed(2)}</span>}
                  </div>
                  <div className="text-[11px] leading-snug text-zinc-500">{s.note}</div>
                </div>
              </li>
            ))}
          </ol>
        </div>

        {/* Confidence bar */}
        <div>
          <div className="mb-1 flex items-center justify-between text-[11px]">
            <span className="text-zinc-600">综合置信度</span>
            <span className={ok ? "font-semibold text-emerald-700" : "font-semibold text-amber-700"}>
              {(confidence * 100).toFixed(0)}%
            </span>
          </div>
          <div className="relative h-2 overflow-hidden rounded-full bg-zinc-100">
            <div
              className={["absolute inset-y-0 left-0", ok ? "bg-emerald-500" : "bg-amber-500"].join(" ")}
              style={{ width: `${confidence * 100}%` }}
            />
            <div
              className="absolute inset-y-0 w-px bg-zinc-400"
              style={{ left: `${threshold * 100}%` }}
              title={`阈值 ${threshold}`}
            />
          </div>
          <div className="mt-0.5 flex justify-between text-[10px] text-zinc-400">
            <span>0</span>
            <span>阈值 {threshold}</span>
            <span>1</span>
          </div>
          <div className="mt-1 font-mono text-[10px] text-zinc-500">
            {steps
              .filter((s) => s.weight > 0)
              .map((s) => s.weight.toFixed(2))
              .join(" + ")}{" "}
            = {confidence.toFixed(2)}
          </div>
        </div>

        {/* Actions */}
        {accepted === null ? (
          <div className="flex items-center gap-2 pt-1">
            <button
              onClick={() => setAccepted("accepted")}
              className="inline-flex flex-1 items-center justify-center gap-1.5 rounded bg-violet-600 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-violet-700"
            >
              <Icon name="check" size={14} /> 采纳建议
            </button>
            <button
              onClick={() => setAccepted("ignored")}
              className="inline-flex items-center justify-center gap-1.5 rounded border border-zinc-300 px-3 py-1.5 text-[12px] text-zinc-700 hover:bg-zinc-50"
            >
              <Icon name="x" size={14} /> 忽略
            </button>
          </div>
        ) : (
          <div
            className={[
              "rounded px-2 py-1.5 text-[11px]",
              accepted === "accepted"
                ? "bg-emerald-50 text-emerald-700"
                : "bg-zinc-100 text-zinc-600",
            ].join(" ")}
          >
            {accepted === "accepted" ? "已采纳（P1 将写入审计日志）" : "已忽略"}
            <button onClick={() => setAccepted(null)} className="ml-2 underline">
              撤销
            </button>
          </div>
        )}
      </div>
    </Panel>
  );
}

function TrustTokenCard({ run }: { run: RunDetail }) {
  const enrich = getEnrichment(run);
  const F = enrich?.sections.F_quality_breakdown;
  const I = enrich?.sections.I_self_check;
  const blocked = I?.should_block;
  return (
    <Panel
      title="信任凭证 CP-A"
      icon={blocked ? "shield-alert" : "shield-check"}
      accent={blocked ? "red" : "emerald"}
    >
      <div className="grid grid-cols-3 gap-1.5 text-center">
        {[
          ["解析", F?.parse],
          ["语义", F?.semantic],
          ["完整", F?.integrity],
        ].map(([label, v]) => (
          <div key={label as string} className="rounded bg-zinc-50 px-1 py-1.5">
            <div className="text-[10px] text-zinc-500">{label}</div>
            <div className="text-[13px] font-semibold text-zinc-800">{fmtPct(v as number)}</div>
          </div>
        ))}
      </div>
      <div className="mt-2 flex items-center justify-between rounded bg-zinc-900 px-2 py-1.5 text-[12px] text-white">
        <span className="text-zinc-400">综合</span>
        <span className="font-semibold">{fmtPct(F?.overall)}</span>
      </div>
      {F?.why && <p className="mt-1 text-[11px] leading-snug text-zinc-500">{F.why}</p>}
    </Panel>
  );
}

function EventLogCard({ run }: { run: RunDetail }) {
  const enrich = getEnrichment(run);
  const steps = enrich?.steps_run || [];
  const timings = enrich?.timings_ms || {};
  return (
    <Panel title="事件日志" icon="history">
      <ol className="space-y-1.5">
        {steps.map((s, i) => (
          <li key={s} className="flex items-start gap-2 text-[11px]">
            <span className="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-zinc-100 font-mono text-[9px] text-zinc-600">
              {i + 1}
            </span>
            <div className="flex-1">
              <span className="font-mono text-zinc-800">{s}</span>
              <span className="ml-1 text-zinc-400">· {Math.round(timings[s] || 0)}ms</span>
            </div>
            <Icon name="check" size={11} className="text-emerald-500" />
          </li>
        ))}
        {steps.length === 0 && <EmptyRow>无事件</EmptyRow>}
      </ol>
    </Panel>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Primitives
// ──────────────────────────────────────────────────────────────────────
function Panel({
  title,
  icon,
  right,
  accent,
  children,
}: {
  title: string;
  icon: IconName;
  right?: React.ReactNode;
  accent?: "violet" | "emerald" | "red";
  children: React.ReactNode;
}) {
  const accentBar: Record<string, string> = {
    violet: "border-l-4 border-l-violet-500",
    emerald: "border-l-4 border-l-emerald-500",
    red: "border-l-4 border-l-red-500",
  };
  return (
    <section
      className={[
        "rounded border border-zinc-200 bg-white",
        accent ? accentBar[accent] : "",
      ].join(" ")}
    >
      <header className="flex items-center gap-1.5 border-b border-zinc-100 px-2.5 py-1.5 text-[11px] font-semibold tracking-wide text-zinc-700">
        <Icon name={icon} size={13} className="text-zinc-500" />
        <span className="uppercase">{title}</span>
        {right && <span className="ml-auto font-normal">{right}</span>}
      </header>
      <div className="p-2.5">{children}</div>
    </section>
  );
}

function TreeGroup({
  label,
  count,
  tone,
  children,
}: {
  label: string;
  count: number;
  tone: "ok" | "warn";
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  const toneCls = tone === "ok" ? "text-emerald-700" : "text-amber-700";
  return (
    <div className="mb-1.5 last:mb-0">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1 rounded px-1 py-0.5 text-[11px] font-medium hover:bg-zinc-50"
      >
        <Icon name={open ? "chevron-down" : "chevron-right"} size={11} className="text-zinc-400" />
        <span className={toneCls}>{label}</span>
        <span className="ml-auto text-[10px] text-zinc-400">{count}</span>
      </button>
      {open && <div className="mt-0.5 space-y-0.5 pl-4">{children}</div>}
    </div>
  );
}

function TreeLeaf({
  icon,
  tone,
  label,
  meta,
  active,
  onClick,
}: {
  icon: IconName;
  tone: "ok" | "warn";
  label: string;
  meta?: string;
  active?: boolean;
  onClick?: () => void;
}) {
  const toneCls = tone === "ok" ? "text-emerald-500" : "text-amber-500";
  const activeCls = active ? "bg-violet-50 text-violet-800 ring-1 ring-violet-200" : "text-zinc-700 hover:bg-zinc-50";
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      onClick={onClick}
      className={[
        "flex w-full items-center gap-1.5 truncate rounded px-1 py-0.5 text-left text-[11.5px]",
        activeCls,
      ].join(" ")}
    >
      <Icon name={icon} size={11} className={toneCls} />
      <span className="truncate">{label}</span>
      {meta && <span className="ml-auto text-[10px] text-zinc-400">{meta}</span>}
    </Tag>
  );
}

function CheckRow({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-1.5 py-0.5 text-[11.5px]">
      <Icon
        name={ok ? "check" : "x"}
        size={12}
        className={ok ? "text-emerald-500" : "text-red-500"}
      />
      <span className="text-zinc-700">{label}</span>
    </div>
  );
}

function StatRow({ k, v, label, value }: { k?: string; v?: React.ReactNode; label?: string; value?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-0.5 text-[11.5px]">
      <span className="text-zinc-500">{label ?? k}</span>
      <span className="font-mono text-zinc-800">{(value ?? v) as React.ReactNode}</span>
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-zinc-500">{k}</span>
      <span className="text-zinc-800">{v}</span>
    </div>
  );
}

function EmptyRow({ children }: { children: React.ReactNode }) {
  return <div className="px-1 py-1 text-[11px] text-zinc-400">{children}</div>;
}

function StageComingSoon({ stage }: { stage: { label: string; icon: IconName; desc: string } }) {
  return (
    <div className="flex flex-1 items-center justify-center p-8">
      <div className="max-w-md rounded-lg border border-dashed border-zinc-300 bg-white p-8 text-center">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-zinc-100 text-zinc-500">
          <Icon name={stage.icon} size={22} />
        </div>
        <div className="text-sm font-semibold text-zinc-800">{stage.label}</div>
        <p className="mt-1 text-[12px] leading-relaxed text-zinc-500">{stage.desc}</p>
        <div className="mt-3 inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700">
          <Icon name="info" size={11} /> 该阶段规划中 · 当前 Epic 聚焦 S1
        </div>
      </div>
    </div>
  );
}

function FullBleedMsg({ children, error }: { children: React.ReactNode; error?: boolean }) {
  return (
    <div className="flex h-[calc(100vh-65px)] items-center justify-center bg-zinc-50">
      <p className={["text-sm", error ? "text-red-600" : "text-zinc-500"].join(" ")}>{children}</p>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Utils
// ──────────────────────────────────────────────────────────────────────
function getEnrichment(run: RunDetail): LLMEnrichment | null {
  const e = (run.output_payload as any)?.llm_enrichment;
  if (!e || typeof e !== "object") return null;
  return e as LLMEnrichment;
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v as number)) return "—";
  const n = typeof v === "number" ? v : Number(v);
  if (n > 1) return `${Math.round(n)}%`;
  return `${Math.round(n * 100)}%`;
}

function fmtNum(v: any): string {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  if (Math.abs(n) >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 1 });
  return n.toFixed(2);
}
