# ADR-0005 · ConstraintSet Data Schema

- **Status**: Proposed
- **Date**: 2026-04-24
- **Supersedes / Refines**: 部分收敛 `db_schemas.ConstraintSet`（JSONB 大数组）与 `process_constraints` (migration 0014) 两套并存的约束存储；对齐 `PRD/PRD全局附录_数据模型与接口规范.md § 1.1` ER 图。
- **Driver**: Phase 2.3 结束后需要一个可版本化、可溯源、可被 Layout/Sim 冻结引用的"工艺约束集合"。
- **Extended by**: [ADR-0006 Constraint Evidence & Authority Model](./0006-constraint-evidence-authority.md) — 补充每条约束的"依据 / 权威 / 范围"（authority × conformance × scope + ConstraintSource / Citation）。本 ADR 的 `ConstraintItemV2` 在 ADR-0006 §3.3 中再增补 `authority / conformance / scope / citations` 四字段。


---

## 1. Context

项目中目前存在三套并列但未融合的约束数据：

| 位置 | 粒度 | 语义维度 | 问题 |
|---|---|---|---|
| `constraint_sets` 表 (db_schemas.py L142) | 集合 | `hard_constraints` / `soft_constraints` 两个大 JSONB 数组 | 无行级索引；改一条要重写整表；无法按 kind/source 查询 |
| `process_constraints` 表 (migration 0014) | 单条 | 4 种 `kind` (predecessor / resource / takt / exclusion) | 扁平挂在 `site_model_id` 上，**缺 `constraint_set_id`**，无法版本化 / 快照发布 |
| `shared/models.py.Constraint` (Pydantic) | 单条领域模型 | `expression / source / authority / weight / affected_assets` | 纯内存模型，未落库；风格偏 PRD-2 规则 DSL 路线 |

PRD 全局附录期望的目标 ER（简化）：

```
Project ──1:N──> ConstraintSet ──1:N──> Constraint ──N:1──> SourceDocument
                        │
                        └──1:1──> ProcessGraph
ConstraintSet ──1:N──> LayoutCandidate   (layout 引用冻结版本)
```

**核心矛盾**：现状的"结构 kind"（predecessor / resource / takt / exclusion）和 PRD 的"语义 class"（hard / soft / preference）是**两个正交维度**，过去被错误地用 `hard_constraints` / `soft_constraints` 两个数组表达，导致无法同时查询"所有硬约束的 takt"或"所有来源于 SOP-A 的软约束"。

## 2. Decision

### 2.1 两维度解耦

```
kind      ∈ { predecessor, resource, takt, exclusion }    # 结构：给 solver/DAG 看
class     ∈ { hard, soft, preference }                     # 语义：给调度/人看
severity  ∈ { critical, major, minor }                     # 正交：违约严重度
```

一条约束必须同时持有 (`kind`, `class`, `severity`)。`kind` 决定 `payload` 的 JSON 形状（沿用现有 discriminated union）；`class` 决定违约行为（拒绝 / 扣分 / 报告）；`severity` 决定告警级别与看板颜色。

### 2.2 `ConstraintSet` 作为聚合根 + 版本快照单元

- Layout / Sim / Report 引用的是**冻结版本号**（`cs_xxx@v1`），不是活动草稿。
- 每个 `(site_model_id, status='active')` 组合**最多一个** set（partial unique index）。
- `publish` 操作：`status=active → archived + published_at + freeze`；触发器阻止 published set 的成员写操作。

### 2.3 行级可索引

废弃 `constraint_sets.hard_constraints` / `soft_constraints` 两个 JSONB 列，改用 `constraint` 行（升级版 `process_constraints`）通过 `constraint_set_id` FK 聚合。

### 2.4 溯源可审计

每条约束持有 (`source_document_id`, `source_span`, `mcp_context_id`, `rationale`, `confidence`) — 对齐 PRD-2 RAG 抽取与 Palantir 式决策证据链要求。

### 2.5 向后兼容

保留 Phase 2.2 已上线的 `/sites/{sid}/constraints` 路由，内部重定向到该 site "默认 active set"，不破坏既有客户端。

## 3. Data Model

### 3.1 DB 层 (migration 0015 增量)

