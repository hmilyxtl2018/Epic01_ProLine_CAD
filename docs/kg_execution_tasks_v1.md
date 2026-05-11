# 图计划 + LLM 抽取/绑定/推理 — 详细执行计划 v1

> 配套设计文档：[docs/kg_constraint_execution_plan.md](docs/kg_constraint_execution_plan.md)
> 本文是上面设计的**任务级拆解**，可按 Task ID 直接开 PR。每条 Task 给出：
> 目的 / 改动文件 / 接口契约 / 测试 / 验收 / 估时（人天，理想值）/ 依赖。
> 待你审核通过后从 T1 开始顺序执行。

---

## 0. 执行原则（动手前的红线）

1. **一 Task 一 PR**，提交信息走 Conventional Commits（参见 `CLAUDE.md §8`）。
2. **每个 PR 必带**：L0 schema/contract 测试 ≥ 5 条新增、L1 gold ≥ 1 条新增（累计达到 §7 阈值）。
3. **alembic round-trip 必须过**：`downgrade -1 && upgrade head` 在 PR 检查里跑。
4. **LLM 默认走 stub provider**（`LLM_PROVIDER=stub`），CI 不烧 token；真模型只在本地手动 + nightly 跑。
5. **MCP 透传**：每个新接口/服务的入参第一位都是 `mcp_context_id: str`，否则不准合。
6. **不动既有 demo 数据**：所有新视图 / 新表必须能在现有 4 条 PC-DEMO-* 上验证。
7. **写入永远走 API/服务层**，不允许从脚本直接 INSERT 进 `process_constraints` / `constraint_extractions`。

---

## M1 — 抽取通路（让 LLM 把文档变成 draft 约束）

### T1. ADR-0010 + 抽取证据表 schema  ✅ 已完成（commit 4468cbf）

> **实施偏离 v1 初稿（已落地，本节为最终事实）**：
> 1. **表名**改为 `constraint_extractions`（不是 `constraint_evidence`）。原因：0016 已存在 `constraint_sources` / `constraint_citations`（人审 curation 层）；新表语义是"LLM/regex 抽取过程的原始 span 痕迹"（process 层），与 curation 层并存，详见 ADR-0010 §2.1。
> 2. **列扩展**：新增 `chunk_id`、`extractor_kind`(`llm`/`regex`/`rule`/`human`)、`llm_model`、`prompt_version`、`extraction_run_id`、`extraction_confidence`、`extraction_payload`(JSONB)，以满足 LLM 抽取追溯要求。
> 3. **CHECK 约束**：9 条；其中 `ck_ce_llm_metadata` 强制 `extractor_kind='llm'` 时必须带 `llm_model + prompt_version`；`ck_ce_span_hash_format` 强制 sha256 64 位 hex；`ck_ce_payload_object` 强制 JSONB 顶层对象。
> 4. **唯一索引** `uq_ce_hash_per_constraint(process_constraint_id, span_hash)` 实现按约束去重。

**目的**：把"LLM 抽取约束 + 多段证据"这件事正式立案，提供 `constraint_extractions` 表承接 1:N 抽取证据；与 0016 `constraint_citations`（curation 层）形成两层证据模型。

**已交付**
- [docs/adr/0010-llm-constraint-extraction-and-kg-inference.md](adr/0010-llm-constraint-extraction-and-kg-inference.md)：Context / Decision / Consequences；引 [kg_constraint_execution_plan.md](kg_constraint_execution_plan.md) 为详设；决策点 ①LLM 永远 `parse_method='LLM_EXTRACT' + review_status='draft' + is_active=false`；②抽取证据 1:N 用新表（process 层），与 0016 curation 层分离；③kg facade 视图前缀 `kg_`；④推理留痕表用 hypertable；⑤T6 绑定改用 `binding_strategy='semantic' + binding_evidence` JSONB（**不**扩 enum）。
- [db/alembic/versions/0028_constraint_extractions.py](../db/alembic/versions/0028_constraint_extractions.py)。
- [shared/db_schemas.py](../shared/db_schemas.py) `ConstraintExtraction` ORM。
- [tests/db/test_0028_constraint_extractions.py](../tests/db/test_0028_constraint_extractions.py)：15 测试覆盖 schema sanity / happy path / 8 条 CHECK guard / 唯一性 / FK 级联。

