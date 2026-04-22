"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { Icon } from "@/components/icons";

// Sites list: pivots the runs feed to a "SiteModel-first" view.
// Each run that produced a SiteModel becomes an entry here.
export default function SitesPage() {
  const q = useQuery({
    queryKey: ["sites-as-runs"],
    queryFn: () => api.listRuns(1, 50),
    refetchInterval: 5000,
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
          <li key={r.mcp_context_id}>
            <Link
              href={`/sites/${r.mcp_context_id}`}
              className="group block rounded-lg border border-zinc-200 bg-white p-4 transition hover:border-violet-400 hover:shadow-sm"
            >
              <div className="mb-2 flex items-center gap-2">
                <StatusBadge status={r.status} />
                <span className="ml-auto font-mono text-[11px] text-zinc-400">
                  {r.mcp_context_id.slice(0, 10)}…
                </span>
              </div>
              <div className="text-sm font-medium text-zinc-900 group-hover:text-violet-700">
                {r.agent} <span className="text-zinc-400">·</span>{" "}
                <span className="font-normal text-zinc-600">{r.agent_version || "unversioned"}</span>
              </div>
              <div className="mt-1 flex items-center justify-between text-[11px] text-zinc-500">
                <span>{new Date(r.timestamp).toLocaleString()}</span>
                {typeof r.latency_ms === "number" && r.latency_ms > 0 && (
                  <span>{(r.latency_ms / 1000).toFixed(1)}s</span>
                )}
              </div>
            </Link>
          </li>
        ))}
      </ul>

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
