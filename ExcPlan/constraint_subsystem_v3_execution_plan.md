# 约束子系统 v3.0 执行手册（PRD-2 落地）

> 本文档是 **PRD-2「工艺文档转数字约束」** 的工程落地引导手册，定位与
> [parse_agent_ga_execution_plan.md](parse_agent_ga_execution_plan.md) 同级。
> 范围聚焦 **第一阶段：约束的来源接入 + 关系表达与呈现（列表 + 知识图谱）**，
> 为后续 AI 仲裁、审核队列预埋接口与数据结构。
>
> **数据模型权威来源**：
> [docs/constraint_subsystem_data_model.md](../docs/constraint_subsystem_data_model.md)
> 是单一事实来源。本手册的 §3 / §4 / §10 章节已对齐其 §5（Gap List G1–G7）与
> §8（路由命名空间）。如有冲突以蓝图为准。
>
> 主要 PRD / ADR 依据：
> - [PRD/step3.2-PRD-2 v3.0](../PRD/step3.2-PRD-2%20v3.0%EF%BC%9A%E5%B7%A5%E8%89%BA%E6%96%87%E6%A1%A3%E8%BD%AC%E6%95%B0%E5%AD%97%E7%BA%A6%E6%9D%9F%EF%BC%88%E7%9F%A5%E8%AF%86%E5%9B%BE%E8%B0%B1%2BMBD%E8%B7%AF%E7%BA%BF%EF%BC%89%E7%A0%94%E5%8F%91%E6%8E%92%E6%9C%9F%E7%BA%A7.md)
> - [PRD/step4.2-PRD-2_工艺文档转数字约束_产品原型.html](../PRD/step4.2-PRD-2_工艺文档转数字约束_产品原型.html)
> - [ADR-0005 ConstraintSet Data Schema](../docs/adr/0005-constraint-set-schema.md)
> - [ADR-0006 Constraint Evidence & Authority Model](../docs/adr/0006-constraint-evidence-authority.md)
> - [CLAUDE.md](../CLAUDE.md)（Palantir 本体论；MCP-only；无 emoji；Pydantic v2）

---

## 0. 现状对齐（一句话总结）

截图所示数据库已落地 ADR-0005 + ADR-0006 的 **`constraint_sets` /
`process_constraints` / `process_graphs` / `constraint_sources` /
`constraint_citations` / `constraint_source_version_events` 六张表**。

之前草稿提到的「Layer A / Layer B 双层模型 + `documents` / `constraints` /
`constraint_links` 三张新表」**已废弃**。正确路径是
**单表多维正交**：`process_constraints` 通过 `kind × class × authority ×
conformance × severity × scope` 一次性表达结构与语义；正在补的是
**`category`（业务维度）** 与 **`review_status`（行级审核）** 两列。

