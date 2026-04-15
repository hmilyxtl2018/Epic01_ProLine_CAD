

# 工艺产线 Multi-Agent 协同系统 — 完整实现执行计划

**版本**: v1.0  
**创建日期**: 2026-04-15  
**基线案例**: 航空蒙皮装配产线 FAL（wing_fal.dwg）  
**参考演示指标**: 8min 端到端耗时、0 次返工、99.8% 约束遵循度

---

## 一、项目总体概览

### 1.1 项目愿景

实现一个**生产就绪的三 Agent 闭环系统**，把传统工艺产线设计流程（4-6 周，3-5 次返工）加速到**8 分钟端到端交付、0 返工、99.8% 合规**。

```
传统流程                   系统优化后
设计评审 (1 周)  ──────→  CAD 导入 (< 1s)
工艺会签 (1 周)  ──────→  Agent 协同 (2-3 min)
仿真迭代 (2-4 周) ──────→  布局渲染 (< 1s)
人工返工 (3-5 次) ──────→  零返工（全约束 Z3 验证）
```

### 1.2 核心交付物

| 交付物 | 描述 | 依赖关系 |
|--------|------|---------|
| **ParseAgent** | CAD 解析 + 本体识别（SiteModel 生成） | 基础 |
| **ConstraintAgent** | 规则检查 + Z3 SAT 求解 + 约束诊断 | ParseAgent |
| **LayoutAgent** | GA 优化 + TopK 方案生成 | ConstraintAgent |
| **Orchestrator** | 流程编排 + mcp_context 传递 | 三个 Agent |
| **MCP Toolbelt** | ConstraintTranslator、SolverInvoker、SearchCoordinator 等 | ParseAgent、ConstraintAgent |
| **AuditStore** | 完整链路追溯（mcp_context 存储） | Orchestrator |
| **LLM Integration** | Tool-calling 适配、Prompt 模板 | MCP Toolbelt |
| **前端 Demo** | CAD 导入、图谱展示、Top3 对比、审批 PDF | 所有 Agent |

### 1.3 成功标准（DoD）

- ✅ 三个 Agent **单独可测试**，各自接口符合 JSON Schema 契约
- ✅ **端到端延迟** < 10 min（含 2 轮迭代）；p95 < 8 min
- ✅ **硬约束检出率** = 100%（对所有测试样例）；**假阳性率** < 0.2%
- ✅ **约束求解收敛** 稳定（GA 收敛，Z3 SAT 可验证）
- ✅ **mcp_context 链路** 100% 完整，支持全链路回溯
- ✅ **LLM 翻译** 与 Z3 验证结果 **一致率** >= 95%
- ✅ 所有约束 **源自权威文档**（PRD-3、SOP、HB/Z 标准）并可引用
- ✅ **审批 PDF** 含签名、reasoning chain、所有 mcp_context_id

---

## 二、系统架构与组件清单

### 2.1 三个 Agent 的最小实现框架

```yaml
Agent1-ParseAgent:
  container_name: "agent-parse-service"
  language: Python 3.9+
  dependencies:
    - IfcOpenShell (IFC parsing)
    - Teigha/ODA (DWG parsing)
    - CGAL (Geometry repair)
    - OWL/Protégé (Ontology engine)
    - psycopg2 (Postgres)
  input: CAD file (DWG/IFC/STEP/DXF)
  output: SiteModel (JSON) + Ontology Graph (JSON-LD)
  ports: [5001/REST, Kafka topic input]
  sla: p95_latency < 5s

Agent2-ConstraintAgent:
  container_name: "agent-constraint-service"
  language: Python 3.9+
  dependencies:
    - z3-solver (SAT/SMT)
    - Drools or Jess (Rule engine)
    - psycopg2 (Postgres)
  input: SiteModel + Constraint Set (CS-001)
  output: Hard Violations + Soft Scores + Reasoning Chain
  ports: [5002/REST, Kafka topic input]
  sla: p95_latency < 3s

Agent3-LayoutAgent:
  container_name: "agent-layout-service"
  language: Python 3.9+
  dependencies:
    - libspatialindex (R-Tree)
    - numpy/scipy (GA implementation)
    - psycopg2 (Postgres)
  input: Violations + Soft Targets
  output: Top3 candidate plans + reasoning chain
  ports: [5003/REST, Kafka topic input]
  sla: p95_latency < 6s

Orchestrator:
  container_name: "orchestrator-service"
  language: Python 3.9+ or Go
  dependencies:
    - Kafka/RabbitMQ (message queue)
    - psycopg2 (Postgres)
    - APScheduler (workflow scheduling)
  responsibility: CAD input → trigger chain → manage retries & timeouts
  ports: [5000/REST, Kafka control topics]
  sla: process SLA < 10 min (end-to-end)
```

