# 约束子系统数据模型蓝图（权威规范）

> **定位**：本文档是约束子系统所有后期开发任务的**单一事实来源**。
> 当 [ExcPlan/constraint_subsystem_v3_execution_plan.md](../ExcPlan/constraint_subsystem_v3_execution_plan.md)、
> [ADR-0005](adr/0005-constraint-set-schema.md)、[ADR-0006](adr/0006-constraint-evidence-authority.md)
> 与本文档不一致时，**以本文档为准**。
>
> 修改本文档需走 ADR 流程（新增 ADR 引用本文件章节号）。

---

## 0. 一图看懂

```
                    ┌─────────────┐
                    │   Project   │  (尚无表，project_id 仅为 VARCHAR 占位)
                    └──────┬──────┘
                           │ 1:N
                           ▼
┌─────────────┐   1:N   ┌─────────────────┐   1:N    ┌──────────────────┐
│  SiteModel  │────────▶│  ConstraintSet  │─────────▶│ ProcessConstraint│
│ (PRD-1 产物)│ active  │  聚合根/版本化   │ FK       │  (单条工艺约束)   │
└─────────────┘ 唯一    │  status/version │          │  kind+class+...  │
                       └────────┬────────┘          └────────┬─────────┘
                                │ 1:1                        │ N:M
                                ▼                            ▼
                       ┌─────────────────┐          ┌──────────────────────┐
                       │  ProcessGraph   │          │ ConstraintCitation   │ ← Audit 单元
                       │  DAG 物化缓存   │          │ (引用连接表)         │
                       └─────────────────┘          └──────────┬───────────┘
                                                               │ N:1
                                                               ▼
                                                    ┌──────────────────────┐
                                                    │  ConstraintSource    │
                                                    │ (法规/标准/SOP/MBD)  │
                                                    └──────────┬───────────┘
                                                               │ 1:N
                                                               ▼
                                                    ┌──────────────────────────────┐
                                                    │ ConstraintSourceVersionEvent │
                                                    │ (源升版事件流，触发复核)     │
                                                    └──────────────────────────────┘
```

**关键事实（与执行手册旧稿冲突，以下为正解）**：

1. **不要新建 `documents` 表**。任何上传的工艺文档（PDF/SOP/MBOM/MBD）都是
   一种 `ConstraintSource`，通过 `authority` 字段区分（statutory / industry /
   enterprise / project / heuristic / preference）。文件实体走 MinIO，
   `constraint_sources.doc_object_key` 指向对象存储 key。
2. **不要新建 `constraints`（Layer A 本体）表**。ADR-0005/0006 已把语义维度
   `class / severity / authority / conformance / scope / rule_expression / rationale /
   confidence / source_document_id / source_span / citations` 全部下沉到
   `process_constraints`，这张表**就是** Layer A，没有 Layer B 单独存在。
3. **不要新建 `constraint_links`（KG 边）表**。`constraint_citations` 即是
   `SOURCED_FROM` 边；`CONFLICTS_WITH` 与 `SUPERSEDES` 边由 M4 求解器阶段引入
   独立表，不在本阶段范围。
4. **不要双层模型**。kind（4 种结构）× class（hard/soft/preference）×
   authority × category 已经是充分的正交维度，给求解器与给工程师看的是**同一张表**
   的不同投影。

---

## 1. 现有表清单（截至 migration 0017，由 `dbclient-get-tables` 实证）