**实测**
- `alembic downgrade -1 && upgrade head` 干净；
- 15 / 15 测试通过；
- `check_schema_drift.py` 仅剩 `AssetType` 枚举差异（**预先存在**，与 T1 无关）。

---

### T2. Pydantic 抽取 IO Schema
**目的**：定义 LLM Stage A/B 的输入输出契约，作为后续所有抽取代码的"一等公民"。

**改动**
- 新建 `app/schemas/constraint_extraction.py`：
  ```python
  class DocumentChunk(BaseModel):
      doc_id: str
      page: int
      char_start: int
      char_end: int
      text: str         # ≤ 4000 字
      content_hash: str

  class ExtractCandidate(BaseModel):           # Stage A 输出
      chunk_id: str
      span_start: int
      span_end: int
      span_text: str
      reason: str       # ≤ 200 字

  class ExtractedScope(BaseModel):
      node_rds_candidates: list[str] = []
      asset_guid_candidates: list[str] = []
      product_id: str | None = None

  class ExtractedConstraint(BaseModel):        # Stage B 输出
      kind: ConstraintKind
      category: ConstraintCategory
      cls: ConstraintClass = Field(alias="class")
      severity: ConstraintSeverity
      authority: ConstraintAuthority
      conformance: ConstraintConformance
      rule_expression: str
      rationale: str
      applicable_phases: list[ConstraintPhase]
      valid_from: datetime | None = None
      valid_to: datetime | None = None
      scope: ExtractedScope
      source_document_id: str
      source_span: dict       # {page, char_start, char_end}
      span_text: str
      confidence: float = Field(ge=0.0, le=1.0)

  class ExtractRequest(BaseModel):
      site_model_id: str
      document_id: str
      chunks: list[DocumentChunk] = Field(min_length=1, max_length=50)
      mcp_context_id: str

  class ExtractResponse(BaseModel):
      mcp_context_id: str
      candidates_count: int
      extracted_count: int
      drafts_written: int
      evidence_written: int
      warnings: list[str] = []
  ```
- 复用 `shared/models.py` 已有的枚举（`ConstraintKind/Category/Class/Severity/Authority/Conformance/Phase`）；缺哪个补哪个，不要平行造。

**测试**：`tests/schemas/test_constraint_extraction.py` — 至少 8 条：
- 合法 round-trip
- `confidence` > 1.0 → 422
- 缺 `source_span` → 422
- `kind=predecessor` 时 `scope.node_rds_candidates` 至少 2 个（业务校验）
- enum 越界 → 422
- alias `class` 写入读出
- min_length / max_length 边界
- `valid_to < valid_from` → 422（自定义 validator）

**验收**：单测全过 + `mypy app/schemas/constraint_extraction.py` 0 错。

**估时**：0.5 天 · **依赖**：T1（用到 `ConstraintEvidence` 的 doc_id/page 概念对齐）

---

### T3. Stage A/B Prompt 模板 + 离线 fixture
**目的**：把抽取的"知识"沉淀进可版本控制的 prompt 文件，让 stub 和真 LLM 用同一份输入。

**改动**
- 新建目录 `app/services/constraint_extractor/prompts/`：
  - `stage_a_candidates.zh.md`：高召回，输出 `ExtractCandidate[]` JSON。
  - `stage_b_structured.zh.md`：高精度，输出 `ExtractedConstraint`，硬注入：
    - `ConstraintCategory` 枚举字典（中英对照）
    - `AssetType` 枚举字典
    - 沈飞 RDS 码格式说明（`-ENT.AC.SH01.A2.L1.S20`）
    - 反例 5 条（"不要把'建议'当 MUST"等）
- 新建 fixture：
  - `tests/fixtures/extraction/ao_sample_001.txt` — 一段脱敏装配 AO 文本（含 1 条 SAFETY、1 条 SEQUENCE、1 条 RESOURCE）。
  - `tests/fixtures/extraction/ao_sample_001.expected.json` — 期望抽取结果（gold）。
- `prompt_version` 常量：`STAGE_A_VERSION = "stage_a_v1"`、`STAGE_B_VERSION = "stage_b_v1"`，写进 `extractor.py` 顶部。