### 2.2 关键依赖与基础设施

| 组件 | 用途 | 版本推荐 | 备注 |
|------|------|---------|------|
| **PostgreSQL** | SiteModel、mcp_context 存储 | 13+ | JSON 扩展；分区支持大数据 |
| **GraphDB/Blazegraph** | Ontology 图谱（RDF/JSON-LD） | 10.3+ | SPARQL 查询能力 |
| **Milvus/FAISS** | Vector DB（SOP 段落检索） | 2.3+ | LLM 上下文增强 |
| **S3/MinIO** | AuditStore（proof artifacts、PDF） | — | 持久化、版本控制 |
| **Kafka/RabbitMQ** | 消息队列（Agent 通信） | Kafka 3.x | 支持 Exactly-once 语义 |
| **z3-solver** | SMT/SAT 求解器 | 4.12+ | pip install z3-solver 或自编译 |
| **Docker/Kubernetes** | 容器化 + 编排 | K8s 1.24+ | Helm charts 管理部署 |
| **Prometheus/Grafana** | 监控与告警 | 最新版 | 追踪 Agent latency、token usage |

### 2.3 MCP Toolbelt（受控工具集）

```yaml
Tools:
  - /mcp/tool/constraint_translate
    Input: {sop_text_segments, requested_scope, ontology_version}
    Output: {formal_constraints, citations, confidence}
    Provider: LLM-assisted (受验证)
    mcp_context: ctx-ct-*
    
  - /mcp/tool/validate_with_z3
    Input: {site_model_id, formal_constraints}
    Output: {sat_result, unsat_core, witness, proof_artifact}
    Provider: z3-solver (deterministic)
    mcp_context: ctx-z3-*
    
  - /mcp/tool/generate_fix_suggestions
    Input: {unsat_core, search_hints}
    Output: {candidates, estimated_impact}
    Provider: Rule-based + LLM
    mcp_context: ctx-sugg-*
    
  - /mcp/tool/optimize_layout
    Input: {site_model_id, violations, search_space_size}
    Output: {top_3_plans, scores, reasoning_chain}
    Provider: LayoutAgent + R-Tree + GA
    mcp_context: ctx-layout-*
    
  - /mcp/tool/publish_audit_record
    Input: {mcp_context_ids, decision, signatures}
    Output: {audit_id, storage_url}
    Provider: AuditStore (S3 + DB)
    mcp_context: ctx-audit-*
    
  - /mcp/tool/retrieve_sop
    Input: {query, top_k}
    Output: {segments, segment_ids, scores}
    Provider: Milvus + vector embeddings
    mcp_context: ctx-retriever-*
```

---

## 三、分阶段执行计划（10-12 周推荐方案）

### 阶段 0：项目准备与发现（Week 1，2 人/周）

**主要产出**: 需求确认、基线数据、架构定版、资源申请

#### 0.1 工作清单

- [ ] **需求确认** (2 days)
  - 确认最小支持 CAD 格式（DWG/IFC 优先）
  - 收集约束集合版本化（CS-001 版本、引用标准清单）
  - 定义用户角色与权限（设计、审查、批准）
  - 确认审批流程与签名策略（电子签章、数字证书）

