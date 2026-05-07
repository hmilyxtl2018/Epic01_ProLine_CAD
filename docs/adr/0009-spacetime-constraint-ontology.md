# ADR-0009 · 时空约束本体（4D Spacetime Constraint Ontology）

- **Status**: Proposed
- **Date**: 2026-05-07
- **Driver**: 解决"约束如何与产线实体（如装配工位）建立关联，以及约束在哪些生命周期阶段生效"两个根本问题。当前 `process_constraints.payload.asset_ids` 是字符串数组，既无外键、无视角语义、无生命周期，无法支撑 LayoutAgent / SimAgent / 排程下游消费。
- **Related**: [ADR-0005 ConstraintSet Schema](./0005-constraint-set-schema.md)、[ADR-0006 Constraint Evidence & Authority](./0006-constraint-evidence-authority.md)
- **Followed by**: 后续 ADR 将固化 4D 时空查询接口与 RBAC 投影策略。

---

## 1. Context

### 1.1 当前问题

| 问题 | 现象 | 后果 |
|---|---|---|
| 约束的"主语"模糊 | `payload.asset_ids: ["STA-103"]` 是字符串数组，无 FK 约束、无类型校验 | 资产改名 / 软删 → 约束悬空；无法回链到工序 |
| 缺少时间维 | 约束只有 `created_at / updated_at`，无"何时生效" | 设计期约束（梁高 ≥ 4.5m）混入运营期校验；改造与新建期约束无差别 |
| 缺少视角维 | 同一句 SOP（"24h 内完成铆接"）在工序时间、设备占用、工位互斥三个维度都成立，模型无法表达 | 下游消费者各自解析字符串，语义漂移 |
| 实体类型扁平 | 仅 `Asset` 一种，混淆 `Location / Equipment / Tool / Procedure / Document` | 无法做按类型聚合查询、无法层级继承约束 |

### 1.2 用户原始挑战

> "约束如何与产线实体（如装配工位）建立关联？这些约束最终是应用到 entity 的 SOP 上的。约束需要分时空——时指生命周期阶段（设计/建造/投产/改造/维护），然后才是空间约束。我们是否需要把资产分组：Location / Asset / Equipment / Tool / Procedure？"

直觉正确。其本质需求是**时空双维 + 视角分离**，与多个国际标准的根隐喻一致。

### 1.3 行业标准锚定

| 标准 | 提供 | 我们采纳 |
|---|---|---|
| **ISO 55000** 资产管理 | 物理资产生命周期 8 阶段 | `LifecyclePhase` 枚举 |
| **ISO 15926-2** 流程工厂全生命周期数据集成 | 4D space-time data model（每个事实带"何时有效 + 指向哪个对象"） | 约束携带 `temporal_scope + spatial_scope` |
| **ISA-95 / IEC 62264** 企业-控制系统集成 | Equipment Hierarchy（Enterprise → Site → Area → Line → WorkCenter → Station → Equipment → Module） | `node_kind` 枚举 + `parent_id` 自引用 |
| **IEC/ISO 81346** Reference Designation System | 三视角 RDS：Function `=` / Product `-` / Location `+`，同一物理对象可被多 aspect 引用 | `aspect` 枚举 + `rds_code` 唯一可读 ID |

---

## 2. Decision

### 2.1 核心模型

```
Constraint
  ├─ semantic_payload   { kind, params, … }                       [现有，不变]
  ├─ temporal_scope     applicable_phases: Set<LifecyclePhase>    [新]
  │                     valid_from / valid_to: Optional[datetime]
  └─ spatial_scope ──N:M──▶ HierarchyNode (经 ConstraintScope)    [新]
```

**LifecyclePhase 枚举（8 值，对齐 ISO 55000 + CAPEX）**：
```
CONCEPT         概念论证（FEED 之前）
DESIGN          详细设计
CONSTRUCTION    建造 / 安装
COMMISSIONING   调试投产
OPERATION       投产使用
MODIFICATION    改造扩能
MAINTENANCE     维护检修
DECOMMISSION    退役处置
```

**HierarchyAspect 枚举（IEC 81346）**：`FUNCTION | PRODUCT | LOCATION`

