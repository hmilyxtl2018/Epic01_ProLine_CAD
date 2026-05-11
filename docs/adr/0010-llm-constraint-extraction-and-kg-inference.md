# ADR-0010 · LLM 约束抽取 + 知识图谱推理留痕

- **Status**: Proposed
- **Date**: 2026-05-11
- **Driver**: 把"工艺文档 → 数字约束 → 实体绑定 → LLM 决策建议"全链路打通，且每一步都可审计、可回放、可反馈。
- **Related**: [ADR-0005 ConstraintSet Schema](./0005-constraint-set-schema.md) · [ADR-0006 Constraint Evidence & Authority](./0006-constraint-evidence-authority.md) · [ADR-0009 时空约束本体](./0009-spacetime-constraint-ontology.md)
- **Supersedes**: 无（在 0006 / 0009 之上加层）
- **Detail Plan**: [docs/kg_constraint_execution_plan.md](../kg_constraint_execution_plan.md) · [docs/kg_execution_tasks_v1.md](../kg_execution_tasks_v1.md)

---

## 1. Context

### 1.1 目标场景

沈飞集团飞机装配产线。现有数字约束依赖工艺师手动录入，**两个瓶颈**：

| 瓶颈 | 现象 | 后果 |
|---|---|---|
| 抽取效率 | AO/MBD/标准/EHS 文档量级 10⁴ 页，每页 1–5 条规则 | 手工录入 < 1% 覆盖率 |
| 绑定质量 | 一条约束可能命中多个工位/资产，靠工艺师"看名字猜" | 误绑导致下游布局/仿真失真 |

### 1.2 既有能力（不重复造）

- **0016 `constraint_sources` + `constraint_citations`**：策展级证据。**人工**或**审核后**确认的"约束 ↔ 标准条款"M:N 引用，含 `quote/confidence/derivation/reviewed_at_version`。
- **0009 `hierarchy_nodes` + `constraint_scopes`**：约束 ↔ 节点 N:M 绑定，含 `binding_strategy ∈ {explicit_id, asset_type, semantic, manual}`、`inherit_to_descendants`、`confidence`。
- **0024 时间维度**：`process_constraints.applicable_phases / valid_from / valid_to`。
- **0025–0027 视图**：`v_active_constraints_at_node`、`v_constraint_temporal`、`v_active_constraints_now` 等。
- **app/services/llm/provider.py**：`LLMClient` 抽象 + stub/openai 双 provider。

### 1.3 缺口

| 缺口 | 影响 |
|---|---|
| LLM 抽取过程的**原始 span 痕迹**无处可放 | 不能回放 / 不能与 prompt 版本对齐 / 不能证明引用未被编造 |
| `constraint_scopes.binding_strategy` 没有 `suggested_by_llm` 一档 | LLM 推断的绑定不能写入，强写会污染人工绑定的统计口径 |
| 无 KG 门面视图 | LLM 直接读底表/JOIN，列爆炸、易幻觉 |
| 无推理留痕 | 同一问题不同时间答案不同，无法做趋势 / 反馈不能闭环 |
| 多段证据共证一约束 | 0016 `constraint_citations` 设计是策展引用；不适合一次抽取产生 5 个原始 span 这种"过程数据" |

---

## 2. Decision

### 2.1 分层证据模型（关键决策）

引入**两层证据**，职责分离：

| 层 | 表 | 谁写 | 语义 | 何时升级 |
|---|---|------|------|---------|
| **过程层** | `constraint_extractions`（本 ADR 新建） | 抽取服务（LLM/regex）自动写 | 原始抽取 span：哪段文本、哪个 chunk、用了哪个 prompt 版本、置信度多少 | — |
| **策展层** | `constraint_citations`（0016 已存在） | 工艺师审核后确认（或服务在 review_status='approved' 时自动 promote） | 已确认的"约束 ↔ 标准条款"引用 | 抽取被 approve 时由服务/触发器登记 |

**论据**：审计学上"原始证据"和"已策展证据"必须分层；混在一张表会让"未审 / 已审"语义混乱，0016 的 `reviewed_at_version` 也会错位。

### 2.2 LLM 抽取的写入契约