```sql
-- 新枚举
CREATE TYPE constraint_class    AS ENUM ('hard','soft','preference');
CREATE TYPE constraint_severity AS ENUM ('critical','major','minor');
CREATE TYPE constraint_set_status AS ENUM ('draft','active','archived');

-- 重构聚合根
ALTER TABLE constraint_sets
    ADD COLUMN project_id        VARCHAR(50),   -- 可选，项目级模板
    ADD COLUMN site_model_id     VARCHAR(50) REFERENCES site_models(site_model_id),
    ADD COLUMN status            constraint_set_status NOT NULL DEFAULT 'draft',
    ADD COLUMN published_at      TIMESTAMPTZ,
    ADD COLUMN published_by      VARCHAR(100),
    ADD COLUMN description       TEXT,
    ADD COLUMN tags              TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN process_graph_id  UUID;          -- FK 见 3.1.2

-- 废弃（保留一个版本做兼容 view）
ALTER TABLE constraint_sets
    DROP COLUMN hard_constraints,
    DROP COLUMN soft_constraints;

-- 每 site 最多一个 active
CREATE UNIQUE INDEX uq_cset_active_per_site
    ON constraint_sets (site_model_id)
    WHERE status = 'active' AND deleted_at IS NULL;

-- 升级单条约束表
ALTER TABLE process_constraints
    ADD COLUMN constraint_set_id  UUID REFERENCES constraint_sets(id) ON DELETE CASCADE,
    ADD COLUMN class              constraint_class    NOT NULL DEFAULT 'hard',
    ADD COLUMN severity           constraint_severity NOT NULL DEFAULT 'major',
    ADD COLUMN weight             NUMERIC(4,3) NOT NULL DEFAULT 1.0,
    ADD COLUMN rule_expression    TEXT,
    ADD COLUMN rationale          TEXT,
    ADD COLUMN confidence         NUMERIC(3,2),
    ADD COLUMN source_document_id UUID,          -- FK to source_documents when available
    ADD COLUMN source_span        JSONB,         -- {page, bbox | char_range, quote}
    ADD COLUMN tags               TEXT[] NOT NULL DEFAULT '{}';

-- 不变量：hard ↔ weight=1.0
ALTER TABLE process_constraints
    ADD CONSTRAINT ck_hard_full_weight
        CHECK (class <> 'hard' OR weight = 1.0);

CREATE INDEX idx_pc_set_class ON process_constraints (constraint_set_id, class)
    WHERE deleted_at IS NULL;
CREATE INDEX idx_pc_set_severity ON process_constraints (constraint_set_id, severity)
    WHERE deleted_at IS NULL;
CREATE INDEX idx_pc_source_doc ON process_constraints (source_document_id)
    WHERE source_document_id IS NOT NULL;
```

### 3.1.2 ProcessGraph 物化缓存

```sql
CREATE TABLE process_graphs (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    constraint_set_id  UUID NOT NULL UNIQUE REFERENCES constraint_sets(id) ON DELETE CASCADE,
    dag_hash           CHAR(64) NOT NULL,        -- sha256 of sorted edges
    node_count         INTEGER NOT NULL,
    edge_count         INTEGER NOT NULL,
    has_cycle          BOOLEAN NOT NULL,
    cycle_asset_ids    TEXT[] NOT NULL DEFAULT '{}',
    longest_path_s     NUMERIC,                  -- CPM critical path length (optional)
    computed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Publish 时强制要求 `has_cycle = false`。

### 3.1.3 Publish 冻结触发器（伪代码）

```sql
CREATE FUNCTION tg_freeze_published_set() RETURNS trigger AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM constraint_sets cs
               WHERE cs.id = NEW.constraint_set_id
                 AND cs.published_at IS NOT NULL) THEN
        RAISE EXCEPTION 'constraint_set % is published/immutable', NEW.constraint_set_id;
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER tg_pc_freeze
    BEFORE INSERT OR UPDATE OR DELETE ON process_constraints
    FOR EACH ROW EXECUTE FUNCTION tg_freeze_published_set();
```

### 3.2 Pydantic 层 (`app/schemas/constraint_sets.py`)

```python
ConstraintClass    = Literal["hard", "soft", "preference"]
ConstraintSeverity = Literal["critical", "major", "minor"]
ConstraintSetStatus= Literal["draft", "active", "archived"]

class SourceSpan(BaseModel):
    page: int | None = None
    char_range: tuple[int, int] | None = None
    bbox: tuple[float, float, float, float] | None = None
    quote: str | None = Field(None, max_length=500)

class ConstraintSemantics(BaseModel):
    """Orthogonal to structural `kind` + `payload`."""
    class_: ConstraintClass = Field("hard", alias="class")
    severity: ConstraintSeverity = "major"
    weight: float = Field(1.0, ge=0.0, le=1.0)
    rule_expression: str | None = None
    rationale: str | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _hard_full_weight(self):
        if self.class_ == "hard" and self.weight != 1.0:
            raise ValueError("hard constraint must have weight==1.0")
        return self

class ConstraintProvenance(BaseModel):
    source_document_id: str | None = None
    source_span: SourceSpan | None = None
    mcp_context_id: str | None = None