详见 [docs/constraint_subsystem_data_model.md §0](../docs/constraint_subsystem_data_model.md#0-一图看懂) 的 ER 图与
[§5 Gap List G1–G7](../docs/constraint_subsystem_data_model.md#5-gap-list后期开发任务清单蓝图--任务)。

---

## 1. 范围与非范围

### 1.1 本阶段（M0–M2）做什么

| # | 模块 | 一句话 | 蓝图 Gap |
|---|---|---|---|
| M0 | 数据模型补维度 | `process_constraints` 增补 `category` + `review_status` + `parse_method` + `verified_*` + `needs_re_review`；`constraint_sources` 增补 `hash_sha256` + `classification` | G1, G2, G4 |
| M1 | 来源接入 | `POST /constraint-sources` (multipart, MinIO) + 手工录入 + Excel 批量导入 + 三层提取占位 | G3 |
| M2 | 列表与图谱 | 新版 `ConstraintsWorkbench` 三栏 + `GET /constraint-sets/{csid}/graph` 本体视图 + 溯源面板 | — |

> 不再新建 `documents` / `constraints` / `constraint_links` 三表。详见蓝图 §0 与 §9。

### 1.2 本阶段**不做**（明确划线，写进验收）

- ❌ Z3 SAT 求解、UNSAT core 提取（M3，下一阶段）
- ❌ AI 冲突仲裁推理链、证据链评分（M4，蓝图 G6 `constraint_relations` 表）
- ❌ CP-B Token 签发（M5）
- ❌ MBD/PMI 引擎对接（PythonOCC，M6+）
- ❌ Neo4j 引入（用 PG 邻接表先跑，规模 < 10k 节点足够）
- ❌ 删除 `process_constraints.source_document_id` 冗余字段（蓝图 G5，留到 M3 一起做）

M4+ 字段不预留可空列；待 ADR 明确表结构后再增。

---

## 2. 约束维度词汇（与已实现 schema 对齐）

约束有 **6 个正交维度**，全部存在 `process_constraints` 同一行上。详见
[蓝图 §4 维度组合速查](../docs/constraint_subsystem_data_model.md#4-维度组合速查避免再混淆-kind--class--category--authority)。

| 维度 | 字段 | 取值 | 状态 | 决定 |
|---|---|---|---|---|
| 结构 | `kind` | predecessor / resource / takt / exclusion | ✅ 已有 | solver 代码路径、payload 形状 |
| 强制等级 | `class` | hard / soft / preference | ✅ 已有 | 违约处理（拒绝/扣分/提示） |
| 业务维度 | `category` | SPATIAL / SEQUENCE / TORQUE / SAFETY / ENVIRONMENTAL / REGULATORY / QUALITY / RESOURCE / LOGISTICS / OTHER | ⚠ **本阶段补（G1）** | UI 配色、报表分组、权重模板 |
| 法理来源 | `authority` | statutory / industry / enterprise / project / heuristic / preference | ✅ 已有 | publish gate、仲裁默认胜方 |
| 表述 | `conformance` | MUST / SHOULD / MAY | ✅ 已有 | 审计报告措辞 |
| 严重度 | `severity` | critical / major / minor | ✅ 已有 | 告警颜色 |

**生命周期分两层**（不要再说 `lifecycle`）：

- **集合层**：`constraint_sets.status ∈ {draft, active, archived}`（已实现，ADR-0005）
- **行层**：`process_constraints.review_status ∈ {draft, under_review, approved, rejected, superseded}`
  （**本阶段补，G2**）

```
[行层 review_status]
draft ─┬─ submit ──→ under_review ─┬─ approve ──→ approved ──┐
       │                            └─ reject  ──→ rejected  │
       │                                                     │
       └──────────────── supersede（M4 仲裁后）──────────────┘
                                ↓
                           superseded

[集合层 status]
draft ── publish ──→ active ── (新版 publish) ──→ archived
        （触发器 freeze 所有 process_constraints 行）
```

只有 `review_status='approved'` 的约束在 publish gate 里被纳入；只有
`status='active'` 的 ConstraintSet 才能被 LayoutAgent / SimAgent 引用。

---

## 3. 数据模型（M0 交付物 = 蓝图 G1+G2+G4）

**不新建表**。所有改动落在 3 张已存在的表上。完整 SQL 见
[蓝图 §5](../docs/constraint_subsystem_data_model.md#5-gap-list后期开发任务清单蓝图--任务)。

### 3.1 migration `0018_add_category.py`（蓝图 G1）

- 新枚举 `constraint_category`（10 值，见 §2 表格）
- `ALTER TABLE process_constraints ADD COLUMN category constraint_category NOT NULL DEFAULT 'OTHER'`
- 索引 `(constraint_set_id, category) WHERE deleted_at IS NULL`
- 数据回填规则：exclusion→SPATIAL、predecessor→SEQUENCE、resource→RESOURCE、takt→QUALITY

### 3.2 migration `0019_add_review_status.py`（蓝图 G2）

- 新枚举 `constraint_review_status`（5 值）
- `process_constraints` 新增 `review_status` / `parse_method` / `verified_by_user_id` /
  `verified_at` / `needs_re_review` 共 5 列
- DB CHECK：`review_status='approved' ⇒ verified_* 非空`（INV-8）
- 旧行回填 `review_status='approved'`，`parse_method='MANUAL_UI'`

### 3.3 migration `0020_source_hash_classification.py`（蓝图 G4）

- `constraint_sources` 新增 `hash_sha256 CHAR(64)` + `classification VARCHAR(20)`
- 部分唯一索引 `(hash_sha256) WHERE NOT NULL AND deleted_at IS NULL`

### 3.4 同步层

- `shared/db_schemas.py`：补 ORM 列定义
- `shared/models.py` / `shared/enums.py`：补 Pydantic 枚举与字段（`extra="forbid"`）
- `web/src/lib/types.ts`：补 TS 联合类型

### 3.5 Alembic 通用要求

- 双向 round-trip 通过：`alembic upgrade head && alembic downgrade -3 && alembic upgrade head`
- `python scripts/check_schema_drift.py` 零差异
- `python scripts/check_constraint_fk_matrix.py`（蓝图 §10）零差异

> ⚠ **不要碰** `process_constraints.source_document_id` 冗余列（蓝图 G5），
> 留到 M3 与 LLM 抽取一起处理。

---

## 4. 后端 API（M1 交付物）

命名空间锁定见 [蓝图 §8](../docs/constraint_subsystem_data_model.md#8-路由命名空间消除前缀冲突)。
RBAC 与现有 viewer/operator/admin 一致。

### 4.1 ConstraintSource（规范 / 标准 / SOP / MBD 元数据）

| 方法 | 路径 | 角色 | 说明 |
|---|---|---|---|
| POST | `/constraint-sources` | operator+ | **multipart**，上传文件 → MinIO，写元数据；自动算 `hash_sha256`，重复返回 409 |
| GET | `/constraint-sources` | viewer+ | 列表，过滤 `authority` / `tag` / `q`，分页 |
| GET | `/constraint-sources/{sid}` | viewer+ | 详情 + 引用次数 |
| PATCH | `/constraint-sources/{sid}` | admin | 编辑元数据；版本变化自动写 `constraint_source_version_events` |
| DELETE | `/constraint-sources/{sid}` | admin | 软删；publish gate 检测引用 |
| GET | `/constraint-sources/{sid}/version-events` | viewer+ | 升版事件流 |

### 4.2 ConstraintSet 内的单条约束（CRUD）

沿用 ADR-0005 §5 已规划路由：

| 方法 | 路径 | 角色 | 说明 |
|---|---|---|---|
| GET | `/constraint-sets/{csid}/constraints` | viewer+ | 过滤 `kind`/`class`/`category`/`authority`/`review_status`/`tag`，分页 |
| POST | `/constraint-sets/{csid}/constraints` | operator+ | 手工录入；默认 `class=hard`、`authority=heuristic`、`review_status=approved`、`parse_method=MANUAL_UI` |
| PATCH | `/constraint-sets/{csid}/constraints/{cid}` | operator+ | 编辑；`review_status` 转换走合法路径校验 |
| DELETE | `/constraint-sets/{csid}/constraints/{cid}` | operator+ | 软删；`active` 集合受 freeze 触发器拦截 |
| POST | `/constraint-sets/{csid}/constraints:batch-import` | operator+ | Excel 模板批导，落库 `parse_method=EXCEL_IMPORT`、`review_status=draft` |

**兼容层** `/sites/{sid}/constraints` 保持不变，内部转发到该 site 的默认
`status='active'` 集合（详见 ADR-0005 §5）。

### 4.3 Citation（约束 ↔ 源 连接，= SOURCED_FROM 边）

| 方法 | 路径 | 角色 | 说明 |
|---|---|---|---|
| GET | `/process-constraints/{cid}/citations` | viewer+ | 单条约束的所有引用 |
| POST | `/process-constraints/{cid}/citations` | operator+ | 增加一条引用 |
| DELETE | `/process-constraints/{cid}/citations/{cite_id}` | operator+ | 移除引用 |

### 4.4 知识图谱视图（ConstraintSet 派生）

| 方法 | 路径 | 角色 | 说明 |
|---|---|---|---|
| GET | `/constraint-sets/{csid}/graph` | viewer+ | 返回节点 + 边，支持 `?depth=2&seed=cst_xxx` 子图 |

返回结构（前端可直接喂给 reactflow）：

```json
{
  "nodes": [
    {"id": "cst_F003_F005", "type": "CONSTRAINT",
     "label": "F-003 ↔ F-005 ≥ 500mm",
     "category": "SPATIAL", "class": "soft",
     "authority": "project", "review_status": "approved"},
    {"id": "src_mbd_2024_003", "type": "CONSTRAINT_SOURCE",
     "label": "翼根对接.CATProduct", "authority": "project"}
  ],
  "edges": [
    {"id": "cite_xxx", "from": "cst_F003_F005", "to": "src_mbd_2024_003",
     "relation": "SOURCED_FROM", "clause": "§3.2", "confidence": 0.92}
  ]
}
```

M4 后图里多出 `relation: CONFLICTS_WITH | SUPERSEDES`（蓝图 G6）。

### 4.5 Excel 批量导入模板

固化 `corpus/templates/constraints_v3.xlsx`，列：

```
constraint_id | kind | payload_json | class | category | authority | conformance | severity | weight | rule_expression | rationale | tags
```

后端 `:batch-import` 行级 `try/except`，返回 `{ ok, failed, errors[] }`，
落库 `parse_method=EXCEL_IMPORT`、`review_status=draft`。

### 4.6 三层提取（占位骨架）

本阶段只搭骨架：
- L1 PMI / MBOM 解析器：占位 `agents/constraint_agent/extractors/{pmi,mbom}.py`，
  签名锁死，实现 `raise NotImplementedError("M6")`
- L2 LLM 提取：占位 `extractors/llm_sop.py`，不联网
- L3 人工审核：UI + API 走通（review_status `draft → under_review → approved` 按钮）

密级守卫装饰器 `@require_local_llm_when_classified` 在 `classification ∈
{CONFIDENTIAL, SECRET}` 时强制本地 LLM 路由（本阶段日志 only，不真发）。

---

## 5. 前端重构（M2 交付物）

对照截图 2 的产品原型，把当前 [ConstraintsPanel.tsx](../web/src/components/constraints/ConstraintsPanel.tsx)
**一刀切重写为四象限布局**。文件改名为 `ConstraintsWorkbench.tsx`，老文件保留一个版本作 fallback，
首页按 query 参数 `?ui=v3` 切换，灰度一周后删除。

### 5.1 布局

```
┌─────────────┬───────────────────────────────────────────┬───────────┐
│ 左 ：来源 + │ 中 ：四个 Tab                              │ 右 ：详情 │
│ 解析 + Gate │  ① 约束列表  ② 知识图谱  ③ 冲突仲裁(M4)   │ + 溯源    │
│             │  ④ 审核队列(M5，本阶段灰显徽章计数即可)    │           │
│ 280px       │ flex-1                                     │ 360px     │
└─────────────┴───────────────────────────────────────────┴───────────┘
```

### 5.2 左栏组件清单

| 组件 | 文件 | 内容 |
|---|---|---|
| `DocumentUploader` | `web/src/components/constraints/DocumentUploader.tsx` | 拖拽上传，密级下拉，进度条 |
| `DocumentList` | `…/DocumentList.tsx` | 已上传文档 + 解析状态徽章 + 解析约束计数 |
| `ParseProgressCard` | `…/ParseProgressCard.tsx` | 当前会话进度（M1 简化为「待审 / 已审 / 总数」） |
| `OntologyStats` | `…/OntologyStats.tsx` | KG 节点边数；按 category 分桶 mini-bar |
| `GateChecks` | `…/GateChecks.tsx` | 6 项 Gate Check 占位列表（本阶段全部 disabled，仅展示） |

### 5.3 中栏 Tab ① 列表

新表头按截图 2：

```
ID | 类型 | 维度 | 权威 | 置信度 | 规则描述 | 状态
```

- 类型 = `enforcement`（HARD/SOFT/PREFERENCE，配色: rose / amber / sky）
- 维度 = `category`（SPATIAL/SEQUENCE/...，固定配色映射，写在 `constraintTheme.ts`）
- 权威 = `authority`（PMI/SOP/MBOM/EXPERT，作为 chip）
- 置信度 = `confidence`（0–1，渲染水平进度条 + 颜色）
- 状态 = `lifecycle`（已批准 / 待审 / 已驳回 / 已替代 / 草稿）

筛选：顶栏组合搜索（ID、规则文本子串）+ chip 多选（HARD / SOFT / PREFERENCE / 维度 / 来源）。

### 5.4 中栏 Tab ② 知识图谱

复用现有 [ConstraintGraph.tsx](../web/src/components/constraints/ConstraintGraph.tsx)
（`@xyflow/react + @dagrejs/dagre`），但数据源换成 §4.3 的 `/ontology/graph`。

节点视觉：
- `CONSTRAINT` 圆角矩形，按 `category` 配色
- `DOCUMENT` 文档图标
- `ASSET` 椭圆
- `OPERATION` 菱形

边视觉：
- `SOURCED_FROM` 灰色实线
- `GOVERNS` 蓝色实线
- `APPLIES_TO` 绿色实线
- `CONFLICTS_WITH`（M4）红色虚线，本阶段不渲染
- `SUPERSEDES`（M4）紫色双线，本阶段不渲染

交互：
- 点击节点 → 右栏详情联动
- 双击 `CONSTRAINT` 节点 → 跳到 Tab ① 并定位该行
- 右键节点 → 「以此为种子展开 2 跳」（调 `?seed=&depth=2`）

### 5.5 中栏 Tab ③ ④（占位）

- Tab ③ 冲突仲裁：渲染「该功能将在 M4 开放，当前后端尚未启用 Z3 求解」+ 链接到 ROADMAP
- Tab ④ 审核队列：渲染「待审约束 N 条」并把 `lifecycle=DRAFT|UNDER_REVIEW` 的清单
  以只读列表展示（按钮 disabled），让用户对未来工作流有感知

### 5.6 右栏详情

完全按截图 2 的右侧栏：

- Header：`constraint_id` + `enforcement` chip
- 字段块：type / category / authority / confidence / lifecycle / rule_text /
  affected_assets / tags
- **来源溯源块**：`source_doc_id` 可点击 → 在右栏抽屉里弹出文档元数据 +
  `source_locator.snippet` 高亮（PDF 预览 M3 再做）
- **Ontology Links 块**：列出该约束的所有图谱边（一行一边，可点跳）
- **AI 智能签**（M4 占位，本阶段渲染「等待 ConstraintAgent 接入」灰条）

### 5.7 类型与 API 客户端

- [web/src/lib/types.ts](../web/src/lib/types.ts) 新增：
  `ConstraintCategory`, `ConstraintReviewStatus`, `ConstraintParseMethod`,
  `ConstraintSource`, `ConstraintSourceVersionEvent`, `ConstraintSetGraph`,
  `ConstraintSetGraphNode`, `ConstraintSetGraphEdge`
  （`ConstraintItemV2` / `ConstraintAuthority` / `ConstraintConformance` /
  `ConstraintCitation` / `ConstraintScope` 已由 ADR-0005/0006 实现）
- [web/src/lib/api.ts](../web/src/lib/api.ts) 新增：
  `api.uploadConstraintSource`, `api.listConstraintSources`,
  `api.getConstraintSource`, `api.listSourceVersionEvents`,
  `api.batchImportConstraints`, `api.getConstraintSetGraph`,
  `api.listCitations`, `api.addCitation`, `api.removeCitation`

老的 `api.listConstraints` 兼容层保留。

---

## 6. 验收标准

每个里程碑必须满足全部条目才能进入下一个。

### M0（数据模型 = G1+G2+G4）

- [ ] migrations 0018/0019/0020 双向 round-trip 通过
- [ ] `python scripts/check_schema_drift.py` 零差异
- [ ] `python scripts/check_constraint_fk_matrix.py` 与蓝图 §2 完全一致
- [ ] `pytest tests/db/test_constraint_invariants.py -q` 验证 INV-1..INV-10 全部生效
- [ ] L0 契约测试 ≥ 50 条：枚举完整、CHECK 不变量、FK 级联、JSONB 形状

### M1（来源接入 = G3）

- [ ] 文档上传：multipart < 50MB 入 MinIO，`hash_sha256` 命中 → 409
- [ ] 手工录入约束：POST 后 `class=hard`、`authority=heuristic`、`review_status=approved`、
      `parse_method=MANUAL_UI`、`verified_*` 自动填充
- [ ] Excel 批量：模板 18 行导入 `{ ok: 18, failed: 0 }`，全部 `review_status=draft`
- [ ] L1 gold ≥ 10 条：固定输入 → 期望响应（含 `mcp_context_id` 链）
- [ ] 密级 `CONFIDENTIAL` 文档上传，结构化日志含 `llm_route=PRIVATE_LOCAL`（noop）

### M2（列表与图谱）

- [ ] 截图 2 的 7 列表头 1:1 对齐，置信度进度条颜色按 [0,0.5)/[0.5,0.8)/[0.8,1] 三段
- [ ] 知识图谱 100 节点 + 300 边渲染 FPS ≥ 30，节点点击 → 右栏详情 ≤ 100ms
- [ ] axe-core 0 critical / 0 serious
- [ ] 三状态齐全（empty / loading skeleton / error + retry + 可复制 `mcp_context_id`）
- [ ] Lighthouse Accessibility ≥ 95

---

## 7. 测试金字塔

| 层 | 数量下限 | 内容 |
|---|---|---|
| L0 契约 | ≥ 50 | 三表 schema、Pydantic round-trip、API 信封、枚举闭合性 |
| L1 gold | ≥ 15 | 上传 → 解析 → 列表 → 图谱 全链路冻结样本 |
| L2 silver | 标 `slow` | 大文档（500 约束）、密级路由、生命周期非法转换 |
| L3 LLM-judge | 留空 | M3 接入提取器后再加 |

新增脚本：
- `scripts/seed_ontology_demo.py` — 一键灌入截图 2 那张表（22 条约束 + 4 个文档），
  方便 demo 与 e2e。

---

## 8. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 双层模型增加复杂度，开发者搞混 Layer A/B | 中 | 文档第 0 节 + 路由前缀 `/ontology/` 物理隔离 + `compiled_from_constraint_id` 命名提示 |
| `category` 闭枚举增项需 ADR，节奏慢 | 低 | `tags` 自由标签作为缓冲；季度 review 把高频 tag 提升为 category |
| 知识图谱 PG 邻接表规模上限 | 中 | 监控边表行数，> 50k 时启动 Neo4j ADR |
| 前端旧 `ConstraintsPanel` 与新 `ConstraintsWorkbench` 并存期混乱 | 中 | query 参数灰度；旧文件加 `@deprecated` 注释；一周后物理删除 |
| 文档解析（M3）尚未实现，UI 显示「待解析」用户疑惑 | 低 | 文档卡片显示「人工录入模式」徽章，明确告知 |

---

## 9. 工作流（每个 PR 的形状）

按 [CONTRIBUTING.md](../CONTRIBUTING.md) + [PR 模板](../.github/pull_request_template.md)：

1. **PR-1（M0）**：alembic 迁移 + ORM + Pydantic + L0 测试。零 API 变更。
2. **PR-2（M1-a）**：`/documents` CRUD + MinIO 接线 + L0 + L1 gold（3 条）。
3. **PR-3（M1-b）**：`/ontology/constraints` CRUD + 手录 + L1 gold（5 条）。
4. **PR-4（M1-c）**：Excel 批量导入 + 模板文件 + L1 gold（2 条，正常 + 半数失败）。
5. **PR-5（M2-a）**：`ConstraintsWorkbench` 骨架 + 左栏 + Tab ① 列表 + 类型生成。
6. **PR-6（M2-b）**：Tab ② 知识图谱 + `/ontology/graph` API + 右栏详情。
7. **PR-7（M2-c）**：Tab ③ ④ 占位 + GateChecks 灰显 + a11y 通过 + 截图回归。

每个 PR 必须包含：Risk / Rollback / Test plan 三段，遵守
[CLAUDE.md §8](../CLAUDE.md#8-commits-prs-secrets)。

---

## 10. 与后续阶段的接口契约（防止返工）

本阶段**不预留 M4+ 字段**。M4 引入 `constraint_relations` 表（蓝图 G6）作为
CONFLICTS_WITH / SUPERSEDES 边的承载，独立 ADR；M3 LLM 抽取写入
`process_constraints.rule_expression`（已存在）与 `constraint_citations`
（已存在）。

保留的占位 API：
- `POST /constraint-sets/{csid}/publish` — ADR-0005 §5 已规划，本阶段实装
  publish gate 的 INV-7（DAG 无环）；INV-5（hard+regulatory 强制 citation）
  在 M1 §4.3 上线后启用；其余 ADR-0006 §3.2 规则在 M3 LLM 抽取启用后才有意义。

---

## 11. 启动顺序建议

1. 先评审本手册（30 min），把 §2 分类法、§3 表结构、§5 UI 布局三处的争议拍死
2. 落地 PR-1（M0），合并后 `seed_ontology_demo.py` 立刻可灌数据
3. PR-2 ~ PR-4 并行（来源接入是独立切片）
4. PR-5 ~ PR-7 串行（前端依赖累加）

预计 7 个 PR、3 周完成 M0–M2，进入 M3 求解器接入阶段。