**HierarchyNode 表**（统一承载所有"实体"，避免扁平 enum 并列）：
```sql
hierarchy_nodes
  id              UUID PK
  rds_code        VARCHAR(64) UNIQUE   -- "=A1.B2-K1+S03"
  aspect          VARCHAR(16) CHECK IN ('FUNCTION','PRODUCT','LOCATION')
  node_kind       VARCHAR(32) CHECK IN
                    ('Enterprise','Site','Area','Line','WorkCenter','Station',
                     'Equipment','Tool','Fixture','Material',
                     'Procedure','Document','AssetTypeTemplate')
  parent_id       UUID NULL FK→hierarchy_nodes(id)
  asset_guid      VARCHAR(50) NULL FK→assets(asset_guid)
  process_step_id UUID NULL  -- 预留，工序表落地后接入
  name_zh         VARCHAR(200)
  properties      JSONB
  mcp_context_id  VARCHAR(100) FK
  created_at, updated_at, deleted_at, schema_version
  INDEX (parent_id) WHERE deleted_at IS NULL
  INDEX (aspect, node_kind) WHERE deleted_at IS NULL
```

**ConstraintScope 表**（多对多 + 视角 + 继承 + 绑定策略）：
```sql
constraint_scopes
  id                       UUID PK
  constraint_id            UUID FK→process_constraints
  node_id                  UUID FK→hierarchy_nodes
  binding_strategy         VARCHAR(20) CHECK IN
                             ('explicit_id','asset_type','semantic','manual')
  inherit_to_descendants   BOOLEAN DEFAULT FALSE
  confidence               NUMERIC(3,2)        -- 0.00–1.00
  verified_by_user_id      VARCHAR(100) NULL
  verified_at              TIMESTAMP NULL
  binding_evidence         JSONB                -- 原文片段 / 召回得分 / 备注
  mcp_context_id           VARCHAR(100) FK
  created_at, updated_at, deleted_at, schema_version
  UNIQUE (constraint_id, node_id) WHERE deleted_at IS NULL
  INDEX (node_id) WHERE deleted_at IS NULL
```

**`process_constraints` 表新增列**：
```sql
ALTER TABLE process_constraints
  ADD COLUMN applicable_phases JSONB NOT NULL DEFAULT '["DESIGN","OPERATION"]'::jsonb,
  ADD COLUMN valid_from TIMESTAMP NULL,
  ADD COLUMN valid_to   TIMESTAMP NULL;
```

### 2.2 不变量（INV-14..16）

- **INV-14**：`review_status='approved' ⇒ jsonb_array_length(applicable_phases) ≥ 1`。
- **INV-15**：`review_status='approved' ⇒ EXISTS(SELECT 1 FROM constraint_scopes WHERE constraint_id = … AND deleted_at IS NULL)`。
- **INV-16**：FUNCTION aspect 的 scope 必须指向 `node_kind ∈ {Procedure}`；PRODUCT 必须 ∈ {Equipment, Tool, Fixture, Material, AssetTypeTemplate}；LOCATION 必须 ∈ {Enterprise, Site, Area, Line, WorkCenter, Station}。
- 旧 INV-1..13 全部保留。

### 2.3 SOP ↔ Constraint ↔ Entity 链路（用户最关心的那一问）

```
SOP / PMI 文档 (HierarchyNode kind=Document, aspect=FUNCTION)
        │ extracts (parse_method=LLM_INFERENCE / PMI_ENGINE)
        ▼
    Constraint
        │ temporal_scope ──▶ applicable_phases: {DESIGN, OPERATION, …}
        │ spatial_scope ──▶ ConstraintScope[] ─▶ HierarchyNode[]
        ▼                                        ├─ FUNCTION:Procedure   工序应做/禁做
                                                 ├─ PRODUCT:Equipment    资产能力/限制
                                                 └─ LOCATION:Station     场所约束条件
```

**关键修正**：SOP 是文档，**工序（Procedure 节点 / FUNCTION aspect）才是被约束的对象**。同一约束可同时绑到三视角节点，下游 LayoutAgent 取 LOCATION 视角、SimAgent 取 FUNCTION 视角、排程取 PRODUCT 视角。

### 2.4 绑定策略（兼容上一稿讨论的 S1–S4）

| 策略 | binding_strategy | 触发 | 默认 confidence | 是否需人审 |
|---|---|---|---|---|
| S1 显式 ID | `explicit_id` | SOP/PMI 直写 `STA-103` 或 `CATIA://…` | 1.00 | 否 |
| S2 类型匹配 | `asset_type` | 匹配 `node_kind=AssetTypeTemplate` | 0.85 | 落地实例化时审 |
| S3 语义召回 | `semantic` | 向量召回 Top-K 候选 | 0.50–0.85 | `< 0.80` 必审 |
| S4 人工映射 | `manual` | UI 抽屉「添加绑定」 | 1.00 | 自动写 verified_by |

`inherit_to_descendants=true` 时约束沿树下传到子节点，子节点可显式覆盖（标准做法，参考 BIM IfcRelationship nesting + RDS 层级继承语义）。

---

## 3. Consequences

### 3.1 正向

