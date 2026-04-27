# ParseAgent 运行结果页 · 风险呈现重组方案

**版本**: 1.0 · 2026-04-27
**目标读者**: 复核者（Domain Lead / 工艺工程师）+ 工程负责人
**关联文档**: [ExcPlan/parse_agent_evaluation_dimensions.md](../../ExcPlan/parse_agent_evaluation_dimensions.md)

---

## 0. 一句话目标

> 让复核者**进页面 3 秒之内**判断："这次解析能不能放行？"
> 风险点必须**自上而下、由粗到细**：先看红绿灯 → 再看雷达 → 再下钻到对应详情卡。

---

## 1. 现有页面盘点

`web/src/app/runs/[id]/page.tsx` 当前栈结构（自上而下）：

| 区块 | 组件 | 主要数据源 | 评估职能（重组后映射） |
|---|---|---|---|
| Header | `<h1>` + `<StatusBadge>` + `<LiveIndicator>` | `r.status` | （元信息） |
| Input/Output payload | `<Card>` × 2 | `r.input_payload`, `r.output_payload` | （原始数据，不评估） |
| Error | `<Card>` | `r.error_message` | 反向用：有错就阻断 |
| **① 文件指纹与格式确认** | `<Card>` | `out.fingerprint`, `summary.units/dxf_version` | → **D1 几何本体（输入侧）** |
| **② 解析摘要 (counts/bbox)** | `<Card>` | `summary.entity_total/...` | → **D1 几何本体（实体清点）** |
| **③ 语义抽取结果** | `<Card>` | `semantics.matched_terms/quarantine` | → **D2 语义本体** |
| **④ 质量与可追溯性** | `<Card>` | `quality.confidence_score / artifacts / parse_warnings` | → **D5 可追溯（部分）+ 质量综合** |
| **⑤ LLM 富化与可解释性** | `<LLMEnrichmentSections>` | `out.llm_enrichment.sections` | 跨维：D2（语义） + D5（叙事） |
| `<BusinessNarrative>`（"人话版"） | 内嵌 ⑤ | 同上 | 已是顶层 verdict，但藏在 ⑤ 内 |
| `<PipelineOverview>`（5 阶段图） | 内嵌 ⑤ | 同上 | 已经覆盖 H1–H4 硬度 |
| `<Card title="Linked SiteModel">` | `<Card>` | `r.site_model_id / geometry_integrity_score / assets_count` | → **D4 输出契约**（有 site_model_id 即 OK） |
| `<Card title="Run metadata">` | `<Card>` | `r.latency_ms` | → **D5 可追溯（耗时）** |

**最大的痛点**：
1. `BusinessNarrative` 的 verdict（可放行 / 复核 / 阻断）藏在屏幕**第 4–5 屏**，复核者要先滚很远才能看到结论；
2. 4 个评估卡只有"摘要"，**看不出该卡是在评估什么维度**、阈值多少、过没过；
3. **D3 关系本体维度没有专属卡**（虽然 site_model 里有 `links`），用户没法快速定位"链路是不是断的"；
4. 4 个 GA 闸门（G1–G4）的状态**完全不可见**，复核者不知道"这次跑通过了几道闸门"。

---

## 2. 重组方案 — 在顶端加一个 "风险雷达 + 4 闸门" Banner