**测试**：`tests/services/test_extractor_prompts.py`：
- prompt 文件存在且 ≥ 200 字；
- 模板内字符串包含所有枚举值（防漏注入）；
- fixture JSON 通过 `ExtractedConstraint.model_validate`。

**验收**：fixture 在 stub provider 下能被回放（T4 实现后联调）。

**估时**：1 天 · **依赖**：T2

---

### T4. ConstraintExtractor 服务 + 双 provider
**目的**：可调用的抽取服务，stub 与真 LLM 同形。

**改动**
- 新建 `app/services/constraint_extractor/__init__.py`、`extractor.py`：
  ```python
  class ConstraintExtractor:
      def __init__(self, llm: LLMClient, *, mcp_context_id: str): ...
      def extract(self, req: ExtractRequest) -> list[ExtractedConstraint]:
          # Stage A → Stage B → 校验闸口 → 返回
  ```
- 校验闸口（在服务层强制，不由 LLM 自觉）：
  1. JSON Schema 失败 → 丢弃 + warning；
  2. `source_span` 必须能在原 chunk 命中；`span_text` 与原文 hash 比对，否则丢弃；
  3. `confidence < 0.6` → 强制 `review_status='draft'`（默认就是）；
  4. `authority ∈ {regulation, standard}` 且 `severity == 'minor'` → 升 `severity='major'`；
  5. `kind=predecessor` 且 scope 候选 < 2 → 进 warnings 但不丢。
- Stub provider 实现：读 `tests/fixtures/extraction/*.expected.json` 回放，让 CI 离线 100% 可复现。
- 新建 `app/services/constraint_extractor/stub_data.py`：fixture → 内存映射。

**测试**
- `tests/services/test_constraint_extractor.py`：
  - L0：服务初始化 + 空输入 → 空输出 + warning
  - L1 gold：fixture in → expected out 完全一致（≥ 1 条 gold）
  - 校验闸口逐条单测（5 条）

**验收**
- `pytest tests/services/test_constraint_extractor.py -q` 全过；
- `LLM_PROVIDER=stub` 在 CI 默认；
- 真 OpenAI provider 走 `test_constraint_extractor_openai.py`，标 `@pytest.mark.slow` 不在主流水线。

**估时**：1.5 天 · **依赖**：T2、T3

---

### T5. POST /constraints/extract API + 写入闭环
**目的**：HTTP 入口；落地到 DB；端到端可演示。

**改动**
- 在 [app/routers/constraints.py](app/routers/constraints.py) 加：
  ```python
  @router.post("/sites/{site_model_id}/constraints/extract",
               response_model=ExtractResponse, status_code=202)
  def extract_constraints(site_model_id: str, req: ExtractRequest, ...): ...
  ```
- 实现：
  1. 校 site_model_id 存在；
  2. 写 `mcp_contexts`（一条），拿到 `mcp_context_id`；
  3. 调 `ConstraintExtractor.extract(req)`；
  4. 每条 `ExtractedConstraint` →
     - INSERT `process_constraints`（`parse_method='LLM_EXTRACT'`、`review_status='draft'`、`is_active=false`、带 `mcp_context_id`、`scope` 落 JSONB 含 `product_id`）；
     - INSERT `constraint_extractions` 一行（`span_hash=sha256(span_text)`，`extractor_kind='llm'` + `llm_model` + `prompt_version`）；
  5. **不写 `constraint_scopes`**（绑定走 M2）；
  6. 返回 `ExtractResponse`。
- 错误处理：JSON Schema 失败 → 422；DB 失败 → 500 并回滚整批。

**测试**
- `tests/routers/test_constraints_extract.py`：
  - 200 + drafts_written ≥ 1 + evidence_written ≥ 1
  - 无效 site_id → 404
  - 缺 `mcp_context_id` → 422
  - 重放同一 fixture 两次 → 两批独立 draft（不去重，去重走 review 阶段）

**验收**
- 跑：
  ```powershell
  curl -X POST http://localhost:8000/sites/SM-DEMO-001/constraints/extract `
    -H "Content-Type: application/json" `
    -d "@tests/fixtures/extraction/ao_sample_001_request.json"
  ```
  返回 202 + 计数；
- `SELECT * FROM v_constraint_set_summary` 看到 `draft_count` 增长；
- `SELECT * FROM constraint_extractions` 出现新行带 hash。

