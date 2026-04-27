"use client";

/**
 * EvaluationPanorama — sticky banner that surfaces the ParseAgent
 * "5 维 / 4 阶 / 4 闸 / 加固清单" framework on top of the S1 workshop.
 *
 * Rendered between `<SiteHeader>` and the three-column grid in
 * `web/src/app/sites/[runId]/page.tsx`. Designed so a reviewer can
 * answer "should I let this run progress to S2?" in ≤ 3 seconds:
 *
 * ┌─ 5 维进度条 ─────────────┬─ 4 闸红绿灯 ┬─ 4 阶硬度 ──┬─ 加固 4 灯 ─┐
 * │ D1 ████░ 0.82  ✓        │ G1 ✓        │ H1 1209     │ subtype ✓   │
 * │ D2 █░░░░ 0.18  ⚠        │ G2 –        │ H2 0        │ link_prec ✗ │
 * │ D3 ─    N/A             │ G3 –        │ H3 0        │ stable_run ✗│
 * │ D4 ████ ✓               │ G4 –        │ H4 0        │ R5 quar.  ⚠ │
 * │ D5 ░░░░ 0.0   ⚠         └─────────────┴─────────────┴─────────────┘
 * └─ 总判定: 🟡 复核 (D2 词典覆盖 < 0.85 + D5 provenance 0%) ──────────┘
 *
 * Data sources (priority order):
 *   1. `run.evaluation`         — populated by GET /dashboard/runs/{id}/eval
 *      once `agents/parse_agent/finalize.py` writes to `run_evaluations`.
 *      This is the *authoritative* source.
 *   2. `run.output_payload.llm_enrichment.sections.F_quality_breakdown`
 *      and `Asset.classifier_kind` distribution — used as a fallback
 *      *derivation* until the finalize hook lands. Always shown with a
 *      small "(派生)" tag so reviewers know the values aren't pinned.
 *   3. Hard-coded defaults / N-A — for fields neither path can fill
 *      (e.g. G2/G3/G4 only land from CI / weekly cron / GA prep).
 *
 * Why the dual-source design: we want to ship the visual component
 * BEFORE wiring up the finalize hook + DB migration so the user can
 * eyeball the layout right away; once the hook lands, exactly the same
 * banner re-renders driven by typed columns instead of JSON.
 */

import { Icon } from "@/components/icons";
import type { LLMEnrichment, RunDetail } from "@/lib/types";

// ─────────────────────────────────────────────────────────────────────
// Public types — mirror `db/alembic/versions/0018_run_evaluations.py`
// ─────────────────────────────────────────────────────────────────────

/** Status of a reinforcement-checklist item. Maps 1:1 to the DB JSONB. */
export type ReinforceStatus = "ok" | "warn" | "fail" | "na";

/**
 * Shape of the `RunDetail.evaluation` payload (added in a follow-up PR
 * once the API route lands). Optional today; the component tolerates
 * its absence and falls back to deriving values from `llm_enrichment`.
 */
export type RunEvaluation = {
  d1_geometry_score: number;
  d2_semantic_score: number;
  d3_topology_score: number | null;
  d4_contract_pass: boolean;
  d5_provenance_score: number;
  g1_schema_pass: boolean;
  g2_gold_score: number | null;
  g3_llm_judge_score: number | null;
  g4_e2e_pass: boolean | null;
  h1_count: number;
  h2_count: number;
  h3_count: number;
  h4_count: number;
  reinforcement: Record<string, ReinforceStatus>;
  overall_score: number;
  should_block: boolean;
  block_reasons: string[] | null;
};

// ─────────────────────────────────────────────────────────────────────
// Derivation: fall back to llm_enrichment when run.evaluation absent
// ─────────────────────────────────────────────────────────────────────

type Derived = {
  eval: RunEvaluation;
  derived: boolean;        // true when DB-pinned values are unavailable
  derivedNote?: string;    // why some fields are gray / "—"
};

/**
 * Best-effort derivation from the JSON blob currently produced by
 * ParseAgent. ALL fields here are conservative — unknown means
 * "show as gray, not red", because today's pipeline simply doesn't
 * compute them yet (rather than failing).
 */