# Extends existing Phase-2.2 ConstraintItem — keep payload union.
class ConstraintItemV2(ConstraintItem):
    constraint_set_id: str | None = None
    semantics: ConstraintSemantics = Field(default_factory=ConstraintSemantics)
    provenance: ConstraintProvenance = Field(default_factory=ConstraintProvenance)

class ConstraintSetCounts(BaseModel):
    total: int = 0
    by_kind: dict[str, int] = Field(default_factory=dict)
    by_class: dict[str, int] = Field(default_factory=dict)
    by_severity: dict[str, int] = Field(default_factory=dict)

class ProcessGraphStats(BaseModel):
    has_cycle: bool
    node_count: int
    edge_count: int
    cycle_asset_ids: list[str] = Field(default_factory=list)
    longest_path_s: float | None = None

class ConstraintSetSummary(BaseModel):
    id: str
    constraint_set_id: str
    project_id: str | None
    site_model_id: str | None
    version: str
    status: ConstraintSetStatus
    published_at: datetime | None = None
    published_by: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    counts: ConstraintSetCounts
    validation: ValidationReport | None = None      # reuses existing Phase-2.2 type
    process_graph: ProcessGraphStats | None = None
    created_at: datetime
    updated_at: datetime

class ConstraintSetDetail(ConstraintSetSummary):
    constraints: list[ConstraintItemV2] = Field(default_factory=list)

class ConstraintSetCreate(BaseModel):
    constraint_set_id: str = Field(..., pattern=r"^cs_[A-Za-z0-9_\-]+$")
    project_id: str | None = None
    site_model_id: str | None = None
    version: str = "v1.0"
    description: str | None = None
    tags: list[str] = Field(default_factory=list)

class ConstraintSetPatch(BaseModel):
    description: str | None = None
    tags: list[str] | None = None

class ConstraintSetPublishRequest(BaseModel):
    require_no_errors: bool = True
    require_dag_acyclic: bool = True
    note: str | None = None
```

### 3.3 前端 TS (`web/src/lib/types.ts` 增量)

```ts
export type ConstraintClass    = "hard" | "soft" | "preference";
export type ConstraintSeverity = "critical" | "major" | "minor";
export type ConstraintSetStatus= "draft" | "active" | "archived";

export interface SourceSpan {
  page?: number;
  char_range?: [number, number];
  bbox?: [number, number, number, number];
  quote?: string;
}

export interface ConstraintSemantics {
  class: ConstraintClass;
  severity: ConstraintSeverity;
  weight: number;
  rule_expression?: string | null;
  rationale?: string | null;
  confidence?: number | null;
  tags: string[];
}

export interface ConstraintProvenance {
  source_document_id?: string | null;
  source_span?: SourceSpan | null;
  mcp_context_id?: string | null;
}

// ConstraintItemV2 = ConstraintItem (existing) + semantics + provenance + constraint_set_id
export interface ConstraintItemV2 extends ConstraintItem {
  constraint_set_id: string | null;
  semantics: ConstraintSemantics;
  provenance: ConstraintProvenance;
}

export interface ConstraintSetCounts {
  total: number;
  by_kind: Record<string, number>;
  by_class: Record<ConstraintClass, number>;
  by_severity: Record<ConstraintSeverity, number>;
}

export interface ProcessGraphStats {
  has_cycle: boolean;
  node_count: number;
  edge_count: number;
  cycle_asset_ids: string[];
  longest_path_s?: number | null;
}

export interface ConstraintSetSummary {
  id: string;
  constraint_set_id: string;
  project_id: string | null;
  site_model_id: string | null;
  version: string;
  status: ConstraintSetStatus;
  published_at: string | null;
  published_by: string | null;
  description: string | null;
  tags: string[];
  counts: ConstraintSetCounts;
  validation: ValidationReport | null;
  process_graph: ProcessGraphStats | null;
  created_at: string;
  updated_at: string;
}

export interface ConstraintSetDetail extends ConstraintSetSummary {
  constraints: ConstraintItemV2[];
}
```

## 4. Lifecycle

```
 S2-ConstraintAgent (extractSOP / retrieveNorm)
             ▼
  ConstraintSet(draft)                  ← LLM 抽取逐条落库，带 source_span / confidence
             ▼
  人工复核 (ConstraintsPanel)            ← P2.3 现有 UI 加 class/severity 列
             ▼
  POST /constraint-sets/{id}/publish
      · 拒绝 validation.errors > 0
      · 拒绝 process_graph.has_cycle
      · set.status=active, published_at=now()
      · trigger freeze 成员行
             ▼
  ConstraintSet(active, v1)             ← 不可变
             ▼
  LayoutAgent / SimAgent:
      POST /layouts { constraint_set_id: "cs_xxx@v1" }
             ▼
  Sim 反馈触发 writeBackConstraint：
      POST /constraint-sets/{id}/clone → draft v2