### 2.1 视觉布局（Header 之下、Input/Output 之上）

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 风险雷达                                                                  │
│                                                                          │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐                          │
│ │ G1 ✅   │ │ G2 ⚠️   │ │ G3  –   │ │ G4  –   │   ← 4 道 GA 闸门（红绿灯） │
│ │ Schema  │ │ Gold    │ │ LLM-J   │ │ E2E     │      点击展开依据          │
│ └─────────┘ └─────────┘ └─────────┘ └─────────┘                          │
│                                                                          │
│ D1 几何完整性 ████████░░ 0.82  ✓ → 跳 ① ②                                │
│ D2 语义命中率 ██░░░░░░░░ 0.18  ⚠ 词典覆盖不足 → 跳 ③ ⑤                    │
│ D3 关系本体   ░░░░░░░░░░ 0/0   — 该 agent 不输出关系（hidden / N/A）        │
│ D4 输出契约   ████████████ 1.0  ✓ pydantic 0 errors → 跳 SiteModel 卡       │
│ D5 可追溯     ░░░░░░░░░░ 0%   ⚠ provenance 字段缺失（GA 必含）→ 跳 ④      │
│                                                                          │
│ 风险摘要 (top-3):                                                          │
│  ❶ D2 词典命中率 0.18 < 阈值 0.85，建议在 ③ 卡批量审 review 队列           │
│  ❷ D5 100% asset 缺 source_entity_id → R5 签字会被 block                   │
│  ❸ 4 个 GA 闸门仅 G1 通过（运行期通常只有 G1 可评，G2-G4 在 CI/cron 时点亮）│
│                                                                          │
│  总判定: 🟡 建议复核（同 BusinessNarrative）                               │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 5 维进度条计算规则

| 维度 | 数据来源 | 进度值 | 阈值 | 状态色 |
|---|---|---|---|---|
| **D1 几何完整性** | `r.geometry_integrity_score` | 直接读 | ≥ 0.85 绿；0.6–0.85 黄；< 0.6 红 | 三色 |
| **D2 语义命中率** | `out.llm_enrichment.sections.F_quality_breakdown.semantic` 或 fallback `semantics.matched_terms_count / (matched + quarantine)` | 比值 | ≥ 0.85 绿；0.5–0.85 黄；< 0.5 红 | 三色 |
| **D3 关系本体** | `r.output_payload.relationships` 或后续 `link_symmetry`（待实现） | `link_symmetry`（暂不可得时显灰 N/A） | ≥ 0.9 绿；0.7–0.9 黄；< 0.7 红 | 三色 / 灰 |
| **D4 输出契约** | `r.site_model_id` 是否存在 + `r.error_message` 是否为空 | 二值 0/1 | 1 绿；0 红 | 二色 |
| **D5 可追溯** | `quality.artifacts` 完整性 + 未来的 `classifier_kind` 覆盖率 | `artifacts != {} ? 0.5 : 0`，加 `provenance 字段填充率` | ≥ 0.9 绿；0.5–0.9 黄；< 0.5 红 | 三色 |

### 2.3 4 闸门红绿灯计算规则

| 闸门 | 触发时机 | 当前可读源 | 状态 |
|---|---|---|---|
| **G1 Schema** | 每次解析后即可读 | `r.status === "SUCCESS" / "SUCCESS_WITH_WARNINGS"` 即视为 G1 通过；`ERROR` → red | ✅ / ❌ |
| **G2 Gold** | 仅 CI 跑会有 | `out.gold_score` （需后端补字段，**当前默认显示 –**） | ✅ / ⚠️ / – |
| **G3 LLM-judge** | 仅 weekly cron | `out.llm_judge_score` （后端补，**当前显示 –**） | – |
| **G4 Consumer E2E** | 仅 GA prep | `out.e2e_pass` （后端补，**当前显示 –**） | – |

> **说明**: 在线运行只能即时点亮 G1。G2–G4 是离线 CI / cron 才会有的字段，因此前端用灰色 `–` 占位即可，避免误导用户以为"全红"。鼠标悬停显示触发时机说明。

### 2.4 风险摘要 top-3 生成规则

按以下优先级取前 3 条：

1. **任何 D 维度处于红色** → 文案 = "{D 名} = {值} < 阈值 {阈值}，建议在 {对应卡序号} 排查"
2. **G1 红 / 任何 D 黄** → 文案 = 取黄色维度具体警告
3. **D5 = 0** → 文案 = "100% asset 缺 source_entity_id → R5 签字会被 block"
4. 全绿时显示 "无风险，可放行"

---

## 3. 现有 4 个卡片的最小改动