| 表 | 来源 | 角色 | 关键字段 |
|---|---|---|---|
| `constraint_sets` | ADR-0005 mig 0015 | 聚合根 / 版本快照单元 | `id`, `constraint_set_id`, `version`, `status`, `site_model_id`, `project_id`, `published_at`, `published_by`, `tags[]`, `description`, `mcp_context_id` |
| `process_constraints` | ADR-0005 + 0006 mig 0015/0016 | 单条约束（正交多维） | `id`, `constraint_id`, `constraint_set_id` FK, `site_model_id` FK, `kind`, `payload` JSONB, `class`, `severity`, `weight`, `authority`, `conformance`, `scope` JSONB, `rule_expression`, `rationale`, `confidence`, `source_document_id`, `source_span` JSONB, `tags[]`, `priority`, `is_active` |
| `process_graphs` | ADR-0005 §3.1.2 mig 0015 | DAG 物化缓存（per ConstraintSet） | `id`, `constraint_set_id` FK UNIQUE, `dag_hash`, `node_count`, `edge_count`, `has_cycle`, `cycle_asset_ids[]`, `longest_path_s`, `computed_at` |
| `constraint_sources` | ADR-0006 mig 0016 | 规范 / 标准 / SOP 元数据 | `source_id` PK, `title`, `authority`, `issuing_body`, `version`, `clause`, `clause_text`, `effective_from`, `expires_at`, `tags[]`, `url_or_ref`, `doc_object_key` |
| `constraint_citations` | ADR-0006 mig 0016 | 约束 ↔ 源 多对多连接（=SOURCED_FROM 边） | `id`, `process_constraint_id` FK, `source_id` FK, `clause`, `quote`, `confidence`, `derivation`, `cited_by`, `cited_at`, `reviewed_at_version`, `reviewed_by`, `reviewed_at` |
| `constraint_source_version_events` | ADR-0006 mig 0016 | 源升版事件流（GB 50016-2014 → 2026 触发引用方复核） | `id`, `source_id` FK, `old_version`, `new_version`, `changed_at`, `changed_by`, `release_notes` |

---

## 2. 主外键关系（FK 矩阵）

| 子表 | 子列 | 父表 | 父列 | 级联 |
|---|---|---|---|---|
| `constraint_sets` | `site_model_id` | `site_models` | `site_model_id` | RESTRICT |
| `constraint_sets` | `mcp_context_id` | `mcp_contexts` | `mcp_context_id` | SET NULL |
| `process_constraints` | `constraint_set_id` | `constraint_sets` | `id` | CASCADE |
| `process_constraints` | `site_model_id` | `site_models` | `site_model_id` | RESTRICT |
| `process_constraints` | `mcp_context_id` | `mcp_contexts` | `mcp_context_id` | SET NULL |
| `process_graphs` | `constraint_set_id` | `constraint_sets` | `id` | CASCADE，UNIQUE |
| `constraint_citations` | `process_constraint_id` | `process_constraints` | `id` | CASCADE |
| `constraint_citations` | `source_id` | `constraint_sources` | `source_id` | RESTRICT |
| `constraint_source_version_events` | `source_id` | `constraint_sources` | `source_id` | CASCADE |

**软删约定**：`constraint_sets` / `process_constraints` / `constraint_sources`
均有 `deleted_at`，物理 CASCADE 仅在硬删时触发。日常软删不级联，由 publish gate
负责检测「已发布集合引用了已软删的源」。

**待补 FK（M0 之后）**：

| 子列 | 期望父表 | 状态 | 备注 |
|---|---|---|---|
| `constraint_sets.project_id` | `projects` | 表未建 | ADR-0005 §8 Open Q1，VARCHAR 占位 |
| `process_constraints.source_document_id` | `constraint_sources.source_id` | **未建 FK** | ADR-0005 §8 Open Q2，与 `constraint_citations` 重叠，建议**冗余字段废弃**，统一走 citations 表（见 §5 重构项） |

---

## 3. 调用 / 数据流（从产品角度看）

### 3.1 录入路径（写）

```
[A] 工程师手工录入（UI）
    → POST /sites/{sid}/constraints
    → ConstraintsService.create()
        ├─ 找/建 default active ConstraintSet
        ├─ INSERT process_constraints (class=hard 默认, authority=heuristic 默认)
        └─ 触发 ProcessGraph 重算 (mark stale, lazy)

[B] Excel 批量导入
    → POST /constraint-sets/{csid}/constraints:batch-import
    → 行级 try/except，失败行返回 errors[]
    → 全部 INSERT 到 csid（必须为 draft 状态）
    → ProcessGraph 重算

[C] LLM 抽取（M3+，本阶段仅占位）
    → ConstraintAgent.extractSOP(doc_id)
    → ① 若引用源不在 constraint_sources，先 INSERT source（authority=project）
    → ② INSERT process_constraints + 强制配套 INSERT constraint_citations
    → ③ 写 mcp_contexts 留链路

[D] 上传规范/SOP 文档
    → POST /constraint-sources (multipart)
    → ① 上传 binary 至 MinIO，得 doc_object_key
    → ② INSERT constraint_sources（authority 由用户选择）
    → 不直接产生 process_constraints；由后续 [C] 流程消费
```

