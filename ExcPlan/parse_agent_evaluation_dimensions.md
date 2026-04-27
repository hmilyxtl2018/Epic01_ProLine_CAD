# ParseAgent 评估全景 — 5 维 / 4 阶 / 4 闸门

**版本**: 1.0
**创建日期**: 2026-04-27
**Owner**: ParseAgent 工程负责人
**关联文档**:
- [parse_agent_ga_execution_plan.md](./parse_agent_ga_execution_plan.md) — 工时与 Sprint 切分（本文是它的 §7.4 前置补充）
- [agents/parse_agent/agent.json](../agents/parse_agent/agent.json) — Claude AgentDefinition 契约
- [shared/models.py](../shared/models.py) — `Asset` / `OntologyLink` / `SiteModel` 本体 schema
- [agents/parse_agent/gold/jijia_gold.yaml](../agents/parse_agent/gold/jijia_gold.yaml) — Gold 锚点

---

## 0. TL;DR

> **ParseAgent ≠ DXF 解析器**。`ezdxf` / `libredwg` 才是解析器。
> ParseAgent 干的事是 **"DXF → SiteModel 的语义提升 (semantic lifting)"**：
> 把 entities/blocks/layers 这些**几何 + 字面量**翻译成业务概念图 ——
> Equipment / Conveyor / Zone / LiftingPoint / Annotation
> + 它们之间的 LOCATED_IN / FEEDS / LABELED_BY 关系，
> 并附上**置信度 + 证据 + provenance** 让下游可信任地消费。

`SiteModel` 就是 **"针对单张图纸的本体实例 (ABox)"**；TBox（类型 + 关系 schema）由人在 `shared/models.py` + `agent.json` + `jijia_gold.yaml` 中定义；ParseAgent 只填 ABox + 置信度元数据。

完成基线一句话：

> **G1 (Schema) + G2 (Gold) + G3 (LLM-judge) + G4 (Consumer E2E)** 全绿，
> 且 5 维评估指标在 jijia + 至少 1 个独立 silver corpus 上**重复跑 3 次都不漂移**，
> 才能升 `parse_agent/v1.0.0` GA。

---

## 1. 评估维度 — 5 维（D1–D5）

我们把 ParseAgent 的产出按"**它在评估什么**"切成 5 个正交维度。这 5 维 1–1 对应 GA plan §1 的 7 层（L6/L7 是元层 → 评测 + 工程化，是落实手段，不再独立成维度）。

| # | 维度 | 它评估什么 | 落在 L 层 | 落在 Role | 关键指标 |
|---|---|---|---|---|---|
| **D1** 输入与几何本体 | 文件能不能开、坐标系/单位/INSERT 矩阵是否正确、几何是否有效（闭合多段线、自交 hatch 等） | L1 + L2 | R1 / R3 | `geometry_integrity_score`、`max_abs_coord`、单位推断成功率、版本兼容率 |
| **D2** 语义本体 ⭐ | 实体落到 6 类 AssetType 是否正确、未知占比是否可控、Annotation 是否独立 | L3 | R2 / R3 / R4 / R5 | strict_acc、Equipment recall、Unknown%、平均 confidence、KL divergence、LLM-judge 语义合理性 |
| **D3** 关系/拓扑本体 | LOCATED_IN / FEEDS / LABELED_BY 是否对称、链路顺序合理、悬空节点占比 | L4 | R2 / R6 | `link_symmetry`、关系召回 + **关系精确率**（见 §5.加固 2）、孤儿节点率 |
| **D4** 输出契约 | SiteModel 通过 pydantic strict、mcp_context 完整、`agent.json` 与代码一致 | L5 | R1（硬阻断）/ R6 | pydantic 0 ValidationError、`mcp_context_id` 在 CAS 可寻、E2E PASS |
| **D5** 可追溯 + 工程化 | 每条 asset 是怎么得出的（rule_block / rule_layer / llm_fallback / heuristic）+ 调用了多少 LLM token / cost / 耗时 | L5.4 + L7 | R1 / R3 | `classifier_kind` 分布、`source_entity_id` 100% 覆盖、`llm_evidence` 校验通过率、parse_time_ms、llm.cost |