- [ ] **样本数据收集** (3 days)
  - 获取 5-10 个代表性 CAD 样本（不同规模、复杂度、格式）
  - 手工标注标准答案（本体资产、约束状态、预期方案）
  - 建立回归测试集

- [ ] **约束库定义** (2 days)
  - 输入：PRD-3、SOP 蒙皮装配工艺规程、HB/Z 223-2013
  - 输出：约束库 CS-001 版本化仓库
    ```yaml
    C-001:
      type: HARD
      description: "设备间距 >= 500mm"
      source: "PRD-3 §2.1.4"
      authority: PMI_ENGINE
      assets: [MDI-2024-001, MDI-2024-002]
    C-045:
      type: SOFT
      description: "物流路径利用率 >= 0.85"
      source: "SOP §6.5"
      weight: 0.30
    ```

- [ ] **技术评估** (2 days)
  - Z3 部署可行性（Python binding vs 自编译）
  - CAD 库选型（IfcOpenShell、Teigha、CGAL）
  - 图谱 DB 选型（Blazegraph vs JanusGraph）

- [ ] **基础设施规划** (2 days)
  - K8s 环境预置（staging + production）
  - 数据库实例（Postgres、GraphDB、S3）
  - CI/CD 管道框架（GitLab CI / GitHub Actions）

#### 0.2 验收准则
- ✅ 约束库 CSV/JSON 已输入系统，包含 15+ 约束
- ✅ 5 个样本 CAD 已下载并分类
- ✅ K8s namespace + PVC 已创建
- ✅ Postgres/GraphDB 实例运行

---

### 阶段 1：基础设施与 MCP Toolbelt（Week 2-3，3 人/周）

**主要产出**: 完整 infra stack、AuditStore、Retriever、mcp_context 约定

#### 1.1 工作清单

- [ ] **数据库设置** (3 days)
  - Postgres 初始化 + 分区策略（mcp_context 表按时间分区）
  - Schema 定义（SiteModel、Assets、mcp_contexts、audit_logs）
  - 索引优化（on site_model_id, agent, timestamp）
  - 备份策略（daily snapshots to S3）

  ```sql
  -- Example: mcp_context table
  CREATE TABLE mcp_contexts (
    id UUID PRIMARY KEY,
    agent_id VARCHAR(50),
    parent_context_id UUID REFERENCES mcp_contexts(id),
    input_schema JSONB,
    output_schema JSONB,
    timestamp TIMESTAMP,
    latency_ms INT,
    provenance JSONB,  -- {file_sha256, source, version}
    status VARCHAR(20),  -- SUCCESS, PARTIAL, ERROR
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW()
  ) PARTITION BY RANGE (timestamp);
  ```

- [ ] **GraphDB 配置** (2 days)
  - 创建 ontology_repository
  - 导入 AeroOntology-v1.0 初始本体（RDFS/OWL）
  - 配置 SPARQL 端点
  - 测试复杂查询（OPTIONAL, FILTER, paths）

- [ ] **AuditStore 实现** (4 days)
  - 设计 audit record schema（包含所有 mcp_context_id、signatures）
  - 实现存储接口（S3 + DB 双冗余）
  - 实现检索接口（by mcp_context_id、by time range）
  - 版本控制与不可篡改保证（blockchain checksum optional）

  ```json
  {
    "audit_id": "audit-7f3a-4e81-b2c9-001",
    "decision": "APPROVED",
    "mcp_context_ids": [
      "ctx-7f3a-4e81-b2c9-001",
      "ctx-7f3a-4e81-b2c9-002",
      "ctx-7f3a-4e81-b2c9-003"
    ],
    "approver": "engineer@company.com",
    "signature": "-----BEGIN PKCS7-----...",
    "pdf_sha256": "a3b8f2e1...",
    "timestamp": "2026-04-14T09:12:39.445Z"
  }
  ```

- [ ] **Vector DB & Retriever** (3 days)
  - Milvus 部署（单节点或集群）
  - SOP 文本分段与向量化（OpenAI embeddings 或本地模型）
  - 导入 SOP 段落到 Milvus
  - 实现 /mcp/tool/retrieve_sop 接口

