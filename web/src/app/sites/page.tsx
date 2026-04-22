"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { Icon } from "@/components/icons";

// Sites list: pivots the runs feed to a "SiteModel-first" view.
// Each run that produced a SiteModel becomes an entry here.
function formatBytes(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

export default function SitesPage() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["sites-as-runs"],
    queryFn: () => api.listRuns(1, 50),
    refetchInterval: 5000,
  });
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const delMut = useMutation({
    mutationFn: (id: string) => api.deleteRun(id),
    onSuccess: () => {
      setPendingDelete(null);
      setErrorMsg(null);
      qc.invalidateQueries({ queryKey: ["sites-as-runs"] });
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
    onError: (err: unknown) => {
      setErrorMsg(err instanceof Error ? err.message : "删除失败");
    },
  });

  const items = q.data?.items || [];

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">SiteModel 工作台</h1>
          <p className="mt-1 text-sm text-zinc-500">
            每一份上传的 CAD 图纸 = 一个 SiteModel · 点开进入三栏工作台审核 AI 识别结果
          </p>
        </div>
        <Link
          href="/runs"
          className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-900"
        >
          <Icon name="history" size={14} />
          技术视图 · Runs
        </Link>
      </header>

      {q.isLoading && <p className="text-sm text-zinc-500">加载中…</p>}
      {q.isError && <p className="text-sm text-red-600">加载失败</p>}

      <ul className="grid gap-3 md:grid-cols-2">
        {items.map((r) => (
          <li key={r.mcp_context_id} className="relative">
            <Link
              href={`/sites/${r.mcp_context_id}`}
              className="group block rounded-lg border border-zinc-200 bg-white p-4 transition hover:border-violet-400 hover:shadow-sm"
            >
              <div className="mb-2 flex items-center gap-2">
                <StatusBadge status={r.status} />
                <span className="ml-auto pr-7 font-mono text-[11px] text-zinc-400">
                  {r.mcp_context_id.slice(0, 10)}…
                </span>
              </div>
              <div
                className="truncate pr-7 text-sm font-medium text-zinc-900 group-hover:text-violet-700"
                title={r.filename || "(unknown filename)"}
              >
                {r.filename || "(unknown filename)"}
              </div>
              <div className="mt-0.5 flex items-center gap-2 text-[11px] text-zinc-500">
                {r.detected_format && (
                  <span className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono uppercase text-zinc-600">
                    {r.detected_format}
                  </span>
                )}
                {typeof r.size_bytes === "number" && (
                  <span>{formatBytes(r.size_bytes)}</span>
                )}
                <span className="text-zinc-400">·</span>
                <span>{r.agent} {r.agent_version || ""}</span>
              </div>
              <div className="mt-2 flex items-center justify-between text-[11px] text-zinc-500">
                <span>{new Date(r.timestamp).toLocaleString()}</span>
                {typeof r.latency_ms === "number" && r.latency_ms > 0 && (
                  <span>{(r.latency_ms / 1000).toFixed(1)}s</span>
                )}
              </div>
            </Link>
            {/* Delete button — absolutely positioned so it sits OUTSIDE the <a>. */}
            <button
              type="button"
              aria-label={`删除 run ${r.mcp_context_id.slice(0, 8)}`}
              title="删除该 SiteModel 及其所有数据/文件"
              disabled={delMut.isPending}
              onClick={() => {
                if (pendingDelete === r.mcp_context_id) {
                  delMut.mutate(r.mcp_context_id);
                } else {
                  setPendingDelete(r.mcp_context_id);
                  setErrorMsg(null);
                }
              }}
              onBlur={() => setPendingDelete((cur) => (cur === r.mcp_context_id ? null : cur))}
              className={
                "absolute right-2 top-2 rounded px-2 py-0.5 text-[11px] font-medium transition " +
                (pendingDelete === r.mcp_context_id
                  ? "bg-red-600 text-white hover:bg-red-700"
                  : "bg-white/0 text-zinc-400 hover:bg-red-50 hover:text-red-600") +
                (delMut.isPending ? " opacity-50" : "")
              }
            >
              {pendingDelete === r.mcp_context_id ? "确认删除" : "✕"}
            </button>
          </li>
        ))}
      </ul>

      {errorMsg && (
        <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          删除失败：{errorMsg}
        </div>
      )}

      {items.length === 0 && !q.isLoading && (
        <div className="rounded-lg border border-dashed border-zinc-300 bg-zinc-50 p-8 text-center">
          <p className="text-sm text-zinc-500">还没有 SiteModel。</p>
          <Link
            href="/runs"
            className="mt-3 inline-flex items-center gap-1.5 rounded bg-violet-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-violet-700"
          >
            <Icon name="upload" size={14} /> 上传第一份图纸
          </Link>
        </div>
      )}
    </div>
  );
}