function deriveFromEnrichment(run: RunDetail): Derived {
  const enrich: LLMEnrichment | null =
    ((run.output_payload as any)?.llm_enrichment as LLMEnrichment) || null;
  const F = enrich?.sections.F_quality_breakdown;
  const I = enrich?.sections.I_self_check;

  // D1 ← geometry_integrity_score (already set on RunDetail since 0001).
  const d1 = clamp01(
    typeof run.geometry_integrity_score === "number"
      ? run.geometry_integrity_score
      : (F?.parse ?? 0),
  );
  // D2 ← F.semantic when present, else strict_acc-ish fallback (matched_terms ratio).
  const semantics = (run.output_payload as any)?.semantics;
  const matched = Array.isArray(semantics?.matched_terms) ? semantics.matched_terms.length : 0;
  const quarantined = Array.isArray(semantics?.quarantine) ? semantics.quarantine.length : 0;
  const d2Fallback = matched + quarantined > 0 ? matched / (matched + quarantined) : 0;
  const d2 = clamp01(typeof F?.semantic === "number" ? F.semantic : d2Fallback);

  // D3 ← `link_symmetry` not yet emitted by ParseAgent — leave null.
  const d3 =
    typeof (run.output_payload as any)?.relationships?.link_symmetry === "number"
      ? clamp01((run.output_payload as any).relationships.link_symmetry)
      : null;

  // D4 ← contract pass = "we got a site_model_id and no parser error".
  const d4 = !!run.site_model_id && !run.error_message;

  // D5 ← integrity comes from llm_enrichment if exposed; until the
  // finalize hook lands we can only read whether artifacts exist.
  // F.integrity is currently overloaded as "did artifacts persist", but
  // *not* as "classifier_kind coverage". We surface it as-is and warn.
  const d5 = clamp01(typeof F?.integrity === "number" ? F.integrity : 0);

  // G1 — runtime can answer this immediately.
  const g1 = run.status === "SUCCESS" || run.status === "SUCCESS_WITH_WARNINGS";

  // H1-H4 are unavailable without `Asset.classifier_kind` rolled up. We
  // estimate H1 = total recognised assets (everything starts at "geometry
  // identified"), and leave H2-H4 = 0 with a note. The finalize hook
  // will replace this with the exact distribution.
  const h1 = run.site_model_assets_count ?? 0;

  // Reinforcement: §5 of the framework. Until the finalize hook stamps
  // explicit statuses, we infer the four items conservatively.
  const reinforcement: Record<string, ReinforceStatus> = {
    sub_type_field: "ok", // schema slot exists since 0017
    link_precision: "fail", // not yet emitted
    stable_run_hash: "warn", // drift detector pending
    r5_quarantine_url: "warn", // placeholder URL, no UI yet
  };

  // Overall — weighted blend, conservative (D5 dominates when zero so
  // the user can't accidentally treat a missing-provenance run as green).
  const dWeights = [0.15, 0.4, 0.1, 0.1, 0.25];
  const dValues = [d1, d2, d3 ?? 0.5, d4 ? 1 : 0, d5];
  const overall =
    dWeights.reduce((s, w, i) => s + w * dValues[i], 0) /
    dWeights.reduce((s, w) => s + w, 0);

  const blockReasons: string[] = [];
  if (d2 < 0.5) blockReasons.push(`D2 词典覆盖 ${(d2 * 100).toFixed(0)}% < 50%`);
  if (d5 < 0.5) blockReasons.push(`D5 provenance 覆盖 ${(d5 * 100).toFixed(0)}% < 50%`);
  if (!g1) blockReasons.push(`G1 schema 未通过`);

  const should_block = !!I?.should_block || blockReasons.length > 0;

  return {
    eval: {
      d1_geometry_score: d1,
      d2_semantic_score: d2,
      d3_topology_score: d3,
      d4_contract_pass: d4,
      d5_provenance_score: d5,
      g1_schema_pass: g1,
      g2_gold_score: null,
      g3_llm_judge_score: null,
      g4_e2e_pass: null,
      h1_count: h1,
      h2_count: 0,
      h3_count: 0,
      h4_count: 0,
      reinforcement,
      overall_score: clamp01(overall),
      should_block,
      block_reasons: should_block && blockReasons.length > 0 ? blockReasons : null,
    },
    derived: true,
    derivedNote:
      "评估值由 llm_enrichment + run 字段派生；ParseAgent finalize 上线后由 run_evaluations 表驱动",
  };
}

function clamp01(v: number): number {
  if (Number.isNaN(v) || v == null) return 0;
  return Math.max(0, Math.min(1, v));
}

// ─────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────