- [ ] **消息队列与流控** (2 days)
  - Kafka 主题设置（cad_import、agent1_output、agent2_output、agent3_output）
  - 消费者组配置（enable offsets management）
  - 死信队列（DLQ）与重试策略（exponential backoff）

- [ ] **mcp_context 约定文档** (2 days)
  - JSON Schema 定义（global mcp_context structure）
  - 命名规则（ctx-<hash>-<sequence>）
  - 必填字段清单
  - 版本化管理（mcp_context_schema_v1.0）

  ```json
  {
    "mcp_context_id": "ctx-7f3a-4e81-b2c9-001",
    "agent": "ParseAgent",
    "agent_version": "v1.0",
    "parent_context_id": null,
    "input_schema": {...},
    "output_schema": {...},
    "timestamp": "2026-04-14T09:12:34.567Z",
    "latency_ms": 2340,
    "provenance": {
      "source": "wing_fal.dwg",
      "sha256": "a3b8f2e1...",
      "tool_versions": {"IfcOpenShell": "0.7.0", "CGAL": "5.4"}
    },
    "status": "SUCCESS",
    "error_message": null
  }
  ```

#### 1.2 验收准则
- ✅ Postgres 可连接，mcp_context 表可写入/读取 100K+ 记录
- ✅ GraphDB SPARQL 查询耗时 < 100ms（中等复杂度）
- ✅ S3 audit store 可存储 & 检索 PDF
- ✅ Milvus 向量检索 top-5 SOP 段落 < 50ms
- ✅ mcp_context 约定文档已发布并获一致同意

---

### 阶段 2：ParseAgent 实现（Week 4-5，2 人/周）

**主要产出**: 可独立测试的 ParseAgent，生成 SiteModel + Ontology Graph

#### 2.1 工作清单

- [ ] **CAD 解析模块** (4 days)
  - 集成 IfcOpenShell（IFC）、Teigha/ODA（DWG）、STEP parser
  - 实现 format_detect() → 自动识别格式
  - 实现 entity_extract() → 提取所有 CAD entities（LWPOLYLINE、CIRCLE、3DSOLID）
  - 构建空间索引（R-Tree）用于碰撞检测
  - 单元测试（5 个 CAD 样本通过率 100%）

- [ ] **几何修补与标准化** (3 days)
  - 实现 topology_repair()
    - 检测开放 polyline 并闭合
    - 去重复 entities
    - 自我相交检测与修复
  - 实现 coord_normalize()
    - WCS/UCS 变换
    - 单位归一化（→ mm）
    - 原点校准
  - 几何完整度评分（baseline: 0.92 for wing_fal）

- [ ] **本体资产识别** (3 days)
  - 实现 classify_entity() 将 CAD entity 映射到本体类（Equipment、Conveyor、LiftingPoint）
  - 层名匹配（layer mapping）与推理（若层名不存在，基于几何启发式）
  - 提取关键点（吊点、WELD_TIP）
  - 置信度评分 = 0.3×layer_match + 0.3×geometry_valid + 0.2×port_detection + 0.2×reference_check

- [ ] **Ontology 图谱生成** (2 days)
  - 创建资产对象（asset_guid、type、coords、footprint、ports）
  - 生成语义关系（APPLIES_TO、PAIR_WITH、TRAVERSES 等）
  - 序列化为 JSON-LD，导入到 GraphDB
  - 验证图谱完整性

- [ ] **SiteModel 持久化** (2 days)
  - 实现 SiteModel 序列化（到 Postgres JSON 列）
  - 实现检索接口（by site_model_id）
  - mcp_context 记录生成与写入

- [ ] **Agent1 REST 接口** (2 days)
  ```python
  POST /mcp/agent/parse
  {
    "cad_file": "<base64>",
    "format": "DWG",
    "options": {"preprocess": true, "ontology_version": "AeroOntology-v1.0"}
  }
  Response:
  {
    "mcp_context_id": "ctx-7f3a-4e81-b2c9-001",
    "site_model_id": "SM-001",
    "assets": [...],
    "ontology_graph": {...},
    "statistics": {...}
  }
  ```

