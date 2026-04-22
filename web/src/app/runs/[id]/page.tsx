"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
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
    return <p className="mx-auto max-w-6xl px-6 py-6 text-sm text-zinc-500">Loading…</p>;
  }

  if (q.isError) {
    const err = q.error as ApiError | Error;
    const env = err instanceof ApiError ? err.envelope : null;
    return (
      <div className="mx-auto max-w-6xl px-6 py-6">
      <div className="rounded border border-status-error/30 bg-red-50 p-4 text-sm">
        <p className="font-medium text-status-error">
          {env?.error_code || "Error"}: {env?.message || err.message}
        </p>
        <Link href="/runs" className="mt-2 inline-block text-xs underline">
          ← Back to runs
        </Link>
      </div>
      </div>
    );
  }

  const r = q.data!;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-6">
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
          <Json value={r.input_payload} maxHeight={320} />
        </Card>
        <Card title="Output payload (raw)">
          {Object.keys(r.output_payload || {}).length === 0 ? (
            <p className="text-sm text-zinc-400">— pending —</p>
          ) : (
            <CollapsibleJson value={r.output_payload} maxHeight={320} />
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

      <ParseResultSections detail={r} />

      <LLMEnrichmentSections detail={r} />

      <Card title="Linked SiteModel">
        {r.site_model_id ? (
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-zinc-500">site_model_id</dt>
            <dd className="font-mono">{r.site_model_id}</dd>
            <dt className="text-zinc-500">geometry_integrity_score</dt>
            <dd>{r.geometry_integrity_score?.toFixed(3) ?? "—"}</dd>
            <dt className="text-zinc-500">assets</dt>
            <dd>{r.site_model_assets_count}</dd>
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

// ── Parse-result sections ────────────────────────────────────────────────

function ParseResultSections({ detail }: { detail: import("@/lib/types").RunDetail }) {
  const out = (detail.output_payload || {}) as Record<string, any>;
  const fp = out.fingerprint || {};
  const summary = out.summary || {};
  const semantics = out.semantics || {};
  const quality = out.quality || {};
  const stats = detail.site_model_statistics || {};

  const hasAny =
    Object.keys(fp).length > 0 ||
    Object.keys(summary).length > 0 ||
    Object.keys(semantics).length > 0 ||
    Object.keys(quality).length > 0;
  if (!hasAny) return null;

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {/* 1. Fingerprint */}
      <Card title="① 文件指纹与格式确认">
        <KV
          rows={[
            ["filename", fp.filename],
            ["detected_format", fp.detected_format],
            ["size_bytes", fmtBytes(fp.size_bytes)],
            ["sha256", short(fp.sha256, 16)],
            ["units", summary.units],
            ["dxf_version", summary.dxf_version],
            ["schema (IFC/STEP)", summary.schema],
          ]}
        />
      </Card>

      {/* 2. Summary */}
      <Card title="② 解析摘要 (counts / bbox)">
        <KV
          rows={[
            ["entity_total", summary.entity_total ?? 0],
            ["layer_count", summary.layer_count ?? 0],
            ["block_definition_count", summary.block_definition_count ?? 0],
            [
              "bounding_box",
              summary.bounding_box
                ? `min=[${summary.bounding_box.min?.join(", ")}]  max=[${summary.bounding_box.max?.join(", ")}]`
                : "—",
            ],
          ]}
        />
        {summary.entity_counts && Object.keys(summary.entity_counts).length > 0 && (
          <details className="mt-3">
            <summary className="cursor-pointer text-xs text-zinc-500">
              entity_counts ({Object.keys(summary.entity_counts).length} kinds)
            </summary>
            <Json value={summary.entity_counts} />
          </details>
        )}
        {summary.layer_names && summary.layer_names.length > 0 && (
          <details className="mt-2">
            <summary className="cursor-pointer text-xs text-zinc-500">
              layer_names (first {summary.layer_names.length})
            </summary>
            <ul className="mt-1 max-h-48 overflow-auto text-xs font-mono text-zinc-700">
              {summary.layer_names.map((n: string) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </details>
        )}
      </Card>

      {/* 3. Semantics */}
      <Card title="③ 语义抽取结果 (taxonomy + quarantine)">
        <KV
          rows={[
            ["matched_terms_count", semantics.matched_terms_count ?? 0],
            ["quarantine_terms_count", semantics.quarantine_terms_count ?? 0],
            ["linked_site_model_id", semantics.linked_site_model_id ?? "—"],
            ["candidate_count", out.semantics_counts?.candidate_count ?? 0],
          ]}
        />
        {Array.isArray(semantics.matched_terms) && semantics.matched_terms.length > 0 && (
          <details className="mt-3" open>
            <summary className="cursor-pointer text-xs text-zinc-500">
              matched_terms ({semantics.matched_terms.length})
            </summary>
            <table className="mt-2 w-full text-xs">
              <thead className="text-left text-zinc-500">
                <tr>
                  <th className="py-1 pr-2">term</th>
                  <th className="py-1 pr-2">asset_type</th>
                  <th className="py-1 pr-2">count</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {semantics.matched_terms.slice(0, 30).map((t: any, i: number) => (
                  <tr key={i} className="border-t">
                    <td className="py-1 pr-2">{t.term_display}</td>
                    <td className="py-1 pr-2">{t.asset_type}</td>
                    <td className="py-1 pr-2">{t.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        )}
      </Card>

      {/* 4. Quality */}
      <Card title="④ 质量与可追溯性">
        <KV
          rows={[
            ["confidence_score", quality.confidence_score ?? "—"],
            ["warnings", (quality.parse_warnings || []).length],
            ["artifacts", Object.keys(quality.artifacts || {}).length],
          ]}
        />
        {Array.isArray(quality.parse_warnings) && quality.parse_warnings.length > 0 && (
          <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-amber-700">
            {quality.parse_warnings.map((w: string, i: number) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        )}
        {stats && Object.keys(stats).length > 0 && (
          <details className="mt-3">
            <summary className="cursor-pointer text-xs text-zinc-500">
              site_model.statistics
            </summary>
            <Json value={stats} />
          </details>
        )}
      </Card>
    </div>
  );
}

function KV({ rows }: { rows: Array<[string, unknown]> }) {
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
      {rows.map(([k, v]) => (
        <Row key={k} k={k} v={v} />
      ))}
    </dl>
  );
}
function Row({ k, v }: { k: string; v: unknown }) {
  const display =
    v === null || v === undefined || v === ""
      ? "—"
      : typeof v === "object"
      ? JSON.stringify(v)
      : String(v);
  return (
    <>
      <dt className="text-zinc-500">{k}</dt>
      <dd className="font-mono break-all">{display}</dd>
    </>
  );
}
function fmtBytes(n: unknown): string {
  if (typeof n !== "number") return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KiB`;
  return `${(n / 1024 / 1024).toFixed(2)} MiB`;
}
function short(s: unknown, n: number): string {
  if (typeof s !== "string") return "—";
  return s.length <= n ? s : `${s.slice(0, n)}…`;
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

function Json({ value, maxHeight }: { value: unknown; maxHeight?: number }) {
  const style = maxHeight ? { maxHeight: `${maxHeight}px` } : undefined;
  return (
    <pre
      className="overflow-auto rounded bg-zinc-50 p-3 text-xs text-zinc-700"
      style={style}
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function CollapsibleJson({
  value,
  maxHeight = 320,
}: {
  value: unknown;
  maxHeight?: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const text = JSON.stringify(value, null, 2);
  const lineCount = text.split("\n").length;
  const sizeKb = (new Blob([text]).size / 1024).toFixed(1);
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-[11px] text-zinc-500">
        <span>
          {lineCount.toLocaleString()} lines · {sizeKb} KB
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="rounded border border-zinc-300 px-2 py-0.5 text-[11px] text-zinc-600 hover:bg-zinc-100"
          >
            {expanded ? "Collapse" : "Expand"}
          </button>
          <button
            type="button"
            onClick={() => {
              void navigator.clipboard?.writeText(text);
            }}
            className="rounded border border-zinc-300 px-2 py-0.5 text-[11px] text-zinc-600 hover:bg-zinc-100"
          >
            Copy
          </button>
        </div>
      </div>
      <pre
        className="overflow-auto rounded bg-zinc-50 p-3 text-xs text-zinc-700"
        style={{ maxHeight: expanded ? "none" : `${maxHeight}px` }}
      >
        {text}
      </pre>
    </div>
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

// ── LLM Enrichment ─────────────────────────────────────────────────────

type StepKey =
  | "A_normalize"
  | "B_softmatch"
  | "C_arbiter"
  | "D_cluster_proposals"
  | "E_block_kind"
  | "F_quality_breakdown"
  | "G_root_cause"
  | "H_audit_narrative"
  | "I_self_check"
  | "J_site_describe"
  | "K_asset_extract"
  | "L_geom_anomaly"
  | "M_provenance_note";

type CapKind = "embedding" | "text-gen" | "rule" | "hybrid";

interface StepMeta {
  letter: string;
  short: string;
  stage: 1 | 2 | 3 | 4 | 5;
  cap: CapKind;
  capability: string; // 调用的 LLM 能力 / 推理类型
  signature: string; // model / prompt_version 或 rule 标识
  prompt?: string; // 简要 prompt 草图（hover/details）
}

const STEP_META: Record<StepKey, StepMeta> = {
  // ── Stage 1：候选准备（把脏字符串变干净的可比较 token）
  A_normalize: {
    letter: "A",
    short: "Normalize",
    stage: 1,
    cap: "rule",
    capability: "Lexicon + Regex 归一",
    signature: "rule:lex_v1",
    prompt: "去 $lead$ / 尾随数字 / 多语种词典映射（zh/de → en）",
  },
  E_block_kind: {
    letter: "E",
    short: "Block Kind",
    stage: 1,
    cap: "rule",
    capability: "正则级联分类",
    signature: "rule:block_kind_v1",
    prompt: "9 类启发式：autocad_internal / hatch / centermark / ...",
  },

  // ── Stage 2：语义对齐（embedding 召回 + 阈值仲裁）
  B_softmatch: {
    letter: "B",
    short: "Softmatch",
    stage: 2,
    cap: "embedding",
    capability: "Embedding 余弦近邻 → gold",
    signature: "embed:stub-64d (LLM_PROVIDER 可切 OpenAI/Cohere)",
    prompt: "embed(candidate) · cosine(top-k gold) → {accept≥0.86, review≥0.65, reject}",
  },
  C_arbiter: {
    letter: "C",
    short: "Arbiter",
    stage: 2,
    cap: "rule",
    capability: "阈值仲裁聚合",
    signature: "rule:arbiter_v1",
    prompt: "汇总 verdict 计数 → review_queue / promotion_candidates",
  },

  // ── Stage 3：提案生成（embedding 聚类 + 资产抽取）
  D_cluster_proposals: {
    letter: "D",
    short: "Cluster Proposals",
    stage: 3,
    cap: "hybrid",
    capability: "Embedding 聚类 + (可选) LLM 命名",
    signature: "embed:stub-64d → llm:chat (待接)",
    prompt: "single-link 聚类 quarantine → 每簇推荐 suggested_term + asset_type_hint",
  },
  K_asset_extract: {
    letter: "K",
    short: "Asset Extract",
    stage: 3,
    cap: "rule",
    capability: "种子抽取 stub（M3 接 LLM JSON-mode）",
    signature: "rule:seed_v1",
    prompt: "matched_terms ∪ INSERT block 名 → asset 列表 + coverage 缺口",
  },

  // ── Stage 4：质量与诊断（规则 + 阈值，结果驱动 H 叙述）
  F_quality_breakdown: {
    letter: "F",
    short: "Quality Breakdown",
    stage: 4,
    cap: "rule",
    capability: "加权评分公式",
    signature: "rule:quality_v1 (0.4·parse + 0.3·semantic + 0.3·integrity)",
  },
  G_root_cause: {
    letter: "G",
    short: "Root Cause",
    stage: 4,
    cap: "rule",
    capability: "Warning 模式 → owner / fix",
    signature: "rule:root_cause_v1",
  },
  L_geom_anomaly: {
    letter: "L",
    short: "Geom Anomaly",
    stage: 4,
    cap: "rule",
    capability: "几何启发式",
    signature: "rule:geom_v1 (bbox / z-extent / mm-scale)",
  },
  I_self_check: {
    letter: "I",
    short: "Self Check",
    stage: 4,
    cap: "rule",
    capability: "阻断阈值检查",
    signature: "rule:self_check_v1",
    prompt: "quality<0.3 / match<1‰ / parser unavailable → BLOCK",
  },

  // ── Stage 5：叙述与画像（chat-LLM 落地点，当前 stub 模板）
  J_site_describe: {
    letter: "J",
    short: "Site Describe",
    stage: 5,
    cap: "text-gen",
    capability: "Chat-LLM 命名 / 打标（当前 stub 模板）",
    signature: "stub:site_v1 → llm:chat (json_object) 待接",
    prompt: "input: {filename, units, bbox, layer 关键词} → {title, description, tags[]}",
  },
  M_provenance_note: {
    letter: "M",
    short: "Provenance",
    stage: 5,
    cap: "rule",
    capability: "DXF 版本 + 多语种检测",
    signature: "rule:provenance_v1",
    prompt: "AC1018 → AutoCAD 2004；layer_names 字符集 → zh/de/en/...",
  },
  H_audit_narrative: {
    letter: "H",
    short: "Audit Narrative",
    stage: 5,
    cap: "text-gen",
    capability: "Chat-LLM 文本合成（当前 stub 模板）",
    signature: "stub:narrative_v1 → llm:chat 待接",
    prompt: "cited_fields 拼接为审计稿；接 LLM 后改为 strict-cite 摘要",
  },
};

const STAGE_DEFS: Record<
  number,
  { id: number; title: string; subtitle: string; color: string; ring: string }
> = {
  1: { id: 1, title: "候选准备", subtitle: "Preparation", color: "bg-sky-50 text-sky-800", ring: "ring-sky-200" },
  2: { id: 2, title: "语义对齐", subtitle: "Semantic Alignment", color: "bg-indigo-50 text-indigo-800", ring: "ring-indigo-200" },
  3: { id: 3, title: "提案生成", subtitle: "Proposal Generation", color: "bg-violet-50 text-violet-800", ring: "ring-violet-200" },
  4: { id: 4, title: "质量诊断", subtitle: "Quality & Diagnosis", color: "bg-amber-50 text-amber-800", ring: "ring-amber-200" },
  5: { id: 5, title: "叙述与画像", subtitle: "Narrative & Profile", color: "bg-emerald-50 text-emerald-800", ring: "ring-emerald-200" },
};

const CAP_STYLE: Record<CapKind, { label: string; short: string; cls: string }> = {
  embedding: { label: "embedding", short: "EMB", cls: "bg-indigo-100 text-indigo-800" },
  "text-gen": { label: "chat-LLM", short: "LLM", cls: "bg-emerald-100 text-emerald-800" },
  rule: { label: "rule", short: "RUL", cls: "bg-zinc-100 text-zinc-700" },
  hybrid: { label: "hybrid", short: "HYB", cls: "bg-violet-100 text-violet-800" },
};

function CapabilityBadge({ step }: { step: StepKey }) {
  const m = STEP_META[step];
  const cap = CAP_STYLE[m.cap];
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className={"rounded px-1.5 py-0.5 text-[10px] font-semibold " + cap.cls}>
        {cap.label}
      </span>
      <span
        title={m.prompt || ""}
        className="rounded border border-zinc-200 bg-white px-1.5 py-0.5 font-mono text-[10px] text-zinc-600"
      >
        {m.signature}
      </span>
    </div>
  );
}

function StepCard({
  step,
  timingMs,
  hasError,
  children,
}: {
  step: StepKey;
  timingMs?: number;
  hasError?: boolean;
  children: React.ReactNode;
}) {
  const m = STEP_META[step];
  const stage = STAGE_DEFS[m.stage];
  return (
    <div className={"flex flex-col rounded-lg border bg-white p-4 shadow-sm ring-1 " + stage.ring}>
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={"rounded px-1.5 py-0.5 text-[10px] font-bold " + stage.color}>
              S{stage.id}
            </span>
            <h3 className="truncate text-sm font-semibold">
              <span className="font-mono text-violet-700">{m.letter}.</span> {m.short}
            </h3>
            {hasError && (
              <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-700">
                ERR
              </span>
            )}
          </div>
          <p className="mt-0.5 text-[11px] text-zinc-500">{m.capability}</p>
        </div>
        <div className="shrink-0 text-right">
          {typeof timingMs === "number" && (
            <div className="font-mono text-[10px] text-zinc-400">{timingMs} ms</div>
          )}
        </div>
      </div>
      <div className="mb-2">
        <CapabilityBadge step={step} />
      </div>
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  );
}

function BusinessNarrative({ s }: { s: any }) {
  // —— 把机器结果翻译成"小学生也能懂"的三段话 ——
  const J = s.J_site_describe || {};
  const F = s.F_quality_breakdown || {};
  const I = s.I_self_check || {};
  const D = s.D_cluster_proposals || {};
  const G = s.G_root_cause || {};
  const M = s.M_provenance_note || {};

  const title: string = J.title || "（暂无站点画像）";
  const overall: number = typeof F.overall === "number" ? F.overall : 0;
  const semantic: number = typeof F.semantic === "number" ? F.semantic : 0;
  const blocked: boolean = !!I.should_block;

  const inputN: number = D?.stats?.input ?? 0;
  const shownN: number = D?.stats?.shown ?? 0;
  const compress: string = D?.stats?.compression_ratio ? `${D.stats.compression_ratio}×` : "—";

  const verdict =
    overall >= 0.8 && !blocked
      ? { tone: "ok", label: "可放行", cls: "bg-emerald-100 text-emerald-800 ring-emerald-300" }
      : blocked
      ? { tone: "block", label: "需人工介入", cls: "bg-red-100 text-red-800 ring-red-300" }
      : { tone: "review", label: "建议复核", cls: "bg-amber-100 text-amber-800 ring-amber-300" };

  // —— 行动清单：根据结果生成"你现在该做什么" ——
  const actions: { icon: string; text: string }[] = [];
  if (shownN > 0) {
    actions.push({
      icon: "→",
      text: `打开下方 Stage 3 的提案表，给前 ${Math.min(shownN, 30)} 条 AI 聚类提案打 ✓ / ✗（一次能消化 ${inputN} 个原始未知词）`,
    });
  }
  if (semantic < 0.05 && inputN > 100) {
    actions.push({
      icon: "→",
      text: "术语词典命中率几乎为零 → 多半是词典还没覆盖这家工厂；批量审完提案后点 Promote 写回词典，下一份图就会自动认出来",
    });
  }
  if ((G.root_causes || []).length > 0) {
    const owners = Array.from(
      new Set((G.root_causes || []).map((rc: any) => rc.owner).filter(Boolean)),
    );
    if (owners.length > 0) {
      actions.push({
        icon: "→",
        text: `Stage 4 给出了根因 → 该找的人：${owners.join(" / ")}`,
      });
    }
  }
  if (M.multi_team_source) {
    actions.push({
      icon: "→",
      text: "图层名混杂多种语言 → 这张图来自多团队/多供应商，命名规范分歧大，复核时请优先看 D 表里 total_count 较高的簇",
    });
  }
  if (actions.length === 0) {
    actions.push({ icon: "✓", text: "没有需要立刻处理的待办，可继续浏览下方明细。" });
  }

  return (
    <div className="rounded-lg border-2 border-violet-300 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center gap-3">
        <span className="rounded-full bg-violet-600 px-2 py-0.5 text-[10px] font-bold uppercase text-white">
          人话版
        </span>
        <h3 className="text-base font-semibold">这一次跑了什么 · 为什么 · 你该做什么</h3>
        <span
          className={
            "ml-auto rounded-full px-3 py-1 text-xs font-semibold ring-1 " + verdict.cls
          }
        >
          总判定：{verdict.label}
        </span>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        {/* WHAT */}
        <div className="rounded border border-zinc-200 bg-zinc-50 p-3">
          <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-zinc-500">
            ① 刚刚发生了什么
          </div>
          <p className="text-sm leading-relaxed text-zinc-700">
            系统打开了你上传的 CAD 图纸，认出来这是
            <span className="font-semibold text-violet-700"> {title}</span>
            。然后挨个检查里面的图层名 / 块名，跟工厂术语词典对比，把"认识的"自动入库，"不认识的"
            <span className="font-semibold text-violet-700">
              {" "}
              聚成 {shownN} 条提案（压缩 {compress}）
            </span>
            等你审。
          </p>
        </div>

        {/* WHY */}
        <div className="rounded border border-zinc-200 bg-zinc-50 p-3">
          <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-zinc-500">
            ② 为什么要做这些
          </div>
          <ul className="list-disc space-y-1 pl-4 text-sm leading-relaxed text-zinc-700">
            <li>
              CAD 图层名常年是
              <strong className="text-zinc-900">"中英德混打 + 工具自动生成的乱码"</strong>
              ，原样进数据库等于没有。
            </li>
            <li>
              直接让人审 {inputN} 条太累 → 用 embedding
              <strong className="text-zinc-900">把相似的归一成几十簇</strong>
              ，人审一簇 = 标完上百条。
            </li>
            <li>
              同一份图既要给"是否可以下游计算"打分（机器决策），也要给一段
              <strong className="text-zinc-900">人能复核的解释</strong>
              （审计可追溯）。
            </li>
          </ul>
        </div>

        {/* NEXT */}
        <div className="rounded border-2 border-violet-200 bg-violet-50 p-3">
          <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-violet-700">
            ③ 你下一步该做什么
          </div>
          <ul className="space-y-1.5 text-sm leading-relaxed text-zinc-800">
            {actions.map((a, i) => (
              <li key={i} className="flex gap-2">
                <span className="shrink-0">{a.icon}</span>
                <span>{a.text}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-zinc-100 pt-2 text-[11px] text-zinc-500">
        <span>总分</span>
        <span className="font-mono font-semibold text-zinc-700">
          {overall.toFixed(2)}
        </span>
        <span>·</span>
        <span>词典命中率</span>
        <span className="font-mono font-semibold text-zinc-700">
          {(semantic * 100).toFixed(1)}%
        </span>
        <span>·</span>
        <span>是否阻断下游</span>
        <span
          className={
            "rounded px-1.5 font-mono font-semibold " +
            (blocked ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700")
          }
        >
          {blocked ? "BLOCK" : "OK"}
        </span>
        <span className="ml-auto italic text-zinc-400">
          下方 5 阶段流程图 = 拆解；想看机器在每一步具体做了什么，往下滚 ↓
        </span>
      </div>
    </div>
  );
}

function PipelineOverview({
  ran,
  errs,
  timings,
}: {
  ran: string[];
  errs: Record<string, string>;
  timings: Record<string, number>;
}) {
  const ranSet = new Set(ran);
  const stages = [1, 2, 3, 4, 5] as const;
  return (
    <div className="rounded-lg border border-violet-200 bg-gradient-to-br from-violet-50 to-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-violet-700">
          Pipeline 总览（5 阶段 · 13 步）
        </h3>
        <span className="text-[11px] text-zinc-500">
          steps_run = {ran.length}/13 · errors = {Object.keys(errs).length} · total ={" "}
          {Object.values(timings).reduce((a, b) => a + (b || 0), 0)} ms
        </span>
      </div>
      <div className="grid gap-2 md:grid-cols-5">
        {stages.map((sid, idx) => {
          const stage = STAGE_DEFS[sid];
          const steps = (Object.keys(STEP_META) as StepKey[]).filter(
            (k) => STEP_META[k].stage === sid,
          );
          return (
            <div key={sid} className="relative">
              <div className={"rounded-lg p-3 ring-1 " + stage.color + " " + stage.ring}>
                <div className="flex items-center justify-between">
                  <div className="text-[10px] font-semibold uppercase tracking-wide opacity-80">
                    Stage {sid}
                  </div>
                  <div className="text-[9px] opacity-60">{stage.subtitle}</div>
                </div>
                <div className="mt-1 text-sm font-semibold">{stage.title}</div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {steps.map((k) => {
                    const m = STEP_META[k];
                    const did = ranSet.has(k);
                    const err = !!errs[k];
                    const cap = CAP_STYLE[m.cap];
                    return (
                      <a
                        key={k}
                        href={"#step-" + k}
                        title={`${m.short}\n${m.capability}\n${m.signature}`}
                        className={
                          "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-mono text-[10px] transition " +
                          (err
                            ? "border-red-400 bg-red-50 text-red-700"
                            : did
                            ? "border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-100"
                            : "border-dashed border-zinc-300 bg-white/50 text-zinc-400")
                        }
                      >
                        <span className="font-bold">{m.letter}</span>
                        <span className={"rounded px-1 text-[9px] " + cap.cls}>
                          {cap.short}
                        </span>
                      </a>
                    );
                  })}
                </div>
              </div>
              {idx < stages.length - 1 && (
                <div className="absolute right-0 top-1/2 hidden -translate-y-1/2 translate-x-1/2 text-violet-400 md:block">
                  →
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-violet-100 pt-2 text-[10px] text-zinc-500">
        <span className="font-semibold text-zinc-600">能力图例：</span>
        <span className={"rounded px-1.5 py-0.5 " + CAP_STYLE.embedding.cls}>
          {CAP_STYLE.embedding.label}
        </span>
        <span className={"rounded px-1.5 py-0.5 " + CAP_STYLE["text-gen"].cls}>
          {CAP_STYLE["text-gen"].label}
        </span>
        <span className={"rounded px-1.5 py-0.5 " + CAP_STYLE.hybrid.cls}>
          {CAP_STYLE.hybrid.label}
        </span>
        <span className={"rounded px-1.5 py-0.5 " + CAP_STYLE.rule.cls}>
          {CAP_STYLE.rule.label}
        </span>
        <span className="ml-auto italic">
          签名格式 <code className="font-mono">embed:* / llm:* / rule:*</code>，stub 走离线确定算法，可经
          <code className="font-mono">LLM_PROVIDER</code> 切换为真实模型。
        </span>
      </div>
    </div>
  );
}

function LLMEnrichmentSections({ detail }: { detail: import("@/lib/types").RunDetail }) {
  const out = (detail.output_payload || {}) as Record<string, any>;
  const enr = out.llm_enrichment as import("@/lib/types").LLMEnrichment | undefined;
  if (!enr || !enr.sections) return null;
  const s = enr.sections;

  const ran = enr.steps_run || [];
  const errs = (enr.errors || {}) as Record<string, string>;
  const timings = (enr.timings_ms || {}) as Record<string, number>;

  return (
    <section className="flex flex-col gap-4">
      <header className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-violet-700">
          ⑤ LLM 富化与可解释性
        </h2>
        <span className="text-xs text-zinc-500">
          {ran.length} steps · {Object.keys(errs).length} errors ·{" "}
          {Object.values(timings).reduce((a, b) => a + (b || 0), 0)} ms
        </span>
      </header>

      <BusinessNarrative s={s} />

      <PipelineOverview ran={ran} errs={errs} timings={timings} />

      {/* ───── Stage 5 顶置：J 站点画像作为入口 banner ───── */}
      <h3 id="stage-5-top" className="text-xs font-semibold uppercase tracking-wide text-emerald-700">
        Stage 5 · 叙述与画像
        <span className="ml-2 font-normal normal-case text-zinc-500">
          — 把这张图变成一段人能读的话 + 自动起标题/打标签
        </span>
      </h3>
      {s.J_site_describe && (
        <div id="step-J_site_describe">
          <StepCard
            step="J_site_describe"
            timingMs={timings["J_site_describe"]}
            hasError={!!errs["J_site_describe"]}
          >
            <p className="text-base font-medium">{s.J_site_describe.title}</p>
            <p className="mt-1 text-sm text-zinc-600">{s.J_site_describe.description}</p>
            {s.J_site_describe.suggested_tags?.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {s.J_site_describe.suggested_tags.map((t: string) => (
                  <span key={t} className="rounded bg-violet-50 px-2 py-0.5 text-xs text-violet-700">
                    #{t}
                  </span>
                ))}
              </div>
            )}
          </StepCard>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {s.H_audit_narrative && (
          <div id="step-H_audit_narrative">
            <StepCard
              step="H_audit_narrative"
              timingMs={timings["H_audit_narrative"]}
              hasError={!!errs["H_audit_narrative"]}
            >
              <p className="text-sm leading-relaxed">{s.H_audit_narrative.narrative}</p>
              <details className="mt-2">
                <summary className="cursor-pointer text-xs text-zinc-500">
                  cited fields ({s.H_audit_narrative.cited_fields?.length ?? 0})
                </summary>
                <ul className="mt-1 list-disc pl-5 text-xs font-mono text-zinc-600">
                  {(s.H_audit_narrative.cited_fields || []).map((c: string) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </details>
            </StepCard>
          </div>
        )}
        {s.M_provenance_note && (
          <div id="step-M_provenance_note">
            <StepCard
              step="M_provenance_note"
              timingMs={timings["M_provenance_note"]}
              hasError={!!errs["M_provenance_note"]}
            >
              <p className="text-sm">{s.M_provenance_note.note}</p>
              <KV
                rows={[
                  ["release", s.M_provenance_note.release],
                  ["languages", (s.M_provenance_note.languages || []).join(", ") || "—"],
                  ["multi_team_source", s.M_provenance_note.multi_team_source ? "yes" : "no"],
                ]}
              />
            </StepCard>
          </div>
        )}
      </div>

      {/* ───── Stage 4 · 质量诊断 ───── */}
      <h3 className="mt-2 text-xs font-semibold uppercase tracking-wide text-amber-700">
        Stage 4 · 质量与诊断
        <span className="ml-2 font-normal normal-case text-zinc-500">
          — 这次解析靠谱吗？能不能直接给下游用？哪里坏了、谁来修？
        </span>
      </h3>
      <div className="grid gap-4 md:grid-cols-2">
        {s.F_quality_breakdown && (
          <div id="step-F_quality_breakdown">
            <StepCard
              step="F_quality_breakdown"
              timingMs={timings["F_quality_breakdown"]}
              hasError={!!errs["F_quality_breakdown"]}
            >
              <div className="grid grid-cols-4 gap-2 text-center">
                <ScoreCell label="parse" v={s.F_quality_breakdown.parse} />
                <ScoreCell label="semantic" v={s.F_quality_breakdown.semantic} />
                <ScoreCell label="integrity" v={s.F_quality_breakdown.integrity} />
                <ScoreCell label="overall" v={s.F_quality_breakdown.overall} highlight />
              </div>
              <p className="mt-3 text-xs text-zinc-600">{s.F_quality_breakdown.why}</p>
            </StepCard>
          </div>
        )}
        {s.I_self_check && (
          <div id="step-I_self_check">
            <StepCard
              step="I_self_check"
              timingMs={timings["I_self_check"]}
              hasError={!!errs["I_self_check"]}
            >
              <div className="flex items-center gap-2">
                <span
                  className={
                    "rounded px-2 py-0.5 text-xs font-semibold " +
                    (s.I_self_check.should_block
                      ? "bg-red-100 text-red-700"
                      : "bg-emerald-100 text-emerald-700")
                  }
                >
                  {s.I_self_check.should_block ? "BLOCK" : "OK"}
                </span>
                <span className="text-xs text-zinc-500">severity: {s.I_self_check.severity}</span>
              </div>
              {s.I_self_check.blockers?.length > 0 && (
                <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-red-700">
                  {s.I_self_check.blockers.map((b: string, i: number) => (
                    <li key={i}>{b}</li>
                  ))}
                </ul>
              )}
              <p className="mt-2 text-xs text-zinc-600">{s.I_self_check.advice}</p>
            </StepCard>
          </div>
        )}
        {s.G_root_cause && (
          <div id="step-G_root_cause">
            <StepCard
              step="G_root_cause"
              timingMs={timings["G_root_cause"]}
              hasError={!!errs["G_root_cause"]}
            >
              {s.G_root_cause.root_causes?.length > 0 ? (
                <ul className="space-y-2 text-xs">
                  {s.G_root_cause.root_causes.map((rc: any, i: number) => (
                    <li key={i} className="rounded border-l-2 border-amber-400 bg-amber-50 p-2">
                      <div className="font-semibold text-amber-800">
                        {rc.root_cause} ({rc.count})
                      </div>
                      <div className="text-amber-700">owner: {rc.owner}</div>
                      <div className="text-amber-700">fix: {rc.fix}</div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-zinc-400">— no warnings —</p>
              )}
              {s.G_root_cause.uncategorized?.length > 0 && (
                <details className="mt-2">
                  <summary className="cursor-pointer text-xs text-zinc-500">
                    uncategorized ({s.G_root_cause.uncategorized.length})
                  </summary>
                  <ul className="mt-1 list-disc pl-5 text-xs text-zinc-600">
                    {s.G_root_cause.uncategorized.map((w: string, i: number) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </details>
              )}
            </StepCard>
          </div>
        )}
        {s.L_geom_anomaly && (
          <div id="step-L_geom_anomaly">
            <StepCard
              step="L_geom_anomaly"
              timingMs={timings["L_geom_anomaly"]}
              hasError={!!errs["L_geom_anomaly"]}
            >
              {s.L_geom_anomaly.findings?.length > 0 ? (
                <ul className="space-y-2 text-xs">
                  {s.L_geom_anomaly.findings.map((f: any, i: number) => (
                    <li key={i} className="rounded border-l-2 border-orange-400 bg-orange-50 p-2">
                      <div className="font-semibold text-orange-800">
                        {f.kind} <span className="text-orange-600">[{f.severity}]</span>
                      </div>
                      <div className="text-orange-700">{f.hypothesis}</div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-zinc-400">— no anomalies —</p>
              )}
            </StepCard>
          </div>
        )}
      </div>

      {/* ───── Stage 3 · 提案生成 ───── */}
      <h3 className="mt-2 text-xs font-semibold uppercase tracking-wide text-violet-700">
        Stage 3 · 提案生成
        <span className="ml-2 font-normal normal-case text-zinc-500">
          — 把上千个不认识的名字打包成几十条「请你审一下」的人审任务
        </span>
      </h3>
      {s.D_cluster_proposals && (
        <div id="step-D_cluster_proposals">
          <StepCard
            step="D_cluster_proposals"
            timingMs={timings["D_cluster_proposals"]}
            hasError={!!errs["D_cluster_proposals"]}
          >
            <p className="mb-3 text-xs text-zinc-500">{s.D_cluster_proposals.rationale}</p>
            <div className="mb-3 grid grid-cols-3 gap-3 text-sm">
              <Stat label="raw quarantine" v={s.D_cluster_proposals.stats?.input ?? 0} />
              <Stat label="proposals shown" v={s.D_cluster_proposals.stats?.shown ?? 0} />
              <Stat
                label="compression"
                v={
                  s.D_cluster_proposals.stats?.compression_ratio
                    ? `${s.D_cluster_proposals.stats.compression_ratio}×`
                    : "—"
                }
              />
            </div>
            <div className="max-h-96 overflow-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-white text-left text-zinc-500">
                  <tr>
                    <th className="py-1 pr-2">cluster</th>
                    <th className="py-1 pr-2">suggested_term</th>
                    <th className="py-1 pr-2">asset_type</th>
                    <th className="py-1 pr-2">members</th>
                    <th className="py-1 pr-2">total_count</th>
                    <th className="py-1 pr-2">examples</th>
                  </tr>
                </thead>
                <tbody>
                  {s.D_cluster_proposals.proposals.slice(0, 30).map((p: any) => (
                    <tr key={p.cluster_id} className="border-t align-top">
                      <td className="py-1 pr-2 font-mono">{p.cluster_id}</td>
                      <td className="py-1 pr-2 font-mono">{p.suggested_term || "—"}</td>
                      <td className="py-1 pr-2">{p.asset_type_hint}</td>
                      <td className="py-1 pr-2">{p.member_count}</td>
                      <td className="py-1 pr-2">{p.total_count}</td>
                      <td className="py-1 pr-2 font-mono text-zinc-600">
                        {(p.members || [])
                          .slice(0, 3)
                          .map((m: any) => m.term_display || m.term_normalized)
                          .join(", ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </StepCard>
        </div>
      )}
      {s.K_asset_extract && (
        <div id="step-K_asset_extract">
          <StepCard
            step="K_asset_extract"
            timingMs={timings["K_asset_extract"]}
            hasError={!!errs["K_asset_extract"]}
          >
            <KV
              rows={[
                ["extracted", s.K_asset_extract.stats?.extracted ?? 0],
                ["block_inserts", s.K_asset_extract.stats?.block_inserts_in_drawing ?? 0],
                ["coverage_ratio", s.K_asset_extract.stats?.coverage_ratio ?? "—"],
              ]}
            />
            <p className="mt-2 text-xs text-zinc-600">{s.K_asset_extract.rationale}</p>
            {s.K_asset_extract.backlog?.length > 0 && (
              <ul className="mt-2 list-disc pl-5 text-xs text-zinc-500">
                {s.K_asset_extract.backlog.map((b: string, i: number) => (
                  <li key={i}>{b}</li>
                ))}
              </ul>
            )}
          </StepCard>
        </div>
      )}

      {/* ───── Stage 2 · 语义对齐 ───── */}
      <h3 className="mt-2 text-xs font-semibold uppercase tracking-wide text-indigo-700">
        Stage 2 · 语义对齐
        <span className="ml-2 font-normal normal-case text-zinc-500">
          — 图里的词长得跟标准词典像不像？像就直接收，差不多就丢人审
        </span>
      </h3>
      <div className="grid gap-4 md:grid-cols-2">
        {s.B_softmatch && (
          <div id="step-B_softmatch">
            <StepCard
              step="B_softmatch"
              timingMs={timings["B_softmatch"]}
              hasError={!!errs["B_softmatch"]}
            >
              <KV
                rows={[
                  ["input", s.B_softmatch.stats?.input ?? 0],
                  ["gold_size", s.B_softmatch.stats?.gold_size ?? 0],
                  ["produced", s.B_softmatch.stats?.produced ?? 0],
                  ["accept_threshold", s.B_softmatch.thresholds?.accept],
                  ["review_threshold", s.B_softmatch.thresholds?.review],
                ]}
              />
              {s.B_softmatch.matches?.length > 0 && (
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs text-zinc-500">
                    top matches ({s.B_softmatch.matches.length})
                  </summary>
                  <div className="mt-2 max-h-72 overflow-auto">
                    <table className="w-full text-xs">
                      <thead className="sticky top-0 bg-white text-left text-zinc-500">
                        <tr>
                          <th>candidate</th>
                          <th>best</th>
                          <th>sim</th>
                          <th>verdict</th>
                        </tr>
                      </thead>
                      <tbody className="font-mono">
                        {s.B_softmatch.matches.slice(0, 20).map((m: any, i: number) => (
                          <tr key={i} className="border-t">
                            <td className="pr-2">{m.candidate}</td>
                            <td className="pr-2">{m.best_match}</td>
                            <td className="pr-2">{m.best_sim}</td>
                            <td className="pr-2">{m.verdict}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              )}
            </StepCard>
          </div>
        )}
        {s.C_arbiter && (
          <div id="step-C_arbiter">
            <StepCard
              step="C_arbiter"
              timingMs={timings["C_arbiter"]}
              hasError={!!errs["C_arbiter"]}
            >
              <KV
                rows={[
                  ["accept", s.C_arbiter.counts?.accept ?? 0],
                  ["review", s.C_arbiter.counts?.review ?? 0],
                  ["reject", s.C_arbiter.counts?.reject ?? 0],
                ]}
              />
              <p className="mt-2 text-xs text-zinc-600">{s.C_arbiter.rationale}</p>
            </StepCard>
          </div>
        )}
      </div>

      {/* ───── Stage 1 · 候选准备 ───── */}
      <h3 className="mt-2 text-xs font-semibold uppercase tracking-wide text-sky-700">
        Stage 1 · 候选准备
        <span className="ml-2 font-normal normal-case text-zinc-500">
          — 把图纸里乱七八糟的字符串洗干净，并初步分类（哪些是工具自动产生的垃圾、哪些是真有意义的图层名）
        </span>
      </h3>
      <div className="grid gap-4 md:grid-cols-2">
        {s.A_normalize && (
          <div id="step-A_normalize">
            <StepCard
              step="A_normalize"
              timingMs={timings["A_normalize"]}
              hasError={!!errs["A_normalize"]}
            >
              <KV
                rows={[
                  ["input", s.A_normalize.stats?.input],
                  ["shown", s.A_normalize.stats?.shown],
                ]}
              />
              <details className="mt-3">
                <summary className="cursor-pointer text-xs text-zinc-500">
                  samples ({s.A_normalize.items?.length ?? 0})
                </summary>
                <div className="mt-2 max-h-72 overflow-auto">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-white text-left text-zinc-500">
                      <tr>
                        <th>original</th>
                        <th>normalized</th>
                        <th>lang</th>
                        <th>reason</th>
                      </tr>
                    </thead>
                    <tbody className="font-mono">
                      {s.A_normalize.items.slice(0, 15).map((it: any, i: number) => (
                        <tr key={i} className="border-t">
                          <td className="pr-2">{it.original}</td>
                          <td className="pr-2">{it.normalized}</td>
                          <td className="pr-2">{it.lang}</td>
                          <td className="pr-2 text-zinc-500">{it.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            </StepCard>
          </div>
        )}
        {s.E_block_kind && (
          <div id="step-E_block_kind">
            <StepCard
              step="E_block_kind"
              timingMs={timings["E_block_kind"]}
              hasError={!!errs["E_block_kind"]}
            >
              <KV
                rows={Object.entries(s.E_block_kind.kind_counts || {}).map(([k, v]) => [k, v])}
              />
              <details className="mt-3">
                <summary className="cursor-pointer text-xs text-zinc-500">
                  items ({s.E_block_kind.items?.length ?? 0})
                </summary>
                <div className="mt-2 max-h-72 overflow-auto">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-white text-left text-zinc-500">
                      <tr>
                        <th>name</th>
                        <th>kind</th>
                        <th>conf</th>
                      </tr>
                    </thead>
                    <tbody className="font-mono">
                      {s.E_block_kind.items.slice(0, 20).map((it: any, i: number) => (
                        <tr key={i} className="border-t">
                          <td className="pr-2">{it.name}</td>
                          <td className="pr-2">{it.kind}</td>
                          <td className="pr-2">{it.confidence}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            </StepCard>
          </div>
        )}
      </div>

      {/* errors / timings */}
      {(Object.keys(errs).length > 0 || Object.keys(timings).length > 0) && (
        <Card title="Pipeline diagnostics">
          {Object.keys(errs).length > 0 && (
            <details open>
              <summary className="cursor-pointer text-xs font-semibold text-red-700">
                errors ({Object.keys(errs).length})
              </summary>
              <Json value={errs} />
            </details>
          )}
          <details className="mt-2">
            <summary className="cursor-pointer text-xs text-zinc-500">
              step timings (ms)
            </summary>
            <Json value={timings} />
          </details>
        </Card>
      )}
    </section>
  );
}

function ScoreCell({ label, v, highlight }: { label: string; v: number; highlight?: boolean }) {
  const pct = Math.max(0, Math.min(1, v ?? 0));
  const color =
    pct >= 0.8 ? "text-emerald-700" : pct >= 0.5 ? "text-amber-700" : "text-red-700";
  return (
    <div
      className={
        "rounded p-2 " +
        (highlight ? "bg-violet-50 ring-1 ring-violet-200" : "bg-zinc-50")
      }
    >
      <div className={"font-mono text-lg " + color}>{(v ?? 0).toFixed(2)}</div>
      <div className="text-[10px] uppercase tracking-wide text-zinc-500">{label}</div>
    </div>
  );
}

function Stat({ label, v }: { label: string; v: any }) {
  return (
    <div className="rounded bg-zinc-50 p-2">
      <div className="font-mono text-lg">{v}</div>
      <div className="text-[10px] uppercase tracking-wide text-zinc-500">{label}</div>
    </div>
  );
}
