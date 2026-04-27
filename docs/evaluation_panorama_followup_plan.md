# Evaluation Panorama — 后续 PR 接入计划

> 现状：本 PR 落地了 **schema (0017/0018) + Pydantic Asset 字段 + 顶部 Banner UI**，  
> 但是 ParseAgent 还**没有真正写入** `run_evaluations` 表 — 因此 Banner 当前显示 **派生值**（标小标 `派生`），  
> 不是 DB 物化值。本文件列出把 Banner 切换到"DB 直读"所需的 4 个后续小 PR。
>
> 参考：
> - `ExcPlan/parse_agent_evaluation_dimensions.md` 5/4/4/§5
> - `db/alembic/versions/0017_asset_provenance_extension.py`
> - `db/alembic/versions/0018_run_evaluations.py`
> - `web/src/components/sites/EvaluationPanorama.tsx`

## PR-A · ParseAgent 写 D5 字段（≈ 2 h）

**目标**：每条 `Asset` 出仓时带齐 `classifier_kind` / `source_entity_id` / `evidence_keywords`。

- `agents/parse_agent/agents.py` (asset 创建处) — 在每个分类分支末尾写 `classifier_kind`：
  - block-name 命中 → `"rule_block"`
  - layer 命中 → `"rule_layer"`
  - 几何特征命中 → `"rule_geom"`
  - 频次/启发式 → `"heuristic"` / `"heuristic.frequency"`
  - LLM 兜底 → `"llm_fallback"`（同时要求 `evidence_keywords ⊆ input_tokens`，不满足时
    rollback 到 `"heuristic"` + `Other`）
- `agents/parse_agent/persistence.py`（`asset_geometries` insert/upsert）— 把上述 3 个字段
  也写到 DB 列。  
  → 0017 已建好，列名一一对应。
- 新增测试：`tests/parse_agent/test_classifier_kind_distribution.py`
  - 用 `tests/fixtures/dxf/sample_factory.dxf` 跑一次解析，断言每个 asset 的 `classifier_kind`
    都不是 None，并断言 LLM-fallback 的 `evidence_keywords` 不为空。

## PR-B · ParseAgent finalize 写 `run_evaluations`（≈ 3 h）

**目标**：解析尾段 UPSERT 一行 D1–D5 + G1 + H1–H4 + reinforcement，让 Banner 不再"派生"。

- 新文件 `agents/parse_agent/finalize.py`：
  - 入口签名 `def finalize(run_ctx: ParseAgentContext) -> None`，由 `agents.py` 主流程末尾调用。
  - D1：复用 `geometry_integrity_score`。
  - D2：从 `enrichment.sections.F_quality_breakdown.semantic` 读取，缺失则按
    `len(matched_terms) / (len(matched_terms)+len(quarantine))` 兜底。
  - D3：留 `None`（ParseAgent v1.0 不出关系）。
  - D4：`bool(site_model_id) and not error_message`。
  - D5：`sum(1 for a in assets if a.classifier_kind and a.evidence_keywords is not None) / len(assets)`。
  - G1：`schema_pass = True`（能跑到 finalize 即通过 pydantic）。
  - H1–H4：`Counter([a.classifier_kind for a in assets])` 投影到 4 阶。
  - reinforcement：4-key dict，按 §5 计算（`sub_type_field=ok`、其余按当前缺口给 warn/fail）。
  - overall_score / should_block / block_reasons：按本 PR 中
    `EvaluationPanorama.deriveFromEnrichment` 同样的公式（保持一致）。
  - SQL：`INSERT … ON CONFLICT (mcp_context_id) DO UPDATE SET …`。

- 新增测试 `tests/parse_agent/test_finalize_writes_run_evaluation.py`：
  - 跑端到端解析 → 断言 `SELECT * FROM run_evaluations WHERE mcp_context_id=?`
    返回唯一一行，且 D5 ≥ 0.9（fixture 应该全部带 provenance）。

## PR-C · `/dashboard/runs/{id}/eval` API + 前端类型（≈ 2 h）

**目标**：前端从 API 拿到结构化 `RunEvaluation`，去掉派生兜底。

- `app/api/dashboard.py` 新增路由：
  ```python
  @router.get("/runs/{run_id}/eval")
  def get_run_eval(run_id: str) -> RunEvaluationOut: ...
  ```
  - 直接 `SELECT * FROM run_evaluations WHERE mcp_context_id = :run_id`，
    `404` 时回退 `None`（让前端继续走派生兜底而不是炸）。
- `app/api/schemas.py` 加 `RunEvaluationOut` Pydantic（与
  `EvaluationPanorama.tsx::RunEvaluation` 完全对齐）。
- `web/src/lib/types.ts` 把 `evaluation?: RunEvaluation | null` 加到 `RunDetail`，
  并在 `api.getRun` 里 `Promise.allSettled([detail, eval])` 合并。
- `EvaluationPanorama` 已经按这个契约写好 — **PR-C 落地后 Banner 自动切换到 DB 路径**，
  小标 `派生` 自动消失。

## PR-D · `gold_eval.py` 写 G2 + `link_precision` reinforcement（≈ 4 h）

**目标**：CI/PR 跑后把 G2 写回，`Banner` 第二行变绿。

- `scripts/gold_eval.py` 新增：
  - 读 `tests/fixtures/gold/parse_agent_v1.jsonl`（gold 数据集）；
  - 跑 ParseAgent → 比对 → 计算 `strict_acc` / `recall` / `range_pass`；
  - `UPDATE run_evaluations SET g2_gold_score = :score, reinforcement = jsonb_set(reinforcement, '{link_precision}', :status) WHERE mcp_context_id = :ctx`。
- 新增 GitHub Actions `.github/workflows/gold_eval.yml` — `on: pull_request`，
  跑 `pytest -m gold` + `python scripts/gold_eval.py --upsert`，PR 评论里输出 G2 数值。

---

## 把 TrustTokenCard 从 3 维升到 5 维（可顺手做）

`web/src/app/sites/[runId]/page.tsx::TrustTokenCard` 当前展示 解析/语义/完整 三格。  
PR-C 后建议把它替换为 5 维 mini 进度条，与 Panorama 顶条 1:1 对齐，避免两套口径。  
最小改动版（无需改 API）：把 `TrustTokenCard` 删除，让右栏只保留 `SelectedObjectCard`
+ `AISuggestionCard` + `EventLogCard`，避免重复信息。

---

## 决策点回顾（已用方案）

| #  | 决策点                | 选择                                                                   |
| -- | --------------------- | ---------------------------------------------------------------------- |
| D1 | 评估表 vs JSON 内嵌   | **独立 `run_evaluations` 表**（0018） — JSONB 留作 source of truth，列表化便于查询 / 索引 |
| D2 | provenance 列归属    | **`asset_geometries` 加 3 列**（0017） — 不新建 `assets` 表，避免 schema 分裂        |
| D3 | UI 顶条还是浮窗       | **顶部 Banner**（`EvaluationPanorama`） — 进入 S1 即可见，3 秒判定           |
| D4 | 派生 vs DB 直读        | **现阶段派生 + 派生小标**；PR-C 完成后无缝切到 DB                          |
