# ParseAgent A–M 步骤说明（5 阶段 / 13 步）

> 来源：`app/services/enrichment/pipeline.py` + `web/src/app/runs/[id]/page.tsx::STEP_META`。
> 每个 Run 跑过哪些步骤记录在 `output_payload.llm_enrichment.steps_run`，
> 输出落在 `llm_enrichment.sections.<step_id>`，耗时落在 `timings_ms.<step_id>`。

ParseAgent 把"DXF/DWG → SiteModel + 知识图谱"过程拆成 13 个独立步骤，
按管道方式串起来。命名是"字母 + 角色名"（`A_normalize`、`B_softmatch`…），
字母对应它在管线里的逻辑阶段，便于在日志、UI、技术视图里互相引用。

| 字母 | step_id | 阶段 | 能力 | 作用 | 关键产物 |
|------|---------|------|------|------|----------|
| **A** | `A_normalize` | ① 候选准备 | rule | 把脏 layer/block 名清洗成可比较 token（去前缀、去版本号、统一大小写、CN→EN 软翻译） | `items[]: {original, normalized, lang, reason}` |
| **E** | `E_block_kind` | ① 候选准备 | rule | 用 BLOCK 名 + 关键词字典启发式判断块属于哪种资产类型（CONVEYOR / FIXTURE / …） | `items[]: {block_name, asset_type_hint, evidence}` |
| **B** | `B_softmatch` | ② 语义对齐 | embedding | 把候选 token 与 gold ontology（已知术语）做向量相似度对齐 | `matches[]: {candidate, best_match, best_sim}` |
| **C** | `C_arbiter` | ② 语义对齐 | rule | **仲裁器**——根据 sim 阈值把每个候选打成 `promote / review / discard`。`promote` 即"已识别"，`review` 进人工审核 | `promotion_candidates[]`、`counts: {promote, review, discard}` |
| **D** | `D_cluster_proposals` | ③ 提案生成 | hybrid | 把 quarantine 残留的未识别项按相似度聚类，生成"建议新术语" | `proposals[]: {cluster_id, suggested_term, member_count, asset_type_hint, evidence[]}` |
| **K** | `K_asset_extract` | ③ 提案生成 | rule | 从 SiteModel 实体里抽出 Asset 实例（GUID、几何、来源 entity） | `assets[]: {asset_guid, type, label, evidence_keywords, …}` |
| **F** | `F_quality_breakdown` | ④ 质量诊断 | rule | 三维质量打分：parse(解析) · semantic(语义) · integrity(完整性)，加权得 overall | `parse, semantic, integrity, overall, why` |
| **G** | `G_root_cause` | ④ 质量诊断 | rule | 找质量分低的根因（如 "62% 实体未命中 ontology") | `findings[]: {factor, impact}` |
| **L** | `L_geom_anomaly` | ④ 质量诊断 | rule | 几何异常（NaN 坐标、零长 LINE、零面积 HATCH 边界等）巡检 | `anomalies[]` |
| **I** | `I_self_check` | ④ 质量诊断 | rule | **CP-A 闸门**——综合 F+G+L 决定是否阻断后续阶段。输出 `should_block` + `blockers[]` | `should_block, blockers, hints` |
| **J** | `J_site_describe` | ⑤ 叙述与画像 | text-gen | 用 LLM 生成站点画像（标题、摘要、tag），用于 SiteHeader / 卡片 | `title, summary, suggested_tags[]` |
| **M** | `M_provenance_note` | ⑤ 叙述与画像 | rule | 来源凭证说明（输入文件 sha256、版本、转换链路） | `note` |
| **H** | `H_audit_narrative` | ⑤ 叙述与画像 | text-gen | 生成给评审/审批用的"自然语言审计叙述"（替代纯指标读卡片） | `narrative` |

> ⚠ 字母不连续是历史遗留：H/I/J/K/L/M 是后期补的步骤，按"被加入的时间顺序"
> 编号；阶段 ①–⑤ 才是逻辑顺序。

---

## 5 阶段的角色

```
①候选准备  →  ②语义对齐  →  ③提案生成  →  ④质量诊断  →  ⑤叙述与画像
   A · E         B · C         D · K         F · G · L · I       J · M · H
```

- **① 候选准备**：把原始字符串/几何变成"干净的可比较 token"。失败 = 后续全失真。
- **② 语义对齐**：和已知术语库（ontology）对齐。**这一步决定 SiteHeader 上的"已识别 N 项"**。
- **③ 提案生成**：把对不上的部分抱团成 cluster proposal，给人工审核（左侧"待人工确认"列表来自这里）。
- **④ 质量诊断 + CP-A 闸门**：算分 + 找根因 + 决定是否放行（信任凭证卡片 + CP-A 前置条件来自这里）。
- **⑤ 叙述与画像**：把整个过程写成人类可读的文字，交付到 SiteHeader / Audit Narrative 卡片。

