"use client";

/**
 * RiskPanel — 顶端"风险雷达 + 4 闸门"仪表盘。
 *
 * 设计文档: web/docs/parse_agent_risk_panel_design.md
 * 评估维度: ExcPlan/parse_agent_evaluation_dimensions.md（5 维 D1-D5 / 4 闸 G1-G4）
 *
 * 目标: 让复核者进页面 3 秒之内判断"这次解析能不能放行"。
 *
 * 架构关系:
 *   RiskPanel        —— 仪表盘（量化指标 + 风险定位） ← 本组件
 *   BusinessNarrative —— 新闻稿（自然语言三段话）
 *   ① ② ③ ④ ⑤ 卡    —— 故障诊断（专项明细）
 */

import type { RunDetail, LLMEnrichment } from "@/lib/types";

// ════════════════ 类型 ════════════════

type Tone = "ok" | "warn" | "fail" | "na";

interface DScore {
  key: "D1" | "D2" | "D3" | "D4" | "D5";
  label: string;
  value: number; // 0..1
  display: string; // "0.82" or "—"
  tone: Tone;
  threshold: string; // "≥ 0.85"
  hint: string; // 一句话原因
  anchor: string; // 锚跳 id (#card-...)
}

interface GGate {
  key: "G1" | "G2" | "G3" | "G4";
  label: string;
  tone: Tone;
  triggerHint: string; // tooltip
}

interface RiskItem {
  rank: number;
  text: string;
  tone: Tone;
}

// ════════════════ 取色 ════════════════

const TONE_BAR: Record<Tone, string> = {
  ok: "bg-emerald-500",
  warn: "bg-amber-500",
  fail: "bg-red-500",
  na: "bg-zinc-300",
};

const TONE_TRACK = "bg-zinc-100";

const TONE_TEXT: Record<Tone, string> = {
  ok: "text-emerald-700",
  warn: "text-amber-700",
  fail: "text-red-700",
  na: "text-zinc-400",
};

const TONE_PILL: Record<Tone, string> = {
  ok: "bg-emerald-100 text-emerald-800 ring-emerald-300",
  warn: "bg-amber-100 text-amber-800 ring-amber-300",
  fail: "bg-red-100 text-red-800 ring-red-300",
  na: "bg-zinc-100 text-zinc-500 ring-zinc-300",
};

const TONE_ICON: Record<Tone, string> = {
  ok: "✅",
  warn: "⚠️",
  fail: "❌",
  na: "–",
};

// ════════════════ 主组件 ════════════════