**估时**：1 天 · **依赖**：T1、T4

**M1 出口**：演示给沈飞 = 上传一段 AO，看到 LLM 抽出 N 条 draft 约束 + 原文 citation。

---

## M2 — 绑定通路（LLM 把约束挂到工位/资产）

### T6. constraint_scopes 扩 binding 元数据（**方案修订**）

> **修订原因**（见 ADR-0010 §2.3）：v1 初稿想给 `binding_kind` enum 加 `'suggested_by_llm'`。但 PG `ALTER TYPE ... ADD VALUE` 必须跨事务，且 downgrade 不安全（enum 值无法移除）。改为复用现有 `binding_strategy='semantic'` + 在 `binding_evidence` JSONB 标注 `{provider:'llm', model, prompt_version, run_id, confidence}`。完全兼容现 0024 视图与 `ck_cscope_manual_verified`。

**改动**
- alembic `0029_binding_llm_metadata.py`：
  - `constraint_scopes` ADD COLUMN `suggested_by_model text`、`suggested_run_id text`（仅元数据；置信度复用现有 `confidence` 列）。
  - 不动 `binding_kind` enum；不动 `binding_strategy` enum。
- 更新 ORM `shared/db_schemas.py::ConstraintScope`。
- 更新视图 `v_constraint_bindings`：在 `binding_origin` 行额外暴露 `binding_strategy`、`binding_evidence->>'provider'`，UI 据此判定"LLM 建议"。

**测试**：round-trip；写一行 `binding_kind='inferred'` + `binding_strategy='semantic'` + `binding_evidence={provider:'llm',...}` 能被视图 SELECT 到并标记为 LLM 建议。

**估时**：0.5 天 · **依赖**：T1

---

### T7. constraint_asset_scopes 新表
**改动**
- alembic `0029b_constraint_asset_scopes.py`：镜像 `constraint_scopes` 但 fk → `assets(asset_guid)`。
- ORM + 视图 `v_constraint_asset_bindings`。

**测试**：round-trip + 写入 + 视图查询。

**估时**：0.5 天 · **依赖**：T1

---

### T8. Binder 三层
**改动**
- 新建 `app/services/constraint_binder/`：
  - `regex_match.py`：
    - RDS 码 `^[+\-=][A-Z0-9.]+`（aspect 前缀对应 P/L/F）
    - AO 编号 `AO-\d+`、HB/Q/AS 标准号 `(HB|Q|AS)/?[A-Z]?\s*\d+(\.\d+)*`
    - 设备型号字典（从 `assets` 表 distinct）
  - `vector_match.py`：调 [app/services/llm/embeddings.py](app/services/llm/embeddings.py)，
    `cosine(constraint.rule_expression, hierarchy_node.name_zh + description)` top-k=5，阈值 0.75。
  - `llm_score.py`：把 top-5 候选 + 约束原文喂 LLM，返回 `[{node_id, score 0-1, reason}]`。
  - `binder.py`：编排三层，输出 `list[BindingSuggestion]`。
- 数据流：约束 ID → `BindingSuggestion(node_id|asset_guid, layer, confidence, reason)`。

**测试**
- L0：每层独立单测（regex 用纯字符串、vector/llm 用 stub）；
- L1 gold：`tests/fixtures/binding/ao_001.expected.json` — 4 条 PC-DEMO-* + ao_001 抽出的新约束 → 期望绑定 top-1，gold 通过率 ≥ 80%。

**估时**：2 天 · **依赖**：T5、T6、T7

---

### T9. POST /constraints/{id}/bind 路由
**改动**
- 在 `app/routers/constraints.py` 加：
  ```python
  @router.post("/sites/{site_model_id}/constraints/{constraint_id}/bind",
               response_model=BindResponse)
  def bind_constraint(...): ...
  ```
- 实现：
  1. 拉约束 + 文档证据；
  2. 调 `Binder` 三层，得到 `list[BindingSuggestion]`；
  3. 写 `constraint_scopes` / `constraint_asset_scopes`，`binding_kind='inferred'` + `binding_strategy='semantic'` + `binding_evidence={provider:'llm',...}` + `confidence` + `suggested_by_model` + `suggested_run_id`；
  4. 不动 `is_active`、不动 `review_status`；
  5. 返回写入计数 + suggestions。