> **为什么把 D5 单列而不并入"质量"**：
> - 它对应 `shared/models.py` 即将做的 breaking change（`Asset.source_entity_id` / `classifier_kind` / `llm_evidence`），是 [GA plan S1-T2](./parse_agent_ga_execution_plan.md#s1-t2--provenance-字段-l54--2h) 的硬要求；
> - 一旦 D5 缺了，D2/D3 出问题时**根本无法 root-cause**，也无法支撑 R5 Domain Expert 的人工审计 → R5 没法签字 → GA 卡死。

---

## 2. 语义本体构建的 4 阶硬度（H1–H4）

ParseAgent 对一张图做的本体抽取**由易到难**分 4 阶：

```
H1 几何识别        ← 是不是 INSERT/MTEXT/LWPOLYLINE       (L2)
   ↓
H2 字面量映射      ← 块名 "EXTAR-70A" 命中 EQUIPMENT 词表    (L3.1 规则匹配)
   ↓
H3 上下文消歧      ← 同名块在不同 layer 上意义不同            (L3.2 layer/几何特征)
   ↓
H4 语义补全        ← 词表没收录的新设备名让 LLM 推断 type    (L3.3 LLM 兜底)
```

**关键点**：H1/H2 是**确定性可回放的** (rule-based，零幻觉)，H3/H4 是**概率推断**（必须配 H5 evidence_keywords ⊆ input_tokens 校验 + H6 0.8 置信度折扣，**双保险**）。映射到 `Asset.classifier_kind`：

| 阶 | classifier_kind | 默认 confidence | LLM 调用 |
|---|---|---|---|
| H1 (几何识别) | n/a — 不直接出 type | n/a | ❌ |
| H2 (字面量) | `rule_block` | 0.95 | ❌ |
| H3 (消歧) | `rule_layer` / `rule_geom` / `heuristic` | 0.6–0.85 | ❌ |
| H4 (LLM 兜底) | `llm_fallback` | ≤ 0.8 × LLM 自报 | ✅（限 50/file） |

下游 (ConstraintAgent) 看到的不是 "它是 Equipment"，而是 **"它是 Equipment，置信度 0.76，来源是 LLM 兜底，证据词是 ['extar', 'machining']"** —— **本体构建的"可信度元数据"和本体本身一样重要**。

---

## 3. 完成基线 — 4 道闸门（G1–G4）

这是把 [GA plan §7.5.3](./parse_agent_ga_execution_plan.md#753-ga-准入硬条件-and-关系) 翻译成"开发当天就能跑"的 4 道闸门：

| 闸门 | 触发 | 通过条件 | 不过怎么办 |
|---|---|---|---|
| **G1 Schema 闸**（D4） | 每次跑解析 | pydantic 0 ValidationError + `agent_loader.load_agent_definition()` 启动通过 + 必填 provenance 字段非空 | 立即 fail-fast，不允许 fallback 静默吞 |
| **G2 Gold 闸**（D2 + D3） | 每个 PR (CI) | strict_acc ≥ 0.92 **且** 相对 baseline 不掉 >2% **且** Equipment recall ≥ 0.85 **且** range_pass = 1.0 **且** link_symmetry ≥ 0.9 **且** link_precision ≥ 0.85 | block PR merge |
| **G3 LLM-judge 闸**（D2 语义合理性） | weekly cron | 3-run avg ≥ 0.45 + reject 率 < 5% + stable_run_hash 一致 | 趋势告警，不 block PR，但 block GA |
| **G4 Consumer E2E 闸**（D5 + D4） | GA 发布前 | ConstraintAgent 至少 1 例 jijia 全链路跑通 + provenance 100% 字段覆盖 + R5 Domain Lead 签字 | block GA tag |

**注意**：[GA plan §S3-T1](./parse_agent_ga_execution_plan.md#s3-t1--insert-矩阵展开-l22--6h) (INSERT 矩阵展开) 完成后**必须重置 gold baseline**（`gold_eval_phase4.json` → `gold_eval_phase5_geom.json`），否则 G2 会假性触发回退。

---

## 4. 5 维 × 7 层 × 6 角色 × 7 钩子 一图速览

```
┌──────────────────────────────────────────────────────────────────────────┐
│  D1 输入与几何本体  ←─  L1 输入与格式  + L2 几何与坐标                       │
│      钩子: H1_format_validate, H2_coord_sanity                            │
│      角色: R1 Schema Guardian, R3 Silver Statistician                    │
│                                                                          │
│  D2 语义本体 ⭐  ←─  L3 语义识别（H1→H2→H3→H4 的 4 阶硬度都在这一层）        │
│      钩子: H3_rule_classify, H4_llm_classify_unknowns,                   │
│            H5_response_validator, H6_confidence_calibration              │
│      角色: R2 Gold Auditor, R3 Silver Stat, R4 LLM Judge, R5 Expert      │
│                                                                          │
│  D3 关系/拓扑本体  ←─  L4 关系拓扑                                          │
│      钩子: (无专属钩子, 由 quality_diagnose.compute_link_symmetry 守门)    │
│      角色: R2 Gold Auditor, R6 Consumer Contract                         │
│                                                                          │
│  D4 输出契约  ←─  L5 输出契约                                               │
│      钩子: H5（兼校验 LLM 响应 schema）, agent_loader._validate            │
│      角色: R1（硬阻断）, R6 Consumer                                       │
│                                                                          │
│  D5 可追溯 + 工程化  ←─  L5.4 provenance + L7 工程化                        │
│      钩子: H7_gold_regression_check                                       │
│      角色: R1 Schema, R3 Silver                                          │
└──────────────────────────────────────────────────────────────────────────┘

      L6 评测守门 = G1–G4 闸门的执行器（CI / weekly cron / GA 准入审）
      L7 工程化   = OTel / Cost Budget / ErrorCode / Service / Drift Detector
                    它们不直接评估本体，是"让评估能持续做下去"的脚手架
```

---

## 5. 加固清单（GA 必含 / GA 推后 二选一）

读完 [parse_agent_ga_execution_plan.md](./parse_agent_ga_execution_plan.md) 后发现 4 处偏弱，建议在剩余 Sprint 里顺手补：

### 5.1 Asset.sub_type 占位字段 — **GA 必含**

GA plan §9 把 sub_type 推到 Phase5+，但 Equipment 内部 (HoningMachine / WashingMachine / LeakTester) 的细分对 ConstraintAgent **的工艺约束推理至关重要**。GA 不一定要做出推理逻辑，但应该**至少在 SiteModel 里留 `sub_type: str | None = None` 字段**，让 LLM-judge 评估能有个分层路标。

**改动成本**: 1 行 schema + 1 个测试占位。**今天就能加，向前兼容旧数据。**

```python
class Asset(BaseModel):
    # ... existing ...
    sub_type: str | None = None  # e.g. "HoningMachine" / "WashingMachine"
```

### 5.2 link_precision 评测指标 — **GA 必含**

D3 关系本体目前只评了"该有的关系有没有出"（recall），没评"不该有的关系是不是没出"（false-positive on FEEDS 链）。LLM 兜底 + 半径动态 LABELED_BY 都可能导致**幻关系**。

**改动**: `scripts/gold_eval.py` 加 `link_precision` 指标（除了 recall）。**G2 闸门加一行 ≥ 0.85**。

### 5.3 stable_run_hash — **GA 必含**

同一份 jijia.dwg 跑 10 次，asset 个数应该完全一样、`classifier_kind` 分布漂移应 < 1%。建议在 [S4-T3 Drift Detector](./parse_agent_ga_execution_plan.md#s4-t3--drift-detector-l74--4h) 里**加 stable-run hash**，把"再跑一次结果是否一致"也纳入 G3 GA 准入。

> 这是**判别幻觉与噪声**的最便宜方法，几乎不增加工时（drift_check.py 已经在跑）。

### 5.4 R5 Domain Expert 的签字界面 — **GA 推后到 Phase 5（但需要 placeholder URL）**

R5 Domain Expert 在 Role 矩阵里是 `requires_approval`，但工程上**还没有界面**让他签字 —— `propose_taxonomy_term` tool 已经在 `agent.json` 里，但词表 PR 流程仍在 markdown 上。GA 之前如果没有 UI，至少需要：

- **占位 URL**: `web/src/app/quarantine/page.tsx` 已经存在，把它和 `exp/llm_classifications/<run_id>.jsonl` 串起来；
- **签字方式**: 暂时仍用 GitHub PR 评论 `GA-APPROVED`，但 quarantine 页面要能渲染该 jsonl + 一键复制候选词条到剪贴板。

**真正的 web UI（点同意/拒绝就写回 jijia_gold.yaml）推到 Phase 5。**

---

## 6. 验收 checklist 增量（贴到 [GA plan §7.5.5](./parse_agent_ga_execution_plan.md#755-验收-checklist-ga-发布前必跑) 之后）

```bash
# G2 增量: link_precision
python scripts/gold_eval.py \
  --run-dir <...> \
  --baseline <...> \
  --regression-threshold 0.02 \
  --assert link_precision>=0.85

# G3 增量: stable_run_hash 一致性 (跑 3 次取 hash, 全部相同)
for i in 1 2 3; do
  python -m agents.parse_agent.app parse jijia.dwg \
    --run-dir exp/parse_results/stable_check/run_$i
done
python scripts/quality_drift_check.py \
  --run-dirs exp/parse_results/stable_check/run_{1,2,3} \
  --assert classifier_kind_drift<0.01

# D5 增量: provenance 全字段覆盖
python -m pytest tests/test_pt_p1_01_provenance.py -v
```

---

## 7. 快速 FAQ

**Q: 为什么 D2 语义本体是核心 ⭐？**
A: D1 是"文件读得出"，是基础前提；D3/D4/D5 都是"有了 D2 之后才有意义"。语义错了，整张本体就废了。所以 GA 双指标 (gold ≥ 0.92 + LLM-judge ≥ 0.45) 都落在 D2。

**Q: ParseAgent 算"本体构建"吗？**
A: 算 ABox 抽取 + 置信度标注，不算 TBox 设计。TBox 由 `shared/models.py` 静态定义，词表演化通过 `propose_taxonomy_term` 走 R5 审批，再写回 `jijia_gold.yaml` 才进入下一轮迭代 —— 这是**明确的人在回路**，不是 agent 自动改 schema。

**Q: 没有 sub_type 也能 GA 吗？**
A: 能，但 ConstraintAgent 的工艺约束推理会被卡。所以 §5.1 强烈建议**至少加占位字段**，schema 兼容性比业务推理重要 —— 字段加了下次再用 0 成本，字段没加将来要做 schema migration 成本高 5×。

**Q: D5 可追溯和"日志"有什么区别？**
A: 日志是开发者看的，provenance 是**下游 Agent + Domain Expert 看的**。`Asset.classifier_kind=='llm_fallback'` 会触发 ConstraintAgent 把 `Asset.confidence` 二次乘以一个保守因子，影响的是**业务决策**，不是 debug。

---

## 8. 落地路径

按 GA plan 现有 Sprint 切分，5 个加固点的归属：

| 加固 | Sprint | 工时 | 阻断 GA |
|---|---|---|---|
| 5.1 sub_type 占位字段 | **S1**（schema 改动并入 S1-T2 provenance） | +0.5h | ✅ |
| 5.2 link_precision | **S3-T5** 之后追加 | +2h | ✅ |
| 5.3 stable_run_hash | **S4-T3 Drift Detector** 内含 | +1h | ✅ |
| 5.4 R5 quarantine page 占位 | **S4-T4 FastAPI Service 完善** 内含 | +2h | ⚠ Phase5 完整化 |

**总增量工时 ≈ 5.5h**，不影响原 8–9 工作日总盘子。

---

## 9. 决策记录

- 5 维拆法 (D1–D5) 是 GA plan §1 七层评估的**视图重排**，不是新维度。
- 4 阶硬度 (H1–H4) 与 `Asset.classifier_kind` **强一致**，新增 kind 必须更新 §2 表格。
- G1–G4 闸门是 GA plan §7.5.3 GA_satisfy 公式的执行视图，**不允许在 G 闸门外加任何"特例通过"**。
- `sub_type` 字段标注为 Phase5+ **业务推理目标**，但 GA schema 必须先留位。