### 3.2 发布路径（freeze）

```
POST /constraint-sets/{csid}/publish
  ├─ 1. 重算 process_graph (CPM)；require has_cycle=false
  ├─ 2. validation.errors == 0（kind 内冲突，如同 asset 双 takt）
  ├─ 3. publish gate（ADR-0006 §3.2）：
  │     for c in constraints:
  │       if class=hard AND authority in (statutory, industry):
  │           require len(citations) >= 1
  │       for cite in citations:
  │           if cite.source.expires_at < today: warn
  ├─ 4. UPDATE constraint_sets SET status='active',
  │                                 published_at=NOW(),
  │                                 published_by=:user
  ├─ 5. 触发器 freeze_published_set 启动 → 阻止后续 INSERT/UPDATE/DELETE
  └─ 6. 旧 active 集合 UPDATE status='archived'
```

### 3.3 消费路径（读）

```
[P] LayoutAgent / SimAgent 调用
    → POST /layouts {constraint_set_id: "cs_xxx@v1"}
    → 服务层解析 @version 锁定到具体 cs.id
    → SELECT process_constraints WHERE constraint_set_id=?
                                    AND scope 命中当前上下文
                                    AND is_active
    → 按 class 分流：hard → solver hard cons，soft/preference → 目标函数权重
    → 读 process_graphs 缓存，dag_hash 命中则跳过重算

[Q] 前端 ConstraintsWorkbench 渲染
    → GET /constraint-sets/{csid}                  → summary + counts
    → GET /constraint-sets/{csid}/constraints      → list（分页 + 过滤）
    → GET /constraint-sets/{csid}/process-graph    → DAG JSON
    → GET /constraint-sources                      → 规范库（左栏）
    → GET /process-constraints/{cid}/citations     → 详情面板溯源块
```

### 3.4 源升版传播（lesson-learned 路径）

```
admin 更新 constraint_sources：GB 50016-2014 → GB 50016-2026
  ├─ INSERT constraint_source_version_events (old=2014, new=2026)
  ├─ 后台 worker：找出所有 constraint_citations.source_id=src_gb50016
  │   AND reviewed_at_version != '2026'
  ├─ 标记这些约束 needs_re_review=true（M3 字段，下文 §5）
  └─ 通知 reviewer 队列
```

---

## 4. 维度组合速查（避免再混淆 kind / class / category / authority）

四个维度**正交**，含义与谁来定义：

| 维度 | 含义 | 看谁的 | 取值 | 决定什么 |
|---|---|---|---|---|
| `kind` | 结构类型 | solver | `predecessor / resource / takt / exclusion` | `payload` JSONB 形状；solver 代码路径 |
| `class` | 强制等级 | 调度策略 | `hard / soft / preference` | 违约处理（拒绝 / 扣分 / 提示） |
| `category` | **业务维度** | 工程师 / 报表 | `SPATIAL / SEQUENCE / TORQUE / SAFETY / ENVIRONMENTAL / REGULATORY / QUALITY / RESOURCE / LOGISTICS / OTHER` | UI 配色、报表分组、权重模板（**目前 schema 里还没有，§5 待补**） |
| `authority` | 法理来源 | 审计 / 仲裁 | `statutory / industry / enterprise / project / heuristic / preference` | publish gate（hard+regulatory 强制 citation）；冲突仲裁默认胜方 |
| `conformance` | RFC-2119 表述 | 报告 / UI 文案 | `MUST / SHOULD / MAY` | 审计报告措辞，badge 文字 |
| `severity` | 违约严重度 | 告警 / 看板 | `critical / major / minor` | 告警颜色、SLA 优先级 |

**正交示例**（同一条约束的 6 个维度并存）：