```

**版本寻址**：`constraint_set_id@version`，默认解析为 `@latest-active`。Layout / Sim / Report 存的是冻结版本号，保证"A 方案当初用的是哪版约束"永远可回放。

## 5. API Surface

| Method | Path | Role |
|---|---|---|
| GET    | `/projects/{pid}/constraint-sets` | viewer+ |
| POST   | `/projects/{pid}/constraint-sets` | operator+ |
| GET    | `/constraint-sets/{csid}` | viewer+ |
| PATCH  | `/constraint-sets/{csid}` | operator+ (draft only) |
| POST   | `/constraint-sets/{csid}/publish` | reviewer+ |
| POST   | `/constraint-sets/{csid}/clone` → draft | operator+ |
| GET    | `/constraint-sets/{csid}/validate` | viewer+ |
| GET    | `/constraint-sets/{csid}/process-graph` | viewer+ |
| GET/POST/PATCH/DELETE | `/constraint-sets/{csid}/constraints[/cid]` | (reuse Phase-2.2 handlers) |

**兼容层**：`/sites/{sid}/constraints` 保留，内部透传到该 site 的默认 active set。

## 6. Migration Plan

### P0 · schema 落地（1–2d）

- `db/alembic/versions/0015_constraint_sets_refactor.py`
  - 新枚举、列、触发器、partial unique index、`process_graphs` 表
- 数据回填脚本（`scripts/backfill_0015.py`）
  1. 为每个 `site_model_id` 创建 `cs_default_<sid>` draft，完成后 `publish` 为 active v1
  2. 把现有 `process_constraints` 行 `UPDATE SET constraint_set_id = <new_id>, class='hard', severity='major'`
  3. 把旧 `constraint_sets.hard_constraints` / `soft_constraints` JSONB 数组平铺成行（如有数据）
  4. 为每个 active set 计算 `process_graphs` 行

### P1 · Pydantic / Router（1d）

- `app/schemas/constraint_sets.py`（内容见 3.2）
- `app/routers/constraint_sets.py`（surface 见 §5）
- 旧 `/sites/{sid}/constraints` 改为薄 forwarder

### P2 · ProcessGraph 服务（1d）

- `app/services/process_graph.py`
  - 从 `kind='predecessor' AND class in ('hard','soft') AND is_active` 的行构造 DAG
  - 计算 `dag_hash / has_cycle / longest_path_s`
  - Publish 前强制校验

### P3 · 前端（1–2d）

- `web/src/lib/types.ts` 增量（见 3.3）
- `web/src/lib/api.ts` 新方法：`listConstraintSets`, `getConstraintSet`, `publishConstraintSet`, `cloneConstraintSet`
- `ConstraintsPanel` 顶部加 Set 选择器（Draft / Active vN / Archived …）、Publish 按钮、Source / Class / Severity 列

### P4 · ConstraintAgent 对接（2d）

- `extractSOP` 产出物 → 新建 draft set 并 bulk insert 成员
- `writeBackConstraint` → `clone(active)` → `patch draft` → `publish` 流

## 7. Trade-offs / Rejected Alternatives

- **直接把 class 当作 kind 的扩展（如 `soft_takt`）**：否。`kind` 控制 solver 代码路径；`class` 控制违约策略；正交组合会指数爆炸并让未来新增 "偏好型 takt" 非常别扭。
- **不要 `rule_expression` 字段**：否。PRD-2 规则 DSL / 自然语言原文需要落地位；不填不影响 4-kind solver，填了给审计 / RAG 检索用。
- **ProcessGraph 临时计算不入库**：否。Layout 每次跑都要读 DAG；`dag_hash` 做"未变化则跳过重算"收益明显。
- **允许 publish 后编辑**：否。审计 / 复现性（Palantir 式决策证据链）要求。要改就 clone 成 draft v2。

## 8. Open Questions

1. `project_id` 在当前 repo 中是否已有正式表？如无，本 ADR 的 `constraint_sets.project_id` 先挂空列，等 `projects` 表落地再加 FK。
2. `source_documents` 表是否已存在？当前仅在 PRD 里出现；落库前 `source_document_id` 暂不加 FK，只做 VARCHAR。
3. `published_at` 之后是否允许 "unpublish"？当前设计为不可逆（只能 clone 新 draft）。需要 product 确认。

## 9. Next Actions

切到 Act Mode 后按 §6 P0→P4 推进；每步独立 PR，可回滚。