只在卡片标题左侧加一个 `<DTag>` 小芯片，标注它评估的维度，**不动卡片内容**：

```
[D1] ① 文件指纹与格式确认
[D1] ② 解析摘要 (counts / bbox)
[D2] ③ 语义抽取结果 (taxonomy + quarantine)
[D5] ④ 质量与可追溯性
[D2 · D5] ⑤ LLM 富化与可解释性     ← 跨维
[D4] Linked SiteModel
[D5] Run metadata
```

这样用户点开任何一个 D 维度的进度条 → 锚跳到对应卡片，**且卡片自带 D-tag 让他知道"我现在看的是哪一维"**。

### 3.1 D3 关系本体专属卡（新增 / 视未来需求）

GA 没强制要求新卡 —— 因为目前 ParseAgent 的 `links` 数据已经在 `Linked SiteModel` 卡里（`r.site_model_assets_count` 旁边显示 `links_count` 即可）。**Phase 5 当 link_symmetry / link_precision 真正落地时再单独成卡**。

---

## 4. 跟 BusinessNarrative 的关系

`BusinessNarrative` 已经做了 **"WHAT / WHY / NEXT 三段 + 总判定"**，是页面的"业务叙述"层。新加的 `RiskPanel` 是 **"风险量化"层**：

| 层 | 受众 | 信息密度 | 当前位置 |
|---|---|---|---|
| RiskPanel（新） | Domain Lead 复核 / 工程负责人 | 高（5 D + 4 G + top-3） | **页首**（Header 之下，最先映入眼帘） |
| BusinessNarrative | 复核者 / 业务方 | 中（自然语言三段话） | ⑤ 富化区域 |
| 4 个评估卡 | 工程负责人下钻 | 低（专项明细） | 页中 |
| Pipeline 5 阶段 | 工程师 / Audit | 极低（每步技术细节） | 页中后部 |

**两者互补**：`RiskPanel` 是复核者的「**仪表盘**」，`BusinessNarrative` 是给业务方的「**新闻稿**」，下钻卡是给工程师的「**故障诊断**」。

---

## 5. 实施清单（≤ 4 工时）

| 步骤 | 工时 | 文件 |
|---|---|---|
| 5.1 新建 `RiskPanel` 组件 | 1.5h | `web/src/components/runs/RiskPanel.tsx` |
| 5.2 把 `RiskPanel` 接入 `runs/[id]/page.tsx`（Header 之下立刻渲染） | 0.3h | `web/src/app/runs/[id]/page.tsx` |
| 5.3 给现有 7 个卡的标题前加 `<DTag>` chip | 0.5h | 同上 |
| 5.4 提取 `<DTag>` / `<GateLight>` 共用样式（emerald/amber/red/zinc） | 0.5h | `RiskPanel.tsx` 内联或单独抽 |
| 5.5 加 anchor id（`#card-d1-fingerprint` 等），让进度条点击可跳卡 | 0.2h | 同上 |
| 5.6 单测 `RiskPanel.test.tsx`（5 维 / 4 闸门 fixture） | 1h | `web/src/components/runs/RiskPanel.test.tsx` |

---

## 6. 关键 UI 决策

1. **不替换 `BusinessNarrative`** —— 它已经面向业务侧很到位；`RiskPanel` 只补"量化指标 + 风险定位"。
2. **G2-G4 默认灰色 `–`** —— 避免上线第一天用户看到一片红误以为全坏。带 tooltip 说"此闸门在 CI/cron 触发"。
3. **进度条点击 = 锚跳详情卡** —— 用 `href="#card-d1"` + scroll-margin 自然实现，不需要额外 router。
4. **D5 警告优先级最高** —— GA plan §S1-T2 是 breaking change，没填会卡 R5 签字 → top-3 风险摘要里恒置首位（如果未填）。
5. **使用 emerald/amber/red 三色，对齐 `BusinessNarrative.verdict.tone` 配色** —— 视觉一致。