```jsonc
{
  "constraint_id": "cst_F003_F005_dist",
  "kind":        "exclusion",        // 结构：互斥（不能挨太近）
  "payload":     { "asset_ids": ["F-003","F-005"], "min_distance_mm": 500 },
  "class":       "hard",
  "category":    "SPATIAL",          // ← 业务维度，§5 待补
  "authority":   "project",
  "conformance": "MUST",
  "severity":    "major",
  "scope":       { "phase": ["assembly"] }
}
```

---

## 5. Gap List：后期开发任务清单（蓝图 → 任务）

按优先级排列。每条都对应一个 PR 或 ADR。

### G1 · `process_constraints.category` 列（P0，**M0 必做**）

**问题**：产品截图 2 表头第 3 列「类型」（SPATIAL/SEQUENCE/TORQUE/SAFETY/...）
当前 schema 无字段承载，无法分组、无法配色、无法写权重模板。

**任务**：
- migration `0018_add_category.py`：
  ```sql
  CREATE TYPE constraint_category AS ENUM (
      'SPATIAL','SEQUENCE','TORQUE','SAFETY','ENVIRONMENTAL',
      'REGULATORY','QUALITY','RESOURCE','LOGISTICS','OTHER'
  );
  ALTER TABLE process_constraints
      ADD COLUMN category constraint_category NOT NULL DEFAULT 'OTHER';
  CREATE INDEX idx_pc_category ON process_constraints (constraint_set_id, category)
      WHERE deleted_at IS NULL;
  ```
- 同步 `shared/db_schemas.py`、`shared/models.py`、Pydantic、TS types
- 数据回填：旧行根据 `kind` 推断初值（exclusion→SPATIAL、predecessor→SEQUENCE，
  resource→RESOURCE，takt→QUALITY），允许后续手动校正
- 新增维度走 ADR

### G2 · 行级审核状态（P0，**M1 必做**）

**问题**：当前 `constraint_sets.status` 是集合粒度（draft/active/archived），
无法表达「集合里某条约束需要复核」。截图 2 的「审核队列」需要行级状态。

**任务**：migration `0019_add_review_status.py`：
```sql
CREATE TYPE constraint_review_status AS ENUM (
    'draft','under_review','approved','rejected','superseded'
);
ALTER TABLE process_constraints
    ADD COLUMN review_status      constraint_review_status NOT NULL DEFAULT 'approved',
    ADD COLUMN parse_method       VARCHAR(40) NOT NULL DEFAULT 'MANUAL_UI',
    ADD COLUMN verified_by_user_id VARCHAR(100),
    ADD COLUMN verified_at        TIMESTAMPTZ,
    ADD COLUMN needs_re_review    BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE process_constraints ADD CONSTRAINT ck_review_verified
    CHECK (review_status <> 'approved'
           OR (verified_by_user_id IS NOT NULL AND verified_at IS NOT NULL));
```
- `parse_method` 取值：`MANUAL_UI / EXCEL_IMPORT / MBOM_IMPORT / PMI_ENGINE / LLM_INFERENCE`
  （字符串而非枚举，扩展自由）
- `needs_re_review=true` 由 §3.4 worker 写入

### G3 · 上传文档接入 ConstraintSource（P0，**M1 必做**）

**问题**：执行手册旧稿想新建 `documents` 表，错。SOP/MBD/MBOM 文件就是
`ConstraintSource` 的 `authority='project'` 实例。

**任务**：
- 新增端点 `POST /constraint-sources` (multipart) — operator+
  - 接受 file + metadata（authority/title/version/...）
  - 上传到 MinIO，bucket `constraint-sources`
  - 计算 sha256，写入 `meta` JSONB（建议 G4 补一个 `hash_sha256` 列）
  - INSERT `constraint_sources`，`doc_object_key=s3://constraint-sources/{source_id}.{ext}`
- 新增 `GET /constraint-sources?authority=&tag=&q=`
- 删除执行手册 §4.1 里的 `/sites/{sid}/documents` 路由设计

### G4 · ConstraintSource 补 `hash_sha256` 列（P1）