- [ ] **单元 & 集成测试** (2 days)
  - 回归测试集（5 个样本）
  - 测试覆盖率 > 80%
  - 性能测试（latency histogram）
  - 边界情况（corrupted CAD、oversized files）

#### 2.2 验收准则
- ✅ 对 5 个样本 CAD，avg_confidence >= 0.90
- ✅ p95_latency <= 5s（含 wing_fal ~2.3s baseline）
- ✅ geometry_integrity_score >= 0.85
- ✅ 所有 assets & ontology 可查询（GraphDB SPARQL）
- ✅ mcp_context 完整记录在 Postgres

---

### 阶段 3：ConstraintAgent 实现（Week 6-7，2 人/周）

**主要产出**: Z3 集成的约束检查、硬约束诊断、软约束评分

#### 3.1 工作清单

- [ ] **约束集加载与管理** (2 days)
  - 实现 load_constraint_set(cs_id) 从数据库读取约束集
  - 约束分类（HARD vs SOFT）
  - 权限与版本化管理

- [ ] **Z3 集成 & SolverInvoker** (5 days)
  - 安装 z3-solver（pip 或自编译）
  - 实现约束编码为 Z3 语言（LIA - Linear Integer Arithmetic）
    ```python
    # Example: C-001 encoding
    # distance(MDI-2024-001, MDI-2024-002) >= 500
    x1, y1 = Ints('x1 y1')  # MDI-2024-001 coords
    x2, y2 = Ints('x2 y2')  # MDI-2024-002 coords
    distance = z3.Sqrt((x2-x1)**2 + (y2-y1)**2)
    solver.add(distance >= 500)
    ```
  - 实现 Z3 求解调用（check() → SAT/UNSAT）
  - UNSAT core 提取（explain which constraints conflict）
  - Proof artifact 保存（SMT-LIB2 格式）

- [ ] **软约束评分器** (2 days)
  - 实现评分函数（加权和）：score = 0.4×间距合规 + 0.3×物流效率 + 0.2×吊运安全 + 0.1×扩展性
  - 逐项计算分数并标注

- [ ] **硬约束冲突报告生成** (2 days)
  - 输出结构：{id, type, affected_assets, description, suggested_fix}
  - 每个冲突附带来源标准引用
  - 改进建议生成（基于 UNSAT core 分析）

- [ ] **LLM-assisted ConstraintTranslator**（可选但推荐） (3 days)
  - 实现 /mcp/tool/constraint_translate 接口
  - LLM prompt 模板（输入 SOP 段落 → 输出结构化约束 JSON）
  - 强制 Z3 验证（LLM 输出必走 validate_with_z3）
  - Hallucination 检测（检查 source_id 是否存在）

- [ ] **Agent2 REST 接口** (2 days)
  ```python
  POST /mcp/agent/constraint/check
  {
    "site_model_id": "SM-001",
    "constraint_set_id": "CS-001"
  }
  Response:
  {
    "mcp_context_id": "ctx-7f3a-4e81-b2c9-002",
    "hard_violations": [{"id": "C-001", "description": "...", "suggested_fix": "..."}],
    "soft_scores": {"C-045": 0.68},
    "sat_result": "UNSAT",
    "reasoning_chain": [...]
  }
  ```

- [ ] **单元 & 集成测试** (2 days)
  - 已知 SAT/UNSAT 样例验证（precision = 100%）
  - Z3 solve time 分布测试
  - 超时处理（设置 timeout = 10s）

#### 3.2 验收准则
- ✅ 硬约束检出率 = 100%（无漏检）
- ✅ 假阳性率 < 0.2%（无误报）
- ✅ Z3 solve time p95 <= 2s（对中等模型）
- ✅ soft_scores 计算正确性验证（手工抽检）
- ✅ 所有冲突附带 reasoning 与源标准引用

---

### 阶段 4：LayoutAgent 实现（Week 8-9，2 人/周）

