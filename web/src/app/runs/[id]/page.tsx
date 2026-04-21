"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect } from "react";
import { ApiError, api } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { useRunStream } from "@/lib/useRunStream";
import { useQueryClient } from "@tanstack/react-query";

const TERMINAL = new Set(["SUCCESS", "SUCCESS_WITH_WARNINGS", "ERROR"]);

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";
  const qc = useQueryClient();

  // Open WS stream — when connected, polling backs off to a long interval.
  const stream = useRunStream(id || null);

  const q = useQuery({
    queryKey: ["run", id],
    queryFn: () => api.getRun(id),
    enabled: !!id,
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      if (s && TERMINAL.has(s)) return false;
      // WS is the primary feed; poll slowly as belt-and-braces.
      return stream.connected ? 15_000 : 2_000;
    },
  });

  // Whenever the WS reports a status change, force a re-fetch of the detail
  // so the payload + linked SiteModel update too.
  useEffect(() => {
    if (!id || !stream.lastStatus) return;
    qc.invalidateQueries({ queryKey: ["run", id] });
  }, [id, stream.lastStatus, qc]);

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
          <LiveIndicator connected={stream.connected} />
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

function LiveIndicator({ connected }: { connected: boolean }) {
  return (
    <span
      className={
        "inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide " +
        (connected
          ? "bg-emerald-50 text-emerald-700"
          : "bg-zinc-100 text-zinc-500")
      }
      title={connected ? "WebSocket connected" : "Polling"}
    >
      <span
        className={
          "h-1.5 w-1.5 rounded-full " +
          (connected ? "bg-emerald-500" : "bg-zinc-400")
        }
      />
      {connected ? "live" : "polling"}
    </span>
  );
}