1. LLM 抽取写入 **永远 `parse_method='LLM_EXTRACT'`、`review_status='draft'`、`is_active=false`**；
2. 同时写 ≥ 1 条 `constraint_extractions` 行，含 `span_hash = sha256(span_text)`，服务层校验 `span_text` 必须能在原文 chunk 命中（防 LLM 编造引用）；
3. 整个抽取过程链路上一个 `mcp_context_id`，所有相关行 FK 指向它；
4. 抽取服务**不写** `constraint_scopes`、**不写** `constraint_citations` —— 各自由 M2 / 审核流程负责。

### 2.3 LLM 绑定的写入契约（M2 由 ADR-0010 引出，DDL 在 0029）

`constraint_scopes.binding_strategy` 不扩 ENUM；用 `binding_evidence` JSONB 字段携带 `{"provider": "llm", "model": "gpt-4o", "score": 0.78, "candidates": [...]}`；同时**所有 LLM 绑定一律 `binding_strategy='semantic'`**，与既有 enum 兼容。CHECK 约束 `ck_cscope_manual_verified` 自然把"未审 LLM 绑定"挡在 manual 之外。

> 这里和 v1 任务计划草案不同。原计划想加 enum 值 `suggested_by_llm`，但 PG enum 加值需要跨事务且无法 downgrade，复用 `semantic` + JSONB evidence 更稳。**改动落地在 T6**，本 ADR 提前固化。

### 2.4 KG 门面视图前缀

新建视图前缀 `kg_*` 为 LLM/RAG 入口，列 ≤ 25 稳定；现有 `v_*` 视图保留为数据架构师用细节视图。

### 2.5 推理留痕表

新建 `kg_inference_log`（M4 / alembic 0031），用 TimescaleDB hypertable 按 `inferred_at` 分区；超 100KB 的 `input_context_snapshot` 外移 MinIO，表里只留 URL + hash。

---

## 3. `constraint_extractions` 表（本 ADR 立 schema，由 alembic 0028 落地）