export function RiskPanel({ detail }: { detail: RunDetail }) {
  const out = (detail.output_payload || {}) as Record<string, any>;
  const enr = out.llm_enrichment as LLMEnrichment | undefined;
  const sections = enr?.sections;

  // ── D1 几何完整性 ──
  const d1Val = detail.geometry_integrity_score;
  const d1: DScore = (() => {
    if (typeof d1Val !== "number") {
      return {
        key: "D1",
        label: "几何完整性",
        value: 0,
        display: "—",
        tone: "na",
        threshold: "≥ 0.85",
        hint: "geometry_integrity_score 暂未上报",
        anchor: "#card-d1-fingerprint",
      };
    }
    const tone: Tone = d1Val >= 0.85 ? "ok" : d1Val >= 0.6 ? "warn" : "fail";
    return {
      key: "D1",
      label: "几何完整性",
      value: clamp01(d1Val),
      display: d1Val.toFixed(2),
      tone,
      threshold: "≥ 0.85",
      hint:
        tone === "ok"
          ? "实体几何检验通过"
          : tone === "warn"
          ? "存在边界自交 / 退化几何，已跳过部分 hatch 填充"
          : "几何完整性偏低，建议检查 INSERT 矩阵 / 单位识别",
      anchor: "#card-d1-fingerprint",
    };
  })();

  // ── D2 语义命中率 ──
  const d2Semantic = sections?.F_quality_breakdown?.semantic;
  const semanticsBlock = (out.semantics || {}) as Record<string, any>;
  const matched = semanticsBlock.matched_terms_count ?? 0;
  const quarantine = semanticsBlock.quarantine_terms_count ?? 0;
  const d2: DScore = (() => {
    let v: number | null = null;
    if (typeof d2Semantic === "number") v = d2Semantic;
    else if (matched + quarantine > 0) v = matched / (matched + quarantine);

    if (v == null) {
      return {
        key: "D2",
        label: "语义命中率",
        value: 0,
        display: "—",
        tone: "na",
        threshold: "≥ 0.85",
        hint: "无语义抽取结果",
        anchor: "#card-d2-semantics",
      };
    }
    const tone: Tone = v >= 0.85 ? "ok" : v >= 0.5 ? "warn" : "fail";
    return {
      key: "D2",
      label: "语义命中率",
      value: clamp01(v),
      display: (v * 100).toFixed(1) + "%",
      tone,
      threshold: "≥ 85%",
      hint:
        tone === "ok"
          ? `${matched} 词命中，词典覆盖良好`
          : tone === "warn"
          ? `${matched}/${matched + quarantine} 命中，建议批量审 quarantine`
          : `仅 ${matched}/${matched + quarantine} 命中，词典覆盖不足`,
      anchor: "#card-d2-semantics",
    };
  })();

  // ── D3 关系本体 ──
  const linksCount = (out.relationships?.count ??
    (Array.isArray(out.links) ? out.links.length : null)) as number | null;
  const linkSymmetry = out.link_symmetry as number | undefined;
  const d3: DScore = (() => {
    if (typeof linkSymmetry === "number") {
      const tone: Tone =
        linkSymmetry >= 0.9 ? "ok" : linkSymmetry >= 0.7 ? "warn" : "fail";
      return {
        key: "D3",
        label: "关系本体",
        value: clamp01(linkSymmetry),
        display: linkSymmetry.toFixed(2),
        tone,
        threshold: "≥ 0.9",
        hint: `link_symmetry=${linkSymmetry.toFixed(2)} (${linksCount ?? "?"} links)`,
        anchor: "#card-d3-links",
      };
    }
    if (typeof linksCount === "number" && linksCount > 0) {
      return {
        key: "D3",
        label: "关系本体",
        value: 0.5,
        display: `${linksCount} links`,
        tone: "warn",
        threshold: "≥ 0.9 link_symmetry",
        hint: "已输出关系但未计算对称性（Phase 5 落地后变绿）",
        anchor: "#card-d3-links",
      };
    }
    return {
      key: "D3",
      label: "关系本体",
      value: 0,
      display: "N/A",
      tone: "na",
      threshold: "≥ 0.9",
      hint: "本次 agent 未输出关系（Phase 5 启用 link_symmetry 时点亮）",
      anchor: "#card-d3-links",
    };
  })();

  // ── D4 输出契约 ──
  const d4: DScore = (() => {
    const ok = !!detail.site_model_id && !detail.error_message;
    return {
      key: "D4",
      label: "输出契约",
      value: ok ? 1 : 0,
      display: ok ? "1.00" : "0",
      tone: ok ? "ok" : "fail",
      threshold: "= 1",
      hint: ok
        ? "SiteModel 已生成 + pydantic 0 errors"
        : detail.error_message
        ? `失败: ${detail.error_message.slice(0, 60)}`
        : "SiteModel 未生成",
      anchor: "#card-d4-sitemodel",
    };
  })();

  // ── D5 可追溯 ──
  const quality = (out.quality || {}) as Record<string, any>;
  const artifactsCount = Object.keys(quality.artifacts || {}).length;
  // 占位：未来从 site_model.statistics.classifier_kind_coverage 取真实覆盖率
  const provenanceCoverage = (
    detail.site_model_statistics as Record<string, any> | undefined
  )?.provenance_coverage as number | undefined;
  const d5: DScore = (() => {
    let v: number;
    if (typeof provenanceCoverage === "number") v = provenanceCoverage;
    else v = artifactsCount > 0 ? 0.5 : 0;
    const tone: Tone = v >= 0.9 ? "ok" : v >= 0.5 ? "warn" : "fail";
    return {
      key: "D5",
      label: "可追溯",
      value: clamp01(v),
      display:
        typeof provenanceCoverage === "number"
          ? (v * 100).toFixed(0) + "%"
          : artifactsCount > 0
          ? `${artifactsCount} artifacts`
          : "0%",
      tone,
      threshold: "≥ 90% provenance",
      hint:
        tone === "ok"
          ? "provenance 字段全覆盖"
          : tone === "warn"
          ? "有 artifacts 但 provenance 覆盖率未上报"
          : "provenance 字段缺失，R5 签字会被 block (GA 必含)",
      anchor: "#card-d5-quality",
    };
  })();

  const dims: DScore[] = [d1, d2, d3, d4, d5];

  // ── 4 闸门 ──
  const gates: GGate[] = [
    {
      key: "G1",
      label: "Schema",
      tone:
        detail.status === "SUCCESS" || detail.status === "SUCCESS_WITH_WARNINGS"
          ? "ok"
          : detail.status === "ERROR"
          ? "fail"
          : "na",
      triggerHint: "每次解析后即时评估：pydantic 通过 + agent_loader 启动 ok",
    },
    {
      key: "G2",
      label: "Gold",
      tone: typeof out.gold_score === "number"
        ? out.gold_score >= 0.92
          ? "ok"
          : "warn"
        : "na",
      triggerHint: "CI 触发：strict_acc ≥ 0.92 + 不掉 >2%（在线运行通常显示 –）",
    },
    {
      key: "G3",
      label: "LLM-Judge",
      tone: typeof out.llm_judge_score === "number"
        ? out.llm_judge_score >= 0.45
          ? "ok"
          : "warn"
        : "na",
      triggerHint: "Weekly cron：3-run avg ≥ 0.45（在线运行通常显示 –）",
    },
    {
      key: "G4",
      label: "E2E",
      tone:
        out.e2e_pass === true ? "ok" : out.e2e_pass === false ? "fail" : "na",
      triggerHint: "GA 发布前：ConstraintAgent E2E 跑通 + R5 签字（在线运行显示 –）",
    },
  ];

  // ── 风险摘要 top-3 ──
  const risks = computeRisks(dims, gates);

  // ── 总判定（与 BusinessNarrative 对齐） ──
  const verdict = computeVerdict(dims, gates);

  return (
    <section className="rounded-lg border-2 border-zinc-200 bg-gradient-to-br from-white to-zinc-50 p-4 shadow-sm">
      {/* Header: 标题 + 总判定 */}
      <div className="mb-4 flex items-center gap-3">
        <span className="rounded-full bg-zinc-900 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
          风险雷达
        </span>
        <h2 className="text-sm font-semibold text-zinc-700">
          5 维评估 · 4 闸门 · 风险摘要
        </h2>
        <span
          className={
            "ml-auto rounded-full px-3 py-1 text-xs font-semibold ring-1 " +
            TONE_PILL[verdict.tone]
          }
          title="同 BusinessNarrative 的总判定"
        >
          总判定：{verdict.label}
        </span>
      </div>

      {/* 4 闸门 */}
      <div className="mb-4 grid grid-cols-2 gap-2 md:grid-cols-4">
        {gates.map((g) => (
          <div
            key={g.key}
            title={g.triggerHint}
            className={
              "flex items-center gap-2 rounded border bg-white px-3 py-2 ring-1 " +
              TONE_PILL[g.tone].replace("bg-", "ring-").replace("text-", "")
            }
          >
            <span className="text-base leading-none">{TONE_ICON[g.tone]}</span>
            <div className="min-w-0 flex-1">
              <div className="text-[10px] font-bold uppercase tracking-wide text-zinc-500">
                {g.key}
              </div>
              <div className={"text-xs font-semibold " + TONE_TEXT[g.tone]}>
                {g.label}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* 5 维进度条 */}
      <div className="mb-4 space-y-1.5">
        {dims.map((d) => (
          <DimRow key={d.key} dim={d} />
        ))}
      </div>

      {/* 风险摘要 top-3 */}
      <div className="rounded border border-zinc-200 bg-white p-3">
        <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-zinc-500">
          风险摘要 (top {risks.length})
        </div>
        <ul className="space-y-1 text-xs leading-relaxed">
          {risks.map((r) => (
            <li key={r.rank} className="flex gap-2">
              <span className={"shrink-0 font-mono " + TONE_TEXT[r.tone]}>
                {r.rank === 0 ? "✓" : `❶❷❸❹❺`[r.rank - 1] || `${r.rank}.`}
              </span>
              <span className="text-zinc-700">{r.text}</span>
            </li>
          ))}
        </ul>
      </div>

      <p className="mt-2 text-[10px] italic text-zinc-400">
        ↓ 点击任一进度条跳转到对应详情卡。BusinessNarrative 的"人话版"在 ⑤ LLM 富化 区域。
      </p>
    </section>
  );
}

// ════════════════ 子组件 ════════════════

function DimRow({ dim }: { dim: DScore }) {
  const pct = Math.max(2, Math.min(100, dim.value * 100));
  const isNa = dim.tone === "na";
  return (
    <a
      href={dim.anchor}
      className="group block rounded px-1.5 py-1 hover:bg-zinc-100"
      title={`${dim.label} · 阈值 ${dim.threshold}`}
    >
      <div className="flex items-center gap-2">
        <span className="w-7 shrink-0 text-[10px] font-bold text-zinc-400">
          {dim.key}
        </span>
        <span className="w-20 shrink-0 truncate text-xs font-medium text-zinc-700">
          {dim.label}
        </span>
        {/* track */}
        <div className={"relative h-2.5 flex-1 overflow-hidden rounded-full " + TONE_TRACK}>
          {!isNa && (
            <div
              className={"absolute left-0 top-0 h-full rounded-full transition-all " + TONE_BAR[dim.tone]}
              style={{ width: `${pct}%` }}
            />
          )}
        </div>
        <span
          className={
            "w-16 shrink-0 text-right font-mono text-xs font-semibold " +
            TONE_TEXT[dim.tone]
          }
        >
          {dim.display}
        </span>
        <span className="w-4 shrink-0 text-center">{TONE_ICON[dim.tone]}</span>
      </div>
      <div className="ml-9 mt-0.5 truncate text-[11px] text-zinc-500 group-hover:text-zinc-700">
        {dim.hint}
        {!isNa && (
          <span className="ml-1 text-zinc-400">· 阈值 {dim.threshold}</span>
        )}
      </div>
    </a>
  );
}

// ════════════════ 计算 ════════════════

function clamp01(x: number): number {
  if (Number.isNaN(x)) return 0;
  if (x < 0) return 0;
  if (x > 1) return 1;
  return x;
}

function computeRisks(dims: DScore[], gates: GGate[]): RiskItem[] {
  const out: RiskItem[] = [];

  // 1. 红色维度优先
  for (const d of dims) {
    if (d.tone === "fail") {
      out.push({
        rank: out.length + 1,
        tone: "fail",
        text: `${d.key} ${d.label} = ${d.display} 低于 ${d.threshold} — ${d.hint}`,
      });
    }
  }

  // 2. 黄色维度
  if (out.length < 3) {
    for (const d of dims) {
      if (d.tone === "warn") {
        out.push({
          rank: out.length + 1,
          tone: "warn",
          text: `${d.key} ${d.label} = ${d.display} — ${d.hint}`,
        });
        if (out.length >= 3) break;
      }
    }
  }

  // 3. G1 失败必须列入
  if (out.length < 3) {
    const g1 = gates.find((g) => g.key === "G1");
    if (g1?.tone === "fail") {
      out.unshift({
        rank: 1,
        tone: "fail",
        text: "G1 Schema 闸 未通过：解析失败/契约错误 — 立即修复，无法降级",
      });
      // 重排 rank
      out.forEach((r, i) => (r.rank = i + 1));
    }
  }

  // 4. G2-G4 灰色提醒（仅在 D 全绿时给一条说明）
  if (out.length === 0) {
    const naGates = gates.filter((g) => g.tone === "na").map((g) => g.key);
    if (naGates.length > 0) {
      out.push({
        rank: 1,
        tone: "ok",
        text: `D1-D5 全部通过；${naGates.join("/")} 闸门待 CI/cron 触发后点亮`,
      });
    } else {
      out.push({
        rank: 0,
        tone: "ok",
        text: "无风险，可放行",
      });
    }
  }

  return out.slice(0, 3);
}

function computeVerdict(
  dims: DScore[],
  gates: GGate[],
): { tone: Tone; label: string } {
  // 任何 D 红 / G1 红 → 阻断
  if (dims.some((d) => d.tone === "fail")) {
    return { tone: "fail", label: "需人工介入" };
  }
  if (gates.find((g) => g.key === "G1")?.tone === "fail") {
    return { tone: "fail", label: "需人工介入" };
  }
  // 任何 D 黄 → 复核
  if (dims.some((d) => d.tone === "warn")) {
    return { tone: "warn", label: "建议复核" };
  }
  // 全绿 / 仅 NA → 可放行
  return { tone: "ok", label: "可放行" };
}
