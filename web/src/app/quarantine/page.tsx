"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { QuarantineDecision, QuarantineItem } from "@/lib/types";
import { useAuth } from "@/components/AuthProvider";

const STATUS_FILTERS = ["pending", "approve", "reject", "merge", "all"] as const;

export default function QuarantinePage() {
  const { identity } = useAuth();
  const canDecide =
    !!identity && (identity.role === "reviewer" || identity.role === "admin");
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]>("pending");
  const [page, setPage] = useState(1);

  const q = useQuery({
    queryKey: ["dashboard", "quarantine", statusFilter, page],
    queryFn: () => api.listQuarantine({ status: statusFilter, page, pageSize: 20 }),
  });

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Quarantine</h1>
        <div className="flex items-center gap-2 text-xs">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => {
                setStatusFilter(s);
                setPage(1);
              }}
              className={
                "rounded px-2 py-1 capitalize " +
                (statusFilter === s
                  ? "bg-zinc-900 text-white"
                  : "border bg-white hover:bg-zinc-50")
              }
            >
              {s}
            </button>
          ))}
        </div>
      </header>

      {!canDecide && (
        <p className="rounded bg-amber-50 px-3 py-2 text-xs text-amber-800">
          You are signed in as <code>{identity?.role ?? "—"}</code>; only
          reviewers and admins can record decisions.
        </p>
      )}

      {q.isLoading && <p className="text-sm text-zinc-500">Loading…</p>}
      {q.isError && (
        <p className="rounded bg-red-50 px-3 py-2 text-sm text-status-error">
          {(q.error as ApiError | Error).message}
        </p>
      )}

      {q.data && (
        <>
          <p className="text-xs text-zinc-500">
            {q.data.total} item{q.data.total === 1 ? "" : "s"} · page {q.data.page}
          </p>
          <ul className="flex flex-col gap-3">
            {q.data.items.map((it) => (
              <QuarantineRow key={it.id} item={it} canDecide={canDecide} />
            ))}
            {q.data.items.length === 0 && (
              <li className="rounded border bg-white p-4 text-sm text-zinc-400">
                — no items —
              </li>
            )}
          </ul>
          <div className="flex items-center gap-2 text-xs">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="rounded border px-2 py-1 disabled:opacity-40"
            >
              ← prev
            </button>
            <button
              type="button"
              disabled={page * q.data.page_size >= q.data.total}
              onClick={() => setPage((p) => p + 1)}
              className="rounded border px-2 py-1 disabled:opacity-40"
            >
              next →
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function QuarantineRow({
  item,
  canDecide,
}: {
  item: QuarantineItem;
  canDecide: boolean;
}) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const decide = useMutation({
    mutationFn: (decision: QuarantineDecision) =>
      api.decideQuarantine(item.id, { decision, reason: reason || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["dashboard", "quarantine"] });
    },
    onError: (e: unknown) => {
      setError(
        e instanceof ApiError ? e.envelope?.message || e.message : (e as Error).message,
      );
    },
  });

  const decided = item.decision && item.decision !== "pending";

  return (
    <li className="rounded border bg-white p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-sm">{item.term_display}</p>
          <p className="text-xs text-zinc-500">
            {item.asset_type} · seen {item.count}× · last{" "}
            {new Date(item.last_seen).toLocaleString()}
          </p>
          {decided && (
            <p className="mt-1 text-xs text-zinc-500">
              Decided <strong>{item.decision}</strong> by {item.reviewer} at{" "}
              {item.reviewed_at && new Date(item.reviewed_at).toLocaleString()}
            </p>
          )}
        </div>
        {!decided && canDecide && (
          <div className="flex flex-col items-end gap-2">
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="reason (optional)"
              className="w-56 rounded border px-2 py-1 text-xs"
              maxLength={500}
            />
            <div className="flex gap-2">
              <button
                type="button"
                disabled={decide.isPending}
                onClick={() => decide.mutate("approve")}
                className="rounded bg-emerald-600 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
              >
                Approve
              </button>
              <button
                type="button"
                disabled={decide.isPending}
                onClick={() => decide.mutate("reject")}
                className="rounded bg-red-600 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
              >
                Reject
              </button>
            </div>
            {error && <p className="text-xs text-status-error">{error}</p>}
          </div>
        )}
      </div>
    </li>
  );
}