| 列 | 类型 | 约束 | 说明 |
|---|------|------|------|
| `id` | UUID | PK, default `gen_random_uuid()` | |
| `process_constraint_id` | UUID | NOT NULL, FK → `process_constraints(id)` ON DELETE CASCADE | 一条约束可有多条抽取（多段共证） |
| `document_id` | TEXT | NOT NULL | 与 `process_constraints.source_document_id` 同源 |
| `chunk_id` | TEXT | NULL | 抽取服务的 chunk 标识（可选） |
| `page` | INT | NULL, CHECK ≥ 0 | |
| `char_start` | INT | NULL, CHECK ≥ 0 | |
| `char_end` | INT | NULL, CHECK > `char_start` | |
| `span_text` | TEXT | NOT NULL, CHECK length ≤ 1000 | 原文截取 |
| `span_hash` | TEXT | NOT NULL, CHECK ~ '^[0-9a-f]{64}$' | sha256(span_text)，用于防伪 + 去重 |
| `extractor_kind` | VARCHAR(20) | NOT NULL, CHECK ∈ `('llm','regex','manual_ui','imported')` | |
| `llm_model` | VARCHAR(60) | NULL | `extractor_kind='llm'` 时必填（CHECK） |
| `prompt_version` | VARCHAR(40) | NULL | 同上必填条件 |
| `extraction_run_id` | TEXT | NULL | 一次批量抽取的 run id（同一调用产出多行可关联） |
| `extraction_confidence` | NUMERIC(3,2) | NULL, CHECK 0..1 | LLM 自报 confidence |
| `extraction_payload` | JSONB | NOT NULL DEFAULT `'{}'::jsonb`, CHECK `jsonb_typeof = 'object'` | 原始 LLM 输出 / 中间产物 |
| `extracted_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | |
| `mcp_context_id` | VARCHAR(100) | FK → `mcp_contexts(mcp_context_id)` | |
| `schema_version` | SMALLINT | NOT NULL DEFAULT 1 | |
| `deleted_at` | TIMESTAMPTZ | NULL | 软删 |

**索引**

- `idx_ce_constraint` ON `(process_constraint_id)` WHERE `deleted_at IS NULL`
- `idx_ce_document` ON `(document_id, page)` WHERE `deleted_at IS NULL`
- `idx_ce_run` ON `(extraction_run_id)` WHERE `extraction_run_id IS NOT NULL`
- `uq_ce_hash_per_constraint` UNIQUE `(process_constraint_id, span_hash)` WHERE `deleted_at IS NULL` — 同一约束同一 span 抽两次只算一次

**CHECK 复合约束**

- `ck_ce_llm_metadata`：`extractor_kind <> 'llm' OR (llm_model IS NOT NULL AND prompt_version IS NOT NULL)`
- `ck_ce_span_range`：`char_end IS NULL OR char_start IS NULL OR char_end > char_start`

---

## 4. Consequences

### 4.1 Positive

- 抽取过程 100% 可回放：`prompt_version + llm_model + extraction_payload` 可以重建当时调用。
- 反幻觉：`span_hash` + 服务层"span 必须在原文出现"的双校验。
- 不污染策展层：`constraint_citations` 仍然只装"已审" / "已策展"引用，0016 的 `reviewed_at_version` 语义保持。
- 多段共证天然支持：1 约束 N 抽取 OK。
- 与 0029（绑定 LLM 痕迹走 `binding_evidence` JSONB）形成对偶设计，全部 LLM 痕迹都通过现有 enum + 旁路 JSON 表达，不爆 enum。

### 4.2 Negative / Trade-offs

- 又多 1 张表，写入变成 2 行（`process_constraints` + `constraint_extractions`）。**缓解**：抽取服务 (T4) 封装事务，外部调用方仍是 1 个 API。
- "审核 approve 自动 promote 到 `constraint_citations`"需要 source_id 存在；如果文档还未策展进 `constraint_sources`，promote 会失败。**缓解**：T5 在抽取入口可选 ensure-or-create 一条 `constraint_sources(source_id='src_doc_<doc_id>', authority='heuristic')`，让自动 promote 总能落地；正式标准条款由人工后续替换。
- `extraction_payload` JSONB 可能很大。**缓解**：长度 > 50 KB 时服务层切到 MinIO，表里只存 URL + sha256（与 4.5 节策略一致）。

### 4.3 Migration / Rollback

- `alembic upgrade head` 一次性建表；
- `alembic downgrade -1` `DROP TABLE constraint_extractions CASCADE`，0027 视图不受影响；
- 现有 4 条 `PC-DEMO-*` 数据不受影响，未来可补 backfill 把它们的 `source_span` 同步进新表（不在本 ADR 范围）。

### 4.4 Test Coverage（本 ADR 落地的最小集）

L0 schema/contract（≥ 8 条）：
- 表存在 + 4 个索引存在 + 5 个 CHECK 存在
- FK 级联：删除 process_constraint 自动删 extractions
- `span_hash` 格式校验
- `extractor_kind='llm'` 时 `llm_model/prompt_version` 必填
- `uq_ce_hash_per_constraint` 同一约束同一 hash 二次插入失败
- `extraction_payload` 必须是 object
- round-trip：`alembic downgrade -1 && upgrade head` 干净

### 4.5 与本 ADR 不冲突的未来扩展

- 5 表 / 视图列表后续随 M2/M3/M4 各自 ADR 增补：本 ADR 只立 §3 的 `constraint_extractions`。
- `kg_inference_log` 用 TimescaleDB hypertable 由 ADR-0011（M4 时再写）固化，**不在本 ADR**。

---

## 5. Open Questions（本 ADR 不阻塞合并，跟踪到 v1.1）

1. promote 到 `constraint_citations` 由 service 显式做，还是 PG 触发器？倾向 service，便于错误处理。
2. `extraction_payload` MinIO 外移阈值是 50KB 还是 200KB？跟 `kg_inference_log` 对齐，待 ADR-0011 一起定。
3. 同一 span 被两个不同 prompt_version 抽出来 → `uq_ce_hash_per_constraint` 会拒第二条。这是 feature（去重），还是 bug（应保留 prompt 历史）？倾向加 `prompt_version` 进 unique key，但暂保守不加。

---

## 6. Decision Log

| 日期 | 决策 | 由 |
|------|------|---|
| 2026-05-11 | 起草 v1 | proline-cad-team |