- **下游可用性**：LayoutAgent / SimAgent 不再解析字符串数组，按 `aspect + phase` 查询即可获得"运营期 STA-103 上的所有约束"。
- **审计与回放**：满足 ISO 15926 "在任何时间点回放数据"理念；可输出 4D 时空矩阵供工艺师审视。
- **国际标准对齐**：未来与 PLM/EAM/BIM 系统集成时不需要重新建模。
- **生命周期治理**：设计期与运营期约束分离，避免"梁高约束在运营期触发误报"等噪声。

### 3.2 代价

- 三张表 + 一组 enum 增量；3 个 Alembic migration（0022/0023/0024）+ data migration。
- 既有 142 条约束需补 `applicable_phases` 默认值并标 `needs_re_review=true`，强制再审。
- 前端工作台需新增 `HierarchyTree`、`ScopePanel`、`LifecyclePhaseChips` 三组件；4D Heatmap 可缓后。
- 工艺师有学习成本（aspect 概念）→ 用 Tooltip + 首次引导缓解。

### 3.3 不做的事

- **不复制 Asset 物理字段**到 HierarchyNode：HierarchyNode 仅持 `asset_guid` 指针；Asset 仍由 ParseAgent 生产，`assets` 表保持唯一物理事实源。
- **不引入完整 ISO 15926 OWL 实现**：仅采纳其根隐喻；不接入 triple store，不切 RDF。
- **不立即支持 valid_from/valid_to 区间查询**：M1.5 仅落字段；查询能力延后至有需求时（YAGNI）。
- **不引入新的工序表**（ProcessStep）：`node_kind=Procedure` 的 HierarchyNode 即承担工序角色；待真有独立属性需求时再拆表。

### 3.4 迁移与回滚

- 三张 migration 必须 `alembic downgrade -3 && alembic upgrade head` 双向通过；`scripts/check_schema_drift.py` 零差异。
- 回滚步骤（按需）：`alembic downgrade -3` → 删除 `applicable_phases / valid_*` 列、`constraint_scopes`、`hierarchy_nodes`。回滚不丢约束语义本身（仅丢时空范围与绑定）。

---

## 4. Alternatives Considered

| 方案 | 否决原因 |
|---|---|
| **A. 把 LifecyclePhase 直接存为 `process_constraints.phase: VARCHAR`（单值）** | 一条约束常跨多阶段（设计 + 建造 + 运营），单值会强制人为复制 N 份，破坏唯一语义事实 |
| **B. 引入 ProcessStep 独立表 + 仅对 ProcessStep 绑定（无 HierarchyNode）** | 失去 LOCATION / PRODUCT 视角；LayoutAgent 仍需自建场所映射 |
| **C. 完整实现 ISO 15926 OWL/RDF 三元存储** | 团队学习曲线陡峭；当前需求规模不需要；与 SQLAlchemy/Pydantic 栈不契合 |
| **D. 把 Location/Equipment/Tool/Procedure 各自建表** | 扁平并列丢失层级；同一对象的多视角无法共享；与 IEC 81346 哲学相悖 |
| **E. 沿用 `payload.asset_ids` 字符串 + 只加 `applicable_phases`** | 不解决"绑定无 FK / 视角缺失"两个根问题；技术债持续 |

---

## 5. Validation

- L0 schema：HierarchyNode / ConstraintScope Pydantic round-trip ≥ 10 用例（含 `aspect × node_kind` 合法组合矩阵）。
- L0 不变量：INV-14/15/16 在 `tests/db/test_constraint_invariants.py` 各 ≥ 3 用例。
- L1 gold：3 条样例 SOP 跑 S1/S2/S3 自动绑定 → 期望 scope 集合冻结对比。
- 集成：`alembic upgrade head && downgrade -3 && upgrade head` round-trip 通过；`check_schema_drift.py` 0 差异。

---

## 6. References

- ISO 55000:2014 — Asset management — Overview, principles and terminology
- ISO 15926-2 — Industrial automation systems and integration — Lifecycle data for process plants — Part 2: Data model (4D space-time)
- ANSI/ISA-95.00.01 / IEC 62264-1 — Enterprise-Control System Integration — Equipment Hierarchy
- IEC/ISO 81346-1:2022 — Industrial systems, installations and equipment and industrial products — Structuring principles and reference designations
- IEC 81346-14 (FDIS) — RDS-MS Manufacturing and Processing Systems
- 内部：[ExcPlan/constraint_agent_frontend_plan.md §4](../../ExcPlan/constraint_agent_frontend_plan.md)、[ExcPlan/constraint_subsystem_v3_execution_plan.md](../../ExcPlan/constraint_subsystem_v3_execution_plan.md)