**主要产出**: GA 优化器 + TopK 方案生成 + Z3 验证

#### 4.1 工作清单

- [ ] **搜索空间定义** (2 days)
  - 参数化：每个 asset 可调整坐标（dx, dy, dz 范围）
  - 搜索空间大小：1000+ 候选（可配置）
  - 初始种群生成（随机 + LLM 启发式）

- [ ] **GA 遗传算法实现** (4 days)
  - 种群初始化（population_size = 100）
  - 适应度函数（scoring function）
  - 遗传算子：交叉、变异、选择
  - 代数设置（max_generations = 50）
  - 收敛判定：Δscore < 0.005 连续 3 代

- [ ] **碰撞检测 & R-Tree** (2 days)
  - 构建 R-Tree 空间索引（每个 asset footprint 作为矩形）
  - 实现快速碰撞检测（避免 N² 比较）
  - 将碰撞结果反馈到适应度评分（碰撞 → score penalty）

- [ ] **候选方案验证与评分** (2 days)
  - 对每个候选方案调用 Z3 验证（validate_layout_candidate）
  - 仅保留满足所有硬约束的方案
  - 按软约束评分排序
  - 输出 Top3 候选

- [ ] **Reasoning Chain 生成** (2 days)
  - 记录搜索过程：SEARCH → EVALUATE → VERIFY → RECOMMEND
  - 每步附带 Based 引用（PRD-3 §3.4 scoring function）
  - 对最终 Top3 方案生成详细说明

- [ ] **Agent3 REST 接口** (2 days)
  ```python
  POST /mcp/agent/layout/optimize
  {
    "site_model_id": "SM-001",
    "violations": ["C-001"],
    "soft_targets": ["C-045"],
    "search_space_size": 1000
  }
  Response:
  {
    "mcp_context_id": "ctx-7f3a-4e81-b2c9-003",
    "candidates": [
      {"plan_id": "A", "score": 0.92, "adjustments": {...}, "hard_pass": true},
      {"plan_id": "B", "score": 0.78, ...},
      {"plan_id": "C", "score": 0.65, ...}
    ],
    "reasoning_chain": [...]
  }
  ```

- [ ] **单元 & 集成测试** (2 days)
  - GA 收敛性测试（不同初值）
  - Top3 方案硬约束验证（100% 通过率）
  - 性能基准（latency histogram）

#### 4.2 验收准则
- ✅ 对 sample violations 输出 Top3 方案
- ✅ 最佳方案满足所有硬约束（hard_pass = true）且 score >= 0.80
- ✅ GA 收敛稳定（Δscore 趋势 monotonic increasing）
- ✅ p95_latency <= 6s（含 sample 3120ms baseline）
- ✅ TopK 方案评分合理（可解释）

---

### 阶段 5：Orchestration、LLM 集成、前端 Demo（Week 10，3 人/周）

**主要产出**: 完整闭环（CAD → Agent1→2→3）、LLM tool-calling、基础 UI

#### 5.1 工作清单

- [ ] **Orchestrator 实现** (3 days)
  - 工作流状态机：PENDING → PARSE_RUNNING → CONSTRAINT_CHECKING → LAYOUT_OPTIMIZING → COMPLETE
  - 触发条件：CAD upload → /api/import_cad → 调用 Agent1
  - 链路传递：Agent1 output (site_model_id) → Agent2 input；Agent2 output → Agent3 input
  - mcp_context 传递与链接（parent_context_id 关系）
  - 超时与重试策略
    ```yaml
    retry_policy:
      Agent1_timeout: 8s
      Agent1_retries: 2
      Agent2_timeout: 5s
      Agent2_retries: 1  # Z3 不建议重试（结果确定）
      Agent3_timeout: 10s
      Agent3_retries: 1
    ```

- [ ] **迭代循环管理** (2 days)
  - 若 Agent3 仍产出 hard_violations，自动 loop → Agent2 再检查
  - 收敛判定：满足度 >= 0.80 且无硬约束违规，或达 max_iterations (3)
  