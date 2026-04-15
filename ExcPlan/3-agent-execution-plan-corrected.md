
# 工艺产线 Multi-Agent 协同系统 — 完整执行计划（修正版）

版本: v1.1  
生成日期: 2026-04-15  
基线案例: 航空蒙皮装配产线 FAL（wing_fal.dwg）

---

## 说明与目的

本文件为三 Agent（ParseAgent / ConstraintAgent / LayoutAgent）产线闭环系统的完整可执行实现计划（修正版）。文档修正并统一了之前计划中的数值、术语与可验证性约定，补充了 LLM 与 MCP（Model Context Protocol）之间的受控交互设计、Tool 调用示例、收敛规则和监控指标，以便工程团队直接依此落地实现与验收。

本版本重点修正项包括：评分算术、指标命名、authority 标注、Z3 编码建议、JSON 示例格式以及文档完整性。

---

## 主要修正清单（重要错误与修正建议）

1. 评分计算修正
   - 原示例：score(A) = 0.40×1.0 + 0.30×0.92 + 0.20×0.85 + 0.10×0.80 = 0.92
   - 修正：0.4*1.00 + 0.3*0.92 + 0.2*0.85 + 0.1*0.80 = 0.926 ≈ 0.93（保留两位小数显示）
   - 建议：统一评分显示为两位小数并在评分处声明四舍五入规则（round half up）。

2. 指标命名与定义一致化
   - 将“物流路径利用率（utilization）”与“物流流畅性（smoothness）”区分并定义计算公式；若为同一指标则使用同一名称与同一数值来源。
   - 建议在指标表中明确每一项的计算方式、单位和时间窗口。

3. Authority 标注修正
   - 不应把 LLM 当作规范“authority”。修正为：`authority: SOP (document)`，并在 metadata 中加入 `translator_tool: LLM (mcp_context_id: ...)`。
   - LLM 仅作为辅助的“翻译器 / 解释器 / 建议生成器”。

4. Z3 约束编码建议（避免非线性表达）
   - 避免直接在 Z3 中使用 sqrt 或开方表达式（易引入非线性问题）。  
   - 推荐做法：
     - 在几何引擎中做距离计算并以布尔事实提供给 Z3；或
     - 使用平方比较（(dx)^2 + (dy)^2 >= R^2）并注意可能导致非线性；或
     - 使用 conservative linearization / axis-aligned bounds（例如 |dx| >= R 或 |dy| >= R 的近似）或引入辅助变量与分段线性化。

5. 修复 JSON / 文档完整性与截断
   - 补全之前被截断的 Stage 5 后续内容，并确保所有 JSON 示例为有效示例或清楚声明为伪 JSON。

6. 其他优化建议
   - mcp_context 输出中保存 proof artifact 的存储路径（S3 URL）；LLM 输出若 confidence < threshold 自动进入人工复核；Z3 超时策略明确并有 fallback。

---

## 一、总体目标与范围

目标：构建生产就绪的三 Agent 闭环系统，实现 CAD 导入 → 本体识别 → 约束检查 → 布局优化 → 审批闭环，满足可审计、可验证与可扩展性要求。

范围：
- ParseAgent：CAD → SiteModel + Ontology Graph（JSON-LD）
- ConstraintAgent：规则加载 → Z3 验证 → 违例/评分输出
- LayoutAgent：约束驱动的布局搜索与 TopK 推荐（GA + R-Tree）
- Orchestrator、MCP Toolbelt、AuditStore、LLM integration、基础 UI（演示级）

成功衡量标准（DoD）：
- 三 Agent 单元与集成测试通过
- 端到端演示（sample CAD）在 10 分钟内完成（目标 8 分钟）
- 硬约束检出率 100%，假阳性率 < 0.2%
- mcp_context 链路完整且可检索 proof artifacts

---

## 二、系统架构与关键组件一览（最小实现）

- Kubernetes 集群（生产/测试命名空间）
- Postgres（SiteModel、mcp_contexts）
- GraphDB（Ontology JSON-LD / RDF）
- Vector DB（Milvus/FAISS，用于 SOP 段落检索）
- S3/MinIO（Audit / proof artifacts / PDFs）
- Kafka/RabbitMQ（Agent 间消息总线）
- z3-solver（SMT 求解）
- CAD 解析库（IfcOpenShell / Teigha / STEP parser）
- Geometry libs（libspatialindex / CGAL）
- LLM 服务（托管或私有部署）
- Agents: ParseAgent, ConstraintAgent, LayoutAgent（各自容器化）
- Orchestrator：流程、重试、超时、审计

MCP Toolbelt（受控功能性工具）：
- /mcp/tool/constraint_translate (LLM-assisted)  
- /mcp/tool/validate_with_z3 (Z3 gateway)  
- /mcp/tool/generate_fix_suggestions (Rule + LLM)  
- /mcp/tool/optimize_layout (LayoutAgent entry)  
- /mcp/tool/retrieve_sop (Vector retriever)  
- /mcp/tool/publish_audit_record (AuditStore)  

每个 Tool 必须返回 new_mcp_context_id、provenance（tool_version、input_sha256）、latency_ms，并写入 AuditStore。

---

## 三、分阶段执行计划（推荐 10–12 周）

阶段划分以 Sprint 为单位（2 周 / sprint）

阶段 0：准备与发现（Week 0–1）
- 收集 5–10 个 CAD 样本（不同格式/规模）并建立回归测试集
- 定义约束库 (CS-001) 的初始条目（PRD-3、SOP、HB/Z）并版本化
- 搭建初步 K8s、Postgres、S3 基础设施

阶段 1：基础设施与 MCP Toolbelt（Week 2）
- 部署 Postgres、GraphDB、Milvus、S3、Kafka
- 实现 AuditStore（S3 + DB）与 mcp_context schema
- 实现 SOP 段落向量化与检索接口（/mcp/tool/retrieve_sop）

阶段 2：ParseAgent（Week 3–4）
- CAD parser、geometry repair、coordinate normalization
- Asset recognition + confidence scoring
- Ontology graph (JSON-LD) 生成并入 GraphDB
- SiteModel persistence + mcp_context generation

收敛与验收（ParseAgent）:
- avg_confidence >= 0.90 或 low_confidence_ratio <= 0.05
- geometry_integrity_score >= 0.85
- p95_latency <= 5s（样本基线）

阶段 3：ConstraintAgent（Week 5–6）
- ConstraintLoader、RuleEngine、Z3 gateway (SolverInvoker)
- Soft scoring implementation
- LLM-assisted ConstraintTranslator 接口（/mcp/tool/constraint_translate）
- Violation report + reasoning chain output

收敛与验收（ConstraintAgent）:
- 硬约束检出率 100%（测试集）
- Z3 solve time p95 <= 2s（中小模型）
- LLM→Z3 一致率 >= 95%

阶段 4：LayoutAgent（Week 7–8）
- SearchCoordinator (GA)、R-Tree collision check
- Candidate generation (1,000+), scoring, Z3 verification
- Top3 export + reasoning chain

收敛与验收（LayoutAgent）:
- 找到至少一个满足所有硬约束的方案或到达 max_generations
- Top plan score >= 0.80（目标 >= 0.90 强烈推荐）
- GA 收敛判定：连续 N 代 TopScore 增益 < delta（举例 N=3, delta=0.005）

阶段 5：Orchestrator、LLM integration、UI（Week 9–10）
- Orchestrator：workflow、retry、timeout、mcp_context linkage
- LLM tool-calling adapter、prompt 模板、hallucination detector
- 前端 Demo（CAD upload, ontology view, Top3 compare, approve/export PDF）

阶段 6：测试、性能优化与部署（Week 11）
- 单元、集成、回归、性能测试；Z3 stress tests
- CI/CD、Helm charts、staging 部署

阶段 7：交付与培训（Week 12）
- UAT、用户培训、交付文档与维护手册

MVP（4–6 周快速版）建议：
- 支持少量 DWG 输入（small），ParseAgent 基本识别 + ConstraintAgent 支持 5 个硬约束 + LayoutAgent 简单 heuristic optimizer + 简单 Orchestrator 与 UI。

---

## 四、Action Flow（每个 Agent 的详细步骤）

ParseAgent（本体识别）
- 输入：cad_file (ref or base64)、format、options
- Steps:
  1. format_detect()
  2. entity_extract() -> build spatial index (R-Tree)
  3. coord_normalize() -> WCS/UCS, units to mm
  4. topology_repair() -> close polylines, remove duplicates
  5. classify_entity() -> ontology mapping with layer mapping + heuristics
  6. extract_ports_and_keypoints()
  7. confidence_scoring()
  8. serialize_site_model() -> persist + mcp_context output
- Convergence:
  - unrecognized_ratio < 0.05 AND avg_confidence >= 0.90 AND geometry_integrity_score >= 0.85
  - On fail: mark NEED_REVIEW, push to HumanReviewQueue

ConstraintAgent（约束检查）
- 输入：site_model_id、constraint_set_id
- Steps:
  1. load_constraint_set()
  2. (LLM-assisted) constraint_translate() for natural language constraints
  3. encode_constraints_for_z3() (avoid non-linear expressions)
  4. solver_invoke() -> z3.check()
  5. extract_unsat_core_if_unSAT()
  6. compute_soft_scores()
  7. generate_violation_report() -> mcp_context output
- Convergence:
  - Z3 returns SAT or provides UNSAT core and produce fix suggestions
  - Max automated translation/validation loops = 3; beyond that escalate to human

LayoutAgent（布局优化）
- 输入：violations, soft_targets, site_model_id
- Steps:
  1. build_search_space() (parameter ranges)
  2. initialize_population() (random + LLM heuristics)
  3. run_ga_with_collision_checks() (R-Tree)
  4. evaluate_candidates() -> score (weighted)
  5. z3_verify_top_candidates()
  6. output_top_k_with_reasoning()
- Convergence:
  - Stop when: existence of candidate with all hard constraints satisfied AND score >= strong_threshold
  - Or when: TopScore improvement < delta for N consecutive generations OR time budget reached
  - Default params example: population=100, generations=50, delta=0.005, N=3, max_time=300s

---

## 五、LLM 在 Action Flow 中的定位（何时用 LLM 更合适）

适合 LLM 的任务
- 将自然语言 SOP / 标准段落翻译为结构化约束（ConstraintTranslator）
- 解释低置信度资产的可能原因并生成复核指令（Human-in-the-loop 文本）
- 生成可审计的 Reasoning Chain（人类可读步骤说明 + 规范引用）
- 为优化器生成启发式参数（初始种群构建、变异率、局部搜索提示）
- 生成审批文档、决策摘要、与用户对话问答

不适合 LLM 的任务
- 精确几何计算（碰撞检测、距离计算）
- 最终的合规决策（必须基于 Z3 等 deterministic solver 的证据）
- 高频低延迟的自动控制逻辑

LLM 使用原则
- 所有 LLM 输出必须为结构化 JSON（不可只依赖自由文本）并带 citations 与 confidence 字段
- LLM 输出必须走到 deterministic tool（Z3 / geometry engine / optimizer）进行验证，验证结果与 proof artifact 必须写回 AuditStore
- 限制自动重试次数（示例：LLM-assisted translation 最大 3 次自动迭代）
- 对 LLM 引用的不在系统中的 source_id 或 asset_guid，自动标记为 hallucination 并 reject

---

## 六、MCP Tool 调用示例（请求/响应示例）

注意：以下示例为结构化 JSON（示例）且每次调用均返回 new_mcp_context_id。

1) ConstraintTranslator（LLM-assisted）
- Request
```json
POST /mcp/tool/constraint_translate
{
  "parent_mcp_context_id": "ctx-7f3a-4e81-b2c9-001",
  "sop_segments": ["sop_seg_00012", "sop_seg_00013"],
  "scope_assets": ["MDI-2024-001", "MDI-2024-002"],
  "ontology_version": "AeroOntology-v1.0"
}
```
- Response
```json
{
  "mcp_context_id": "ctx-ct-0001",
  "formal_constraints": [
    {
      "constraint_id": "C-001",
      "expr": "dist(MDI-2024-001, MDI-2024-002) >= 500",
      "source": {"doc_id": "PRD-3", "section": "2.1.4", "snippet_id": "seg_34"},
      "confidence": 0.93
    }
  ],
  "citations": ["PRD-3:2.1.4:seg_34"],
  "latency_ms": 420,
  "tool_version": "constraint-translator-v1.0"
}
```

2) Validate with Z3 (SolverInvoker)
- Request
```json
POST /mcp/tool/validate_with_z3
{
  "parent_mcp_context_id": "ctx-ct-0001",
  "site_model_id": "SM-001",
  "formal_constraints": ["C-001"]
}
```
- Response (UNSAT example)
```json
{
  "mcp_context_id": "ctx-z3-0001",
  "sat_result": "UNSAT",
  "unsat_core": ["C-001"],
  "proof_artifact_url": "s3://audit/proofs/ctx-z3-0001.smt2",
  "latency_ms": 850
}
```
- Implementation note: Avoid using sqrt in SMT expressions; prefer precomputed geometry facts or squared-distance comparisons only where solver support is adequate.