---

## UI 层的对应关系（sites/[runId]）

| UI 元素 | 数据来自 |
|---------|----------|
| 左栏「图层树 → 已识别」 | `C_arbiter.promotion_candidates`（即 `C` 输出） |
| 左栏「图层树 → 待人工确认」 | `D_cluster_proposals.proposals` |
| 左栏「CP-A 前置条件」 | `I_self_check.should_block / blockers` + `A.items.length` + `C.counts.promote` |
| 右栏「信任凭证 CP-A」 | `F_quality_breakdown` |
| 右栏「事件日志」 | `steps_run` + `timings_ms` |
| 中栏「原始命名 → A_normalize」 | `A_normalize.items` |
| 中栏「拓扑关系图谱」 | `output_payload.links`（如有），否则派生自 `D × C` |
| Header「站点画像 / tags」 | `J_site_describe.title / suggested_tags` |

---

## 调试技巧

1. **某 Run 已识别 = 0 怎么排查？**
   - 看 `steps_run` 是否包含 `C_arbiter`：缺 → 管线问题。
   - 包含 → 看 `C_arbiter.counts`：`promote=0 / review>0` 是合法（候选未达阈值），不是 UI bug。
   - UI 已经把这 4 种状态做成了 `RecognizedDiag` 4 色提示卡。

2. **质量分低？**
   - 直接读 `F_quality_breakdown.why` + `G_root_cause.findings[]`。
   - 几何类问题在 `L_geom_anomaly`（如 hatch 边界异常 → MLightCAD 预览那个 bug 的源头）。

3. **想看完整 enrichment 原始 JSON：**
   - `/runs/{run_id}` → 「LLM Enrichment」→ 每步独立 StepCard。

---

## 13 步的输入 / 输出落地

ParseAgent 是**单 Run 单事务**：所有 13 步的中间产物被打包写在
`mcp_contexts.output_payload`（一个 JSONB 列）里，最终业务对象（SiteModel /
Asset / 几何）才会扁平化到独立的物理表。这个设计的意图是：

- **可追溯**：任何时间打开 `/runs/{id}/llm_enrichment` 都能看到当时这个
  Run 的 13 步 step-by-step 全文，不依赖二次重算。
- **可演进**：sections 的 schema 是字典而非外键，所以加新 step（H/I/J/K/L/M
  陆续补的就是这样）不需要改表结构。
- **可分流**：业务对象（SiteModel, Asset, asset_geometries）才进强 schema，
  方便 S2/S3 下游直接 JOIN 查询。

### 输入侧（每步从哪儿读数据）

| 字母 | 输入数据源 | 物理位置 |
|------|-----------|----------|
| A | DXF/DWG 解析后的 `entity_dump.layers / blocks` | 内存（同一事务内由 dxfgrabber/ezdxf 解析得到，未单独落库） |
| E | 同上 + `_BLOCK_ASSET_PATTERNS` | 内存 + 代码常量（`agents/parse_agent/service.py`） |
| B | `A.items` 的 normalized token + ontology gold terms | `taxonomy_terms`（PostgreSQL） |
| C | `B.matches` + 阈值配置 | 内存（B 的产物） |
| D | C 仲裁后的 quarantine 残留 + 历史 quarantine | `quarantine_terms` 表（跨 Run 累积） + JSONL `exp/llm_classifications/<run_id>.jsonl` |
| K | SiteModel 实体 + asset_type 推断 | 内存（A/E 的产物，与 SiteModel 一起构建） |
| F | A.stats + B.stats + 几何完整性指标 | 内存 |
| G | F 三维分 + 实体级反查 | 内存 |
| L | SiteModel.assets[].geometry | 内存（即将落 `asset_geometries` 表的 in-memory 版本） |
| I | F + G + L | 内存 |
| J | A/B/D/F + SiteModel 顶层统计 | 内存（LLM 调用） |
| M | `mcp_contexts.input_payload`（文件 sha/版本） + `site_model_cad_source` | DB 读取 |
| H | F + I + J + 选定的 promotion_candidates | 内存（LLM 调用） |

### 输出侧（每步的产物落到哪里）

> 表名以 `db.alembic.versions/*` 中迁移定义为准，模型见 `shared/db_schemas.py`。