- 配套 `PATCH /constraints/{id}/scopes/{scope_id}` 让审核员把 `binding_kind='inferred'` + LLM 来源升级为 `direct`（等同"批准绑定"，并清空 `binding_evidence.provider`）。

**测试**
- E2E：fixture 抽取 → bind → `v_constraint_bindings` 出现 `binding_kind=inferred + binding_strategy=semantic + provider=llm` 行；
- 审核 PATCH 后 `v_active_constraints_at_node` 才出现该绑定。

**估时**：1 天 · **依赖**：T8

**M2 出口**：UI/SQL 上能看到"LLM 建议把约束挂到 S20"，工艺师一键批准。

---

## M3 — KG 门面视图（让 LLM 看的是稳定列）

### T10. 7 个 `kg_*` facade + D4–D7 detail 视图
**改动**
- alembic `0030_kg_facade_views.py`，`CREATE OR REPLACE VIEW`：
  | 视图 | 关键列（≤ 25） |
  |---|---|
  | `kg_node` | node_id, rds_code, aspect, node_kind, name_zh, depth, ancestor_path, site_model_id |
  | `kg_constraint` | constraint_uuid, constraint_id, kind, class, category, severity, authority, conformance, review_status, is_active, weight, priority |
  | `kg_constraint_temporal_now` | constraint_uuid, temporal_status, days_until_expiry, applicable_phases, valid_from, valid_to |
  | `kg_node_capability` | node_id, asset_guid, asset_type, capability_tags[], commissioned_at |
  | `kg_process_edge` | from_op_id, to_op_id, edge_kind, lag_s, takt_min_s, takt_max_s |
  | `kg_node_quality` | node_id, metric, target_value, current_value, measured_at |
  | `kg_constraint_extractions` | process_constraint_id, document_id, page, span_text, span_hash, extractor_kind, llm_model, extracted_at |
- 同时建 detail：`v_asset_at_node`、`v_takt_per_station`、`v_fai_per_station`、`v_constraint_extractions`、`v_constraint_orphan`（approved 但无 scope）。
- 同步更新 `db/views/README.md` 加章节"KG facade 视图"。

**测试**
- 4 个真实业务问题 SQL 跑通：
  1. "S20 现在生效的约束有哪些？" → `SELECT FROM kg_constraint_temporal_now JOIN v_active_constraints_now WHERE rds=...`
  2. "约束 PC-DEMO-PRED-01 的所有抽取证据" → `SELECT FROM kg_constraint_extractions`（curation 后的引用走 `constraint_citations`）
  3. "30 天内将失效的约束" → `kg_constraint_temporal_now WHERE days_until_expiry <=30`
  4. "孤儿约束清单" → `v_constraint_orphan`
- 性能：每个查询 < 100ms（在 demo 数据上）。

**估时**：1.5 天 · **依赖**：T1（evidence 表）、T7（asset_scopes）

**M3 出口**：不接 LLM 也能用纯 SQL 答 4 个真实问题。

---

## M4 — 推理 + 留痕（让 LLM 给决策建议）

### T11. KG Fusion Service
**改动**
- `app/services/kg_fusion/`：
  - `models.py`：`InferenceContext` Pydantic（含 `nodes/constraints/edges/capabilities/evidence` 子集 + `snapshot_at`）。
  - `fusion.py`：`build_context(question_type, params, mcp_context_id) -> InferenceContext`。
  - `templates/`：4 个 SQL 模板（`q_model_change_impact.sql`、`q_bottleneck_audit.sql`、`q_standard_update_impact.sql`、`q_safety_audit.sql`）。
- 硬上限：序列化 JSON > 200KB → 抛 `FusionContextTooLargeError`，调用方降采样。

**测试**：4 个模板各有 fixture 输入 + 期望 row count；性能 < 200ms。

**估时**：1.5 天 · **依赖**：T10

---

### T12. kg_inference_log 表 + 留痕写入
**改动**
- alembic `0031_kg_inference_log.py`：表结构见 `kg_constraint_execution_plan.md §4.2`；
- TimescaleDB 不可用时降级为普通表 + `created_at` BRIN 索引（lite 镜像友好）；
- ORM `KgInferenceLog`。