3) Generate Fix Suggestions (Rule-based + LLM)
- Request
```json
POST /mcp/tool/generate_fix_suggestions
{
  "parent_mcp_context_id": "ctx-z3-0001",
  "unsat_core": ["C-001"],
  "search_hints": {"allow_move": true, "max_move_mm": 100}
}
```
- Response
```json
{
  "mcp_context_id": "ctx-sugg-0001",
  "suggestions": [
    {"action": "move", "target": "MDI-2024-002", "dx_mm": 0, "dy_mm": 35, "dz_mm": 0, "est_score": 0.926}
  ],
  "latency_ms": 320
}
```

4) Optimize Layout (LayoutAgent)
- Request
```json
POST /mcp/tool/optimize_layout
{
  "parent_mcp_context_id": "ctx-sugg-0001",
  "site_model_id": "SM-001",
  "violations": ["C-001"],
  "soft_targets": ["C-045"],
  "search_space_size": 1000
}
```
- Response
```json
{
  "mcp_context_id": "ctx-layout-0001",
  "candidates_count": 3,
  "best_plan_id": "Plan-A",
  "candidates": [
    {"plan_id":"Plan-A","score":0.93,"hard_pass": true,"adjustments":[{"asset":"MDI-2024-002","dx":0,"dy":35}]},
    {"plan_id":"Plan-B","score":0.78,"hard_pass": true},
    {"plan_id":"Plan-C","score":0.65,"hard_pass": false}
  ],
  "reasoning_chain": [...],
  "latency_ms": 3120
}
```

注意：所有返回的 mcp_context_id 都应写入 AuditStore，并且 proof_artifact_url（如有）应可直接下载用于审计。

---

## 七、收敛规则（Agent 与 LLM-involved 操作）

统一约定：每个 mcp_context 中须包含 parent_mcp_context_id，tool_version，input_sha256，timestamp，latency_ms，status（SUCCESS/FAIL/REVIEW）。

ParseAgent 收敛准则
- 完成条件（SUCCESS）:
  - unrecognized_ratio < 0.05
  - avg_confidence >= 0.90
  - geometry_integrity_score >= 0.85
  - total_latency_ms <= 8000ms（SLO）
- SUCCESS_WITH_WARNINGS: 若 low_confidence_items ≤ 2 且不影响关键约束，仍可继续；同时生成 HumanReviewTicket
- FAILURE: 格式不支持或几何严重损坏（需人工介入）

ConstraintAgent 收敛准则
- 对每一项 LLM 生成的 formal_constraint 调用 Z3 验证（validate_with_z3）
- 自动循环次数上限：3（constraint_translate → validate_with_z3 → refine）
- 若 Z3 给出 UNSAT，必须产出 UNSAT core 与至少一条可行的修复 suggestion（或分解子问题）
- 若超过自动循环次数或 Z3 超时（configurable, e.g., 10s），产生 HumanReviewTicket

LayoutAgent 收敛准则
- 提前终止条件（accept）:
  - 发现 candidate 满足所有硬约束 AND score >= strong_threshold (e.g., 0.90)
- 收敛判定（GA）:
  - TopScore 增益 < delta (e.g., 0.005) for N consecutive generations (e.g., N=3)
  - 或达 max_generations / time budget
- 若达到 max_time 或 max_generations 仍无可行解，则返回当前 TopK 标注 "未收敛" 并建议 human intervention

LLM-involved 操作收敛与治理
- 对 LLM 输出的结构化产物，必须经 deterministic tools 验证（Z3/geometry）
- LLM 自动迭代上限（per mcp_context）: 3 次；超出需人工签发
- Hallucination controls:
  - 验证 citations 是否存在于 Retriever DB；若不存在，reject 并标注 hallucination_event
  - 验证 asset_guid 是否在 site_model 中存在

---

## 八、监控指标（建议）

基础可观测指标
- Agent latencies: p50/p95/p99 for ParseAgent / ConstraintAgent / LayoutAgent
- mcp_context creation rate and completeness (fraction with all required fields)
- Z3 metrics: solve_time distribution, timeout_rate, unsat_core_size distribution
- Optimizer metrics: generation_count, average_fitness, convergence_time
- LLM metrics: calls/sec, avg tokens per call, hallucination_rate, LLM→Z3 consistency_rate
- AuditStore: proof_artifacts saved, download_count, retention status

SLO 示例
- ParseAgent: p95_latency < 5s
- ConstraintAgent: p95_latency < 3s (small models)
- LayoutAgent: p95_latency < 6s (search_space ~1000)
- End-to-end: typical run < 10 min (target 8 min)

Alerting/Alarms
- Z3 timeout rate > X% → alert (possible unsolvable constraints or scaling issue)
- LLM hallucination_rate > Y% → stop auto LLM workflows and require prompt tuning
- Any Agent ERROR rate spike > baseline → page on-call engineer

---

## 九、接口契约与样例（快速参考）

API Endpoints (示例)
- POST /api/import_cad {file_ref} → returns {mcp_context_id, site_model_id}
- POST /mcp/agent/parse {site_model_ref} → ParseAgent output (mcp_context)
- POST /mcp/agent/constraint/check {site_model_id, constraint_set_id} → ConstraintAgent output
- POST /mcp/agent/layout/optimize {site_model_id, violations, search_space} → LayoutAgent output
- POST /mcp/tool/validate_with_z3 {parent, formal_constraints, site_model_ref} → z3 result (proof_artifact_url)

mcp_context minimal JSON schema (示例)
```json
{
  "mcp_context_id": "ctx-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "parent_mcp_context_id": null,
  "agent": "ParseAgent",
  "agent_version": "v1.0",
  "input_schema": {},
  "output_schema": {},
  "timestamp": "2026-04-14T09:12:34Z",
  "latency_ms": 2340,
  "provenance": {"source": "wing_fal.dwg", "sha256": "a3b8f2e1..."},
  "status": "SUCCESS"
}
```

---

## 十、测试计划（核心测试场景）

- 单元测试：每个 Agent 功能点覆盖（CAD parsing, geometry repair, constraint encoding, GA ops）
- 集成测试：Parse → Constraint → Layout，使用 5–10 个 CAD 样本（包含边界/损坏样本）
- Regression tests：历史用例回测，防止新改动引入误判
- Z3 correctness tests：针对已知 SAT/UNSAT 样例验证 solver 输出及 proof artifacts
- LLM validation tests：随机抽样 LLM 翻译结果与人工标注对比；计算一致率并回收训练数据或 prompt
- Performance tests：latency p95/p99, GA convergence time, Z3 timeout rate
- UAT：业务方验收（导入→优化→审批全流程体验）

---

## 十一、风险与缓解措施

1. CAD 多样性导致解析失败
   - Mitigation: 多 parser 回退策略、人工复核快速通道、样本库持续扩充

2. LLM 幻觉（hallucination）
   - Mitigation: 强制 citations + Retriever 验证 + 限制自动迭代次数 + 人工复核阈值

3. Z3 在大规模约束下性能下降
   - Mitigation: 约束分解、timeout 控制、partial checks、并行求解、保存 proof artifacts 以便离线分析

4. GA 搜索耗时或局部最优
   - Mitigation: LLM 提示的启发式初值、多次随机 restart、并行化种群计算

5. 数据安全 / CAD 敏感性
   - Mitigation: 存储加密、访问控制、审计日志、减少 LLM 传输的敏感原文（使用 document id / segment id）

---

## 十二、交付物清单（交付给客户）

- 三个 Agent 的 Docker 镜像与部署 Helm charts
- MCP Tool API 文档（OpenAPI / JSON Schema）
- SiteModel / Ontology schema 文档
- AuditStore & proof artifacts（示例 s3 URIs）
- 前端 Demo（上传 → Top3 → Approve → PDF）
- 测试报告（单元/集成/性能/UAT）
- 维护手册与操作指南（含 LLM prompt 管理与约束库版本控制）

---

## 十三、下一步（立即行动项）

1. Kickoff meeting（1 小时） — 确认样本 CAD、约束优先级、SLA、团队成员
2. 在 Week0 完成 infra prerequisites（K8s / Postgres / S3 / GraphDB）
3. 优先实现 ParseAgent 与 AuditStore（Week1–2）以便尽早生成 SiteModel 输入
4. 并行准备 Z3 集成与约束库（Week2–3）
5. 设计并固化 LLM tool-calling schema（示例见第六节）

---

若需要，我可以：
- 把本 Markdown 转为 PDF 并签名（simulation），或
- 生成更细的 Sprint backlog（每任务 story points、负责人、验收标准），或
- 导出一份可直接用于开发的 OpenAPI 草案（/mcp/tool/*）

请告知下一步偏好。