#### A. 流水帐（每步的 step 产物）

**全部 13 步的 step-level 产物**统一写在：

```
mcp_contexts.output_payload (JSONB)
  └─ llm_enrichment
       ├─ steps_run: ["A_normalize", "E_block_kind", ...]
       ├─ timings_ms: { A_normalize: 12, B_softmatch: 89, ... }
       ├─ version: "stub-v0" / "openai-emb-v3" / ...
       └─ sections:
            ├─ A_normalize: { items, stats, rationale }
            ├─ E_block_kind: { items, stats }
            ├─ B_softmatch: { matches, stats, thresholds }
            ├─ C_arbiter:   { promotion_candidates, counts }
            ├─ D_cluster_proposals: { proposals }
            ├─ K_asset_extract: { assets }            ← 也会扁平化到 asset_geometries
            ├─ F_quality_breakdown: { parse, semantic, integrity, overall, why }
            ├─ G_root_cause: { findings }
            ├─ L_geom_anomaly: { anomalies }
            ├─ I_self_check: { should_block, blockers, hints }
            ├─ J_site_describe: { title, summary, suggested_tags }
            ├─ M_provenance_note: { note }
            └─ H_audit_narrative: { narrative }
```

> 注：`mcp_contexts` 是"Run"在 DB 中的物理对象。`mcp_context_id` 即 UI 上看到的 `run_id`。

#### B. 业务对象（被下游 Agent 直接消费的强 schema 落库）

| 步骤 | 物理表 | 列 |
|------|--------|-----|
| **K_asset_extract**（资产抽取） | `site_models` | 主表，外键 `site_models.cad_source_run_id → mcp_contexts.id`；存 `assets` JSON、统计、bounding_box、几何完整性分等 |
| **K_asset_extract**（几何细节） | `asset_geometries` | 每个 asset 的 `geometry` JSON、`source_entity_id`、`evidence_keywords`、`sub_type`、`classifier_kind`（迁移 0017 加的） |
| **C_arbiter** 中 *进 quarantine* 的部分 | `quarantine_terms` | 跨 Run 累积："这个候选 term 出现过 N 次、来自哪些 run"。被人工审核 promote 后，记录写入 `taxonomy_terms` 并 archive 此行 |
| **C_arbiter / D_cluster_proposals** 同上 | `exp/llm_classifications/<run_id>.jsonl` | 文件 fallback（`agent.json` 描述的 write-deferred 路径）。每行一个 promotion 候选，等周度聚合脚本处理 |
| **B_softmatch** 用到的字典 | `taxonomy_terms` | 只读（gold ontology），由 `corpus/seeds.yaml` 同步而来 |
| **F + G + I**（CP-A 闸门 / 评估） | `run_evaluations`（迁移 0018） | 5 维 / 4 阶 / 4 闸的评估快照；J 的标题、综合分 overall 也写入便于直接索引 |
| **M_provenance_note** | `audit_logs` + `audit_log_actions` | 来源凭证 → audit_log；下游 ConstraintAgent / LayoutAgent 也往这两张表写 |
| **整个 Run 状态** | `mcp_contexts` | `status`、`finished_at`、`output_payload`、`site_model_id`（FK） |

#### C. 不入 DB 的中间产物

- A/B/E/F/G/I/L/J/H 的 *中间结构*（向量、相似度矩阵、推理草稿）只活在内存，跑完即弃。
- 想复盘 → `output_payload.llm_enrichment.sections` 已经是"压缩后的可见版"。

### 一图流（数据流向）

```
DXF/DWG ──► [A · E]              ──┐
            (内存)                 │
                                   ├──► output_payload.llm_enrichment.sections.* (JSONB)
        ──► [B] ──► taxonomy_terms │
                  ◄────────────────┤
        ──► [C · D] ──► quarantine_terms / exp/*.jsonl
                                   │
        ──► [K]       ──────────► site_models + asset_geometries
                                   │
        ──► [F · G · L · I] ─────► run_evaluations
                                   │
        ──► [J · M · H] ─────────► (only into output_payload + audit_logs for M)
                                   │
                          mcp_contexts.status = "finished"
```

### 下游怎么用这些数据

- **S2 ConstraintAgent** 通过 `site_model_id` JOIN `site_models` + `asset_geometries`，
  约束写入 `constraint_sets` / `process_constraints`。
- **S3 LayoutAgent** 读 `site_models` + `constraint_sets`，候选写 `layout_candidates`。
- **S5 决策工作台** 读 `run_evaluations` + `audit_logs` + `workflows` 做对比与审批。