**测试**：round-trip + 插入 + 按 `observed_at` 区间查询。

**估时**：0.5 天 · **依赖**：T1

---

### T13. DecisionAdvisor Agent
**改动**
- 新建 `agents/decision_advisor/`，按 `agent.json` 注册一个 MCP agent：
  - `service.py`：MCP server，暴露 `inference.advise(question_type, params)`。
  - 内部：调 `KgFusion.build_context` → 喂 LLM（带 system prompt 强制 citation 必须用 `constraint_id`）→ 解析 → 写 `kg_inference_log`。
  - LLM 输出 schema：
    ```python
    class AdvisorOutput(BaseModel):
        summary: str
        risks: list[Risk]                # {level, description, cited_constraint_ids[]}
        recommendations: list[Recommendation]
        citations: list[Citation]        # {constraint_id, span_id?, reason}
        confidence: float
    ```
  - 校验闸口：每条 risk/recommendation 至少 1 个 citation；citation 的 `constraint_id` 必须存在于本次 InferenceContext，否则丢弃 + warning（防幻觉）。
- 注册到 Orchestrator 的 agent 清单。

**测试**
- L0：5 个 question_type 各 1 条 stub 对话；
- L1：3 个 gold 问题，输出关键字段稳定。

**估时**：2 天 · **依赖**：T11、T12

---

### T14. 趋势视图 + 反馈回流
**改动**
- alembic `0032_inference_trend_views.py`：
  - `v_inference_trend_by_type`：按 `question_type × date_trunc('day', observed_at)` 聚合 count + avg(confidence)；
  - `v_constraint_hot`：`unnest(cited_constraints)` 后 group by `constraint_id` 排序 desc；
  - `v_inference_quality`：accept / reject / partial 比例 × `llm_model` × week。
- API：`POST /inferences/{inference_id}/feedback` 写 `user_feedback` 三列；`reject` → 触发 `UPDATE process_constraints SET needs_re_review=true WHERE id = ANY(cited_constraints)`。

**测试**：feedback reject → `needs_re_review` 翻转有断言；30 天数据视图 SELECT < 200ms。

**估时**：1 天 · **依赖**：T12、T13

**M4 出口**：5 个真实问题端到端 → 工艺师能在 UI 给反馈 → 趋势视图能给 PM 看。

---

## 横切（同步推进，不单独排期）

| ID | 内容 | 落点 |
|----|------|------|
| **X1** | `mcp_context_id` 全链路审计 | 每个 Task 验收里检 |
| **X2** | 密级 (`tags.secrecy`) 守卫 | T5 入口、T11 fusion 出口 |
| **X3** | LLM provider stub/openai 双轨 | T4 起 |
| **X4** | L0/L1 测试金字塔达标 | 每个 PR |
| **X5** | 前端 draft 审核页 | T5 完成后立刻起，不等 M2 |

---

## 顺序与并行

```
T1 -> T2 -> T3 -> T4 -> T5  (M1, 串行, ~4.5 天)
                       |
                       +---> T6, T7 (并行, 1 天) -> T8 -> T9 (M2, ~4 天)
                                              |
                                              +-> T10 (M3, 1.5 天)
                                                       |
                                                       +-> T11 -> T12 -> T13 -> T14 (M4, ~5 天)
                       |
                       +---> X5 前端审核页 (与 M2 并行)
```

**总估时**：~15 人日（理想）；带 buffer 约 4 周历日（考虑评审、调 prompt、跨型号 fixture 准备）。

---

## 待审核条目（请逐条 ack）

1. ✅ / ❌ — Task 拆分粒度合适？
2. ✅ / ❌ — Sprint 顺序 M1→M2→M3→M4？
3. ✅ / ❌ — `kg_*` 门面视图前缀命名？
4. ✅ — `constraint_extractions` 用独立表（不挤进 `process_constraints`），且与 0016 `constraint_citations` 形成两层证据模型（process 层 vs curation 层）。
5. ✅ / ❌ — `kg_inference_log` 用 hypertable + 大快照外移 MinIO（T12 是否要先做 MinIO）？
6. ✅ / ❌ — X5 前端审核页要在 T5 之后立即开，还是放到 M2 末尾？

ack 之后我从 **T1** 开干。