**问题**：上传重复检测、版本对比都需要内容指纹。

**任务**：migration `0020`：
```sql
ALTER TABLE constraint_sources
    ADD COLUMN hash_sha256 CHAR(64),
    ADD COLUMN classification VARCHAR(20) NOT NULL DEFAULT 'INTERNAL';
CREATE UNIQUE INDEX uq_cs_hash ON constraint_sources (hash_sha256)
    WHERE hash_sha256 IS NOT NULL AND deleted_at IS NULL;
```
- `classification`: `PUBLIC / INTERNAL / CONFIDENTIAL / SECRET`，决定 LLM 路由
  （PRD §6.2，本阶段守卫装饰器 noop）

### G5 · 废弃 `process_constraints.source_document_id` 冗余字段（P1）

**问题**：与 `constraint_citations` 表重复表达 SOURCED_FROM 关系，且无 FK。

**任务**：
- 数据迁移：把 `source_document_id` 非空的行写入 `constraint_citations`（
  authority 用所属 source 的，confidence=1.0）
- migration 0021 DROP COLUMN
- 同步去掉 Pydantic / TS 字段；前端读 citations 即可

### G6 · KG 边的 CONFLICTS_WITH / SUPERSEDES（M4，**本阶段不做**）

预留方案：新建 `constraint_relations` 表（不是 `constraint_links`）：
```sql
CREATE TABLE constraint_relations (
    id              UUID PK,
    relation        ENUM('CONFLICTS_WITH','SUPERSEDES'),
    subject_pc_id   UUID FK → process_constraints,
    object_pc_id    UUID FK → process_constraints,
    detected_by     VARCHAR(40),  -- z3_solver / human / agent
    detected_at     TIMESTAMPTZ,
    resolution      JSONB,        -- 仲裁结果
    UNIQUE (relation, subject_pc_id, object_pc_id)
);
```
本阶段 M0–M2 不建，路由不预留。

### G7 · `projects` 表（待 PRD 决策）

ADR-0005 §8 Open Q1。`constraint_sets.project_id` 维持 VARCHAR 占位，FK 不加。
若后续接入企业项目主数据，单独 ADR。

---

## 6. 不变量（CI 与运行时强制）

| ID | 规则 | 强制层 | 来源 |
|---|---|---|---|
| INV-1 | 每 (`site_model_id`, `status='active'`) 最多 1 个 ConstraintSet | partial unique index | ADR-0005 §3.1 |
| INV-2 | `class='hard'` 必须 `weight=1.0` | DB CHECK `ck_hard_full_weight` | ADR-0005 §3.1 |
| INV-3 | `authority∈{statutory,industry}` ⇒ `class='hard'` | DB CHECK `ck_authority_class_coherence` | ADR-0006 §3.1 |
| INV-4 | `authority='preference'` ⇒ `class≠'hard'` | DB CHECK | ADR-0006 §3.1 |
| INV-5 | `class='hard' AND authority∈{statutory,industry}` ⇒ ≥1 citation | publish gate | ADR-0006 §3.2 |
| INV-6 | publish 后所有 process_constraints 不可改 | trigger `tg_freeze_published_set` | ADR-0005 §3.1.3 |
| INV-7 | publish 要求 `process_graph.has_cycle=false` | publish 服务层 | ADR-0005 §3.1.2 |
| INV-8 | `review_status='approved'` ⇒ `verified_by_user_id` 与 `verified_at` 非空 | DB CHECK `ck_review_verified` | G2 待补 |
| INV-9 | `(constraint_id, constraint_set_id)` 全局唯一 | unique index | ADR-0005 §3.1 |
| INV-10 | citation 的 `source.expires_at < NOW()` ⇒ publish warn | publish gate | ADR-0006 §3.2 R4 |

---

## 7. 命名/词汇收敛表（消除歧义）