export function EvaluationPanorama({ run }: { run: RunDetail }) {
  // Future: prefer `run.evaluation` once the API route lands.
  const explicit = (run as any).evaluation as RunEvaluation | undefined | null;
  const { eval: ev, derived, derivedNote } = explicit
    ? { eval: explicit, derived: false, derivedNote: undefined }
    : deriveFromEnrichment(run);

  const tone = ev.should_block ? "red" : ev.overall_score >= 0.75 ? "emerald" : "amber";
  const verdictLabel = ev.should_block
    ? "🔴 阻断"
    : ev.overall_score >= 0.75
      ? "🟢 可放行"
      : "🟡 建议复核";

  return (
    <div
      className={[
        "border-b bg-white px-4 py-2",
        tone === "red"
          ? "border-red-200 bg-red-50/40"
          : tone === "amber"
            ? "border-amber-200 bg-amber-50/40"
            : "border-emerald-200 bg-emerald-50/40",
      ].join(" ")}
    >
      <div className="grid grid-cols-[1fr_auto_auto_auto] items-stretch gap-4">
        {/* ── 5 维进度条 ─────────────────────────────────── */}
        <div className="flex flex-col gap-1">
          <div className="mb-0.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">
            <Icon name="bar-chart" size={11} /> 5 维评估
            {derived && (
              <span
                className="rounded bg-zinc-200 px-1.5 py-0.5 text-[9px] font-normal normal-case text-zinc-600"
                title={derivedNote}
              >
                派生
              </span>
            )}
          </div>
          <DRow label="D1 几何完整性" value={ev.d1_geometry_score} threshold={0.85} />
          <DRow label="D2 语义命中率" value={ev.d2_semantic_score} threshold={0.85} />
          <DRow
            label="D3 关系/拓扑"
            value={ev.d3_topology_score}
            threshold={0.9}
            naLabel="N/A · ParseAgent v1.0 不出关系"
          />
          <DRow label="D4 输出契约" value={ev.d4_contract_pass ? 1 : 0} threshold={1} binary />
          <DRow label="D5 可追溯" value={ev.d5_provenance_score} threshold={0.9} />
        </div>

        {/* ── 4 GA 闸门红绿灯 ───────────────────────────── */}
        <div className="flex w-[110px] flex-col gap-1 border-l border-zinc-200 pl-4">
          <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">
            4 GA 闸门
          </div>
          <GateLight
            id="G1"
            label="Schema"
            state={ev.g1_schema_pass === true ? "ok" : ev.g1_schema_pass === false ? "fail" : "na"}
            tooltip="每次解析后即点亮 — agent_loader + pydantic 通过即 OK"
          />
          <GateLight
            id="G2"
            label="Gold"
            state={ev.g2_gold_score == null ? "na" : ev.g2_gold_score >= 0.92 ? "ok" : "warn"}
            score={ev.g2_gold_score}
            tooltip="CI per-PR 跑 — strict_acc ≥ 0.92 + recall ≥ 0.85 + range_pass=1.0"
          />
          <GateLight
            id="G3"
            label="LLM-J"
            state={ev.g3_llm_judge_score == null ? "na" : ev.g3_llm_judge_score >= 0.45 ? "ok" : "warn"}
            score={ev.g3_llm_judge_score}
            tooltip="weekly cron — 3-run avg ≥ 0.45 + reject 率 < 5%"
          />
          <GateLight
            id="G4"
            label="E2E"
            state={ev.g4_e2e_pass === true ? "ok" : ev.g4_e2e_pass === false ? "fail" : "na"}
            tooltip="GA prep 前 — Consumer (ConstraintAgent) 全链路 + R5 签字"
          />
        </div>

        {/* ── 4 阶硬度 (H1-H4 计数) ──────────────────────── */}
        <div className="flex w-[120px] flex-col gap-1 border-l border-zinc-200 pl-4">
          <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">
            4 阶硬度
          </div>
          <HCount label="H1 几何识别" count={ev.h1_count} hint="确定性 · 0 LLM" />
          <HCount label="H2 字面量" count={ev.h2_count} hint="rule_block · ≥0.95" />
          <HCount label="H3 消歧" count={ev.h3_count} hint="layer / geom 特征" />
          <HCount label="H4 LLM 兜底" count={ev.h4_count} hint="≤ 0.8 折扣 · 50/file 上限" />
        </div>

        {/* ── 加固清单 (§5 4 项) ─────────────────────────── */}
        <div className="flex w-[130px] flex-col gap-1 border-l border-zinc-200 pl-4">
          <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">
            加固清单
          </div>
          <ReinforceRow
            label="sub_type 字段"
            status={ev.reinforcement.sub_type_field || "na"}
            note="GA 必含占位 — schema 已加 ✓"
          />
          <ReinforceRow
            label="link_precision"
            status={ev.reinforcement.link_precision || "na"}
            note="D3 关系精确率指标 — gold_eval.py 待加"
          />
          <ReinforceRow
            label="stable_run_hash"
            status={ev.reinforcement.stable_run_hash || "na"}
            note="3-run 一致性 — drift_detector 待加"
          />
          <ReinforceRow
            label="R5 quarantine"
            status={ev.reinforcement.r5_quarantine_url || "na"}
            note="Domain Expert 签字界面 — Phase 5"
          />
        </div>
      </div>

      {/* ── 底部：总判定 + block reasons ──────────────────────── */}
      <div className="mt-2 flex items-center justify-between gap-3 border-t border-zinc-200/70 pt-2 text-[11px]">
        <div className="flex items-center gap-2">
          <span
            className={[
              "rounded px-2 py-0.5 font-semibold",
              tone === "red"
                ? "bg-red-100 text-red-700"
                : tone === "amber"
                  ? "bg-amber-100 text-amber-700"
                  : "bg-emerald-100 text-emerald-700",
            ].join(" ")}
          >
            总判定 {verdictLabel}
          </span>
          <span className="text-zinc-500">
            综合 <b className="text-zinc-800">{(ev.overall_score * 100).toFixed(0)}%</b>
          </span>
        </div>
        {ev.block_reasons && ev.block_reasons.length > 0 && (
          <div className="flex flex-1 items-center gap-1.5 truncate text-zinc-600">
            <Icon name="info" size={11} className="text-amber-500" />
            <span className="truncate">{ev.block_reasons.join(" · ")}</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Inner cells
// ─────────────────────────────────────────────────────────────────────

function DRow({
  label,
  value,
  threshold,
  binary,
  naLabel,
}: {
  label: string;
  value: number | null;
  threshold: number;
  binary?: boolean;
  naLabel?: string;
}) {
  if (value == null) {
    return (
      <div className="flex items-center gap-2 text-[11px]">
        <span className="w-[110px] shrink-0 text-zinc-600">{label}</span>
        <span className="flex-1 text-zinc-400">{naLabel || "—"}</span>
      </div>
    );
  }
  const pct = Math.round(value * 100);
  const ok = value >= threshold;
  const warn = !ok && value >= threshold * 0.6;
  const tone = ok ? "emerald" : warn ? "amber" : "red";
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="w-[110px] shrink-0 text-zinc-600">{label}</span>
      <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-zinc-100">
        <div
          className={[
            "absolute inset-y-0 left-0",
            tone === "emerald" ? "bg-emerald-500" : tone === "amber" ? "bg-amber-500" : "bg-red-500",
          ].join(" ")}
          style={{ width: `${pct}%` }}
        />
        {!binary && (
          <div
            className="absolute inset-y-0 w-px bg-zinc-400/70"
            style={{ left: `${threshold * 100}%` }}
            title={`阈值 ${threshold}`}
          />
        )}
      </div>
      <span
        className={[
          "w-12 shrink-0 text-right font-mono",
          tone === "emerald" ? "text-emerald-700" : tone === "amber" ? "text-amber-700" : "text-red-700",
        ].join(" ")}
      >
        {binary ? (ok ? "✓" : "✗") : `${pct}%`}
      </span>
    </div>
  );
}

function GateLight({
  id,
  label,
  state,
  score,
  tooltip,
}: {
  id: string;
  label: string;
  state: "ok" | "warn" | "fail" | "na";
  score?: number | null;
  tooltip: string;
}) {
  const palette: Record<string, string> = {
    ok: "bg-emerald-100 text-emerald-700",
    warn: "bg-amber-100 text-amber-700",
    fail: "bg-red-100 text-red-700",
    na: "bg-zinc-100 text-zinc-400",
  };
  const glyph =
    state === "ok" ? "✓" : state === "warn" ? "⚠" : state === "fail" ? "✗" : "–";
  return (
    <div className="flex items-center gap-1.5 text-[11px]" title={tooltip}>
      <span className={`inline-flex h-4 w-4 items-center justify-center rounded ${palette[state]}`}>
        {glyph}
      </span>
      <span className="text-zinc-700">
        {id} {label}
      </span>
      {score != null && <span className="ml-auto font-mono text-[10px] text-zinc-400">{score.toFixed(2)}</span>}
    </div>
  );
}

function HCount({ label, count, hint }: { label: string; count: number; hint: string }) {
  const tone = count > 0 ? "text-zinc-800" : "text-zinc-400";
  return (
    <div className="flex items-baseline gap-1.5 text-[11px]" title={hint}>
      <span className="flex-1 text-zinc-600">{label}</span>
      <span className={`font-mono font-semibold ${tone}`}>{count}</span>
    </div>
  );
}

function ReinforceRow({
  label,
  status,
  note,
}: {
  label: string;
  status: ReinforceStatus;
  note: string;
}) {
  const palette: Record<ReinforceStatus, { bg: string; glyph: string }> = {
    ok: { bg: "bg-emerald-500", glyph: "✓" },
    warn: { bg: "bg-amber-500", glyph: "!" },
    fail: { bg: "bg-red-500", glyph: "✗" },
    na: { bg: "bg-zinc-300", glyph: "–" },
  };
  const p = palette[status];
  return (
    <div className="flex items-center gap-1.5 text-[11px]" title={note}>
      <span className={`inline-block h-2.5 w-2.5 shrink-0 rounded-full ${p.bg}`} title={p.glyph} />
      <span className="truncate text-zinc-700">{label}</span>
    </div>
  );
}
