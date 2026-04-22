"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { UploadForm } from "@/components/UploadForm";

const PAGE_SIZE = 20;
const ACTIVE_STATUSES = new Set(["PENDING", "RUNNING"]);

export default function RunsPage() {
  const [page, setPage] = useState(1);

  const q = useQuery({
    queryKey: ["runs", page],
    queryFn: () => api.listRuns(page, PAGE_SIZE),
    // Auto-refresh while there are non-terminal runs visible.
    refetchInterval: (query) => {
      const items = query.state.data?.items || [];
      return items.some((r) => ACTIVE_STATUSES.has(r.status)) ? 2000 : false;
    },
  });

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-6">
      <header className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">ParseAgent runs</h1>
        {q.data && (
          <span className="text-sm text-zinc-500">
            {q.data.total} total · page {q.data.page}
          </span>
        )}
      </header>

      <UploadForm />

      <section className="overflow-x-auto rounded border bg-white">
        <table className="w-full text-sm">
          <thead className="bg-zinc-50 text-left text-xs uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="px-3 py-2">Run ID</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Started</th>
              <th className="px-3 py-2">Latency</th>
            </tr>
          </thead>
          <tbody>
            {q.isLoading && (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-zinc-400">
                  Loading…
                </td>
              </tr>
            )}
            {q.isError && (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-status-error">
                  Failed to load runs: {String((q.error as Error).message)}
                </td>
              </tr>
            )}
            {q.data?.items.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-zinc-400">
                  No runs yet. Upload a CAD file above.
                </td>
              </tr>
            )}
            {q.data?.items.map((r) => (
              <tr key={r.mcp_context_id} className="border-t hover:bg-zinc-50">
                <td className="px-3 py-2 font-mono text-xs">
                  <Link className="hover:underline" href={`/runs/${r.mcp_context_id}`}>
                    {r.mcp_context_id.slice(0, 12)}…
                  </Link>
                </td>
                <td className="px-3 py-2">
                  <StatusBadge status={r.status} />
                </td>
                <td className="px-3 py-2 text-zinc-600">
                  {new Date(r.timestamp).toLocaleString()}
                </td>
                <td className="px-3 py-2 text-zinc-600">
                  {r.latency_ms != null ? `${r.latency_ms} ms` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <footer className="flex items-center justify-end gap-2 text-sm">
        <button
          className="rounded border px-2 py-1 disabled:opacity-50"
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page === 1 || q.isFetching}
        >
          ← Prev
        </button>
        <button
          className="rounded border px-2 py-1 disabled:opacity-50"
          onClick={() => setPage((p) => p + 1)}
          disabled={
            q.isFetching ||
            !q.data ||
            q.data.items.length < PAGE_SIZE
          }
        >
          Next →
        </button>
      </footer>
    </div>
  );
}
