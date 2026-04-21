"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ApiError, api } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

const TERMINAL = new Set(["SUCCESS", "SUCCESS_WITH_WARNINGS", "ERROR"]);

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";

  const q = useQuery({
    queryKey: ["run", id],
    queryFn: () => api.getRun(id),
    enabled: !!id,
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s && TERMINAL.has(s) ? false : 2000;
    },
  });

  if (q.isLoading) {
    return <p className="text-sm text-zinc-500">Loading…</p>;
  }

  if (q.isError) {
    const err = q.error as ApiError | Error;
    const env = err instanceof ApiError ? err.envelope : null;
    return (
      <div className="rounded border border-status-error/30 bg-red-50 p-4 text-sm">
        <p className="font-medium text-status-error">
          {env?.error_code || "Error"}: {env?.message || err.message}
        </p>
        <Link href="/runs" className="mt-2 inline-block text-xs underline">
          ← Back to runs
        </Link>
      </div>
    );
  }

  const r = q.data!;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Link href="/runs" className="text-xs text-zinc-500 hover:underline">
          ← Back to runs
        </Link>
        <div className="mt-1 flex items-center gap-3">
          <h1 className="font-mono text-xl">{r.mcp_context_id}</h1>
          <StatusBadge status={r.status} />
        </div>
        <p className="text-xs text-zinc-500">
          {r.agent} · {r.agent_version || "unversioned"} ·{" "}
          {new Date(r.timestamp).toLocaleString()}
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-2">
        <Card title="Input payload">
          <Json value={r.input_payload} />
        </Card>
        <Card title="Output payload">
          {Object.keys(r.output_payload || {}).length === 0 ? (
            <p className="text-sm text-zinc-400">— pending —</p>
          ) : (
            <Json value={r.output_payload} />
          )}
        </Card>
      </section>

      {r.error_message && (
        <Card title="Error">
          <pre className="whitespace-pre-wrap break-words text-sm text-status-error">
            {r.error_message}
          </pre>
        </Card>
      )}

      <Card title="Linked SiteModel">
        {r.site_model_id ? (
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-zinc-500">site_model_id</dt>
            <dd className="font-mono">{r.site_model_id}</dd>
            <dt className="text-zinc-500">geometry_integrity_score</dt>
            <dd>{r.geometry_integrity_score?.toFixed(3) ?? "—"}</dd>
          </dl>
        ) : (
          <p className="text-sm text-zinc-400">— not yet generated —</p>
        )}
      </Card>

      <Card title="Run metadata">
        <dl className="grid grid-cols-2 gap-2 text-sm">
          <dt className="text-zinc-500">latency_ms</dt>
          <dd>{r.latency_ms ?? "—"}</dd>
        </dl>
      </Card>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded border bg-white p-4">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Json({ value }: { value: unknown }) {
  return (
    <pre className="overflow-x-auto rounded bg-zinc-50 p-3 text-xs text-zinc-700">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}