| 旧/混淆术语 | 正式术语 | 出处 |
|---|---|---|
| Layer A / Layer B 双层模型 | **单层 process_constraints**（多维正交） | 本文档 §0 |
| `Document` / `documents` 表 | **`ConstraintSource`** + MinIO blob | G3 |
| `enforcement` (HARD/SOFT/PREFERENCE) | **`class`** (hard/soft/preference) | ADR-0005 |
| `lifecycle` (DRAFT/UNDER_REVIEW/...) | 集合层 = `ConstraintSet.status`；行层 = `process_constraints.review_status` | G2 |
| `constraint_links` 表 | `constraint_citations` (SOURCED_FROM) + `constraint_relations` (CONFLICTS_WITH/SUPERSEDES, M4) | G6 |
| `Layer A 本体记录 constraints 表` | **不存在；就是 `process_constraints`** | 本文档 §0 |
| `compiled_from_constraint_id` | **不需要；同表内不存在层级** | 本文档 §0 |

---

## 8. 路由命名空间（消除前缀冲突）

| 命名空间 | 含义 | 示例 |
|---|---|---|
| `/sites/{sid}/constraints` | **兼容层**，转发到 site 的默认 active ConstraintSet | Phase 2.2 历史 |
| `/constraint-sets/...` | **聚合根 CRUD + 发布 + clone** | ADR-0005 §5 |
| `/constraint-sets/{csid}/constraints/...` | **集合内单条约束 CRUD** | ADR-0005 §5 |
| `/constraint-sources` | 规范 / 标准 / SOP 元数据库 | ADR-0006 + G3 |
| `/constraint-sources/{sid}/version-events` | 升版事件流 | 本文档 §3.4 |
| `/process-constraints/{cid}/citations` | 单条约束的 citation 子资源 | ADR-0006 §6 P1 |

**禁止再启用**：
- ❌ `/sites/{sid}/documents`
- ❌ `/sites/{sid}/ontology/constraints`
- ❌ `/sites/{sid}/ontology/links`
- ❌ `/sites/{sid}/ontology/graph`

KG 视图作为 ConstraintSet 的派生视图：
**`GET /constraint-sets/{csid}/graph`** 返回 `{nodes, edges}`，节点 = `process_constraints`
+ `constraint_sources`，边 = `constraint_citations` + (M4 后) `constraint_relations`。

---

## 9. 与执行手册的差异收敛清单

| 执行手册旧稿章节 | 状态 | 处理 |
|---|---|---|
| §0 双层 Layer A/B 模型 | ❌ 错 | 改为「单表多维正交」 |
| §3.1.1 新建 `documents` 表 | ❌ 错 | 删除；用 `constraint_sources` + G3 |
| §3.1.2 新建 `constraints` 表 | ❌ 错 | 删除；扩展 `process_constraints`（G1+G2） |
| §3.1.3 新建 `constraint_links` 表 | ❌ 错 | 删除；用 `constraint_citations`，M4 再加 `constraint_relations`(G6) |
| §3 字段名 `enforcement / lifecycle` | ⚠ 命名分歧 | 改用 `class / review_status` |
| §4.1 `/sites/{sid}/documents` | ❌ 错 | 改为 `POST /constraint-sources` (multipart) |
| §4.2 `/sites/{sid}/ontology/constraints` | ❌ 错 | 改为 `/constraint-sets/{csid}/constraints` |
| §4.3 `/sites/{sid}/ontology/graph` | ⚠ 路径错 | 改为 `/constraint-sets/{csid}/graph` |
| §5 UI 三栏 + 四 Tab | ✅ 保留 | 仅字段名按 §7 收敛 |
| §10 预留字段 `compiled_from_constraint_id` | ❌ 错 | 删除 |

执行手册将按本文档 §5 (G1–G7) 重构里程碑：
- **M0** = G1 + G2（schema 补 category / review_status）
- **M1** = G3 + G4（上传文档 → ConstraintSource 接入；hash & classification）
- **M2** = 前端重写（按 §8 路由、§4 维度）

---

## 10. 验证脚本

落地后跑这两条作为本蓝图的回归 gate：

```powershell
# 1. FK 关系与 §2 矩阵一致
python scripts/check_constraint_fk_matrix.py

# 2. 不变量 INV-1..INV-10 全部生效
pytest tests/db/test_constraint_invariants.py -q
```

未通过禁止合并任何约束子系统相关 PR。
