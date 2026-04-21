# 三大补全任务 — 执行计划

> **范围**: (1) `CLAUDE.md` 最佳实践重写 (2) ParseAgent 用户交互 Dashboard (3) 数据架构 / 数据库 / Schema 设计
> **背景**: ParseAgent v1.0 GA 已完成 (S1-T1/S2-T2/S2-T3/S2-T4 + 127 单测全绿), 准备推进配套基建。
> **预估周期**: 3.5 个工作周 (W1=CLAUDE+Schema-A, W2=Schema-B+Dashboard 后端+可观测性, W3=Dashboard 前端+联调, +0.5 周缓冲)
> **状态**: planning
> **修订**: r2 — 合入补充建议 (除 Performance budget 外全部纳入)

---

## 任务 1 — CLAUDE.md 重写 (最佳实践向)

### 1.1 现状差距
当前 `CLAUDE.md` 偏 PoC/Spike 阶段叙事 (10 个 spike 介绍占比过高), 缺少 **Build/Test/Lint/Type-check 命令矩阵**、**代码规范** 和 **禁止项清单**, AI 协作时无法稳定遵循约定。

### 1.2 目标结构 (按用户要求重新分节,r2 增 3 节)

| § | 节标题 | 内容要点 |
|---|---|---|
| 1 | **Project Overview** | Stack (Python 3.11+/FastAPI/Pydantic v2/PostgreSQL+PostGIS/MCP/Temporal/React+Three.js), Architecture (5-Agent + Orchestrator + DB + Frontend), Key Directories (`agents/`, `shared/`, `db/`, `scripts/`, `ExcPlan/`, `PRD/`, `spikes/`) |
| 2 | **Build and Test Commands** | `uv sync` / 单测 `pytest agents/parse_agent/tests/test_X.py::test_Y` / Lint `ruff check .` / Type `mypy agents/ shared/` / Gold `python scripts/gold_eval.py` / Schema drift `python scripts/check_schema_drift.py` |
| 3 | **Code Conventions** | Named exports only / Interfaces 用 `Protocol` (Python) 或 `IXxx` (TS) / Errors 必须 typed (`raise XxxError`)、严禁裸 `except` / Imports 三段式 (stdlib → 3rd → local) / 公共 API 必带 docstring + 类型 |
| 4 | **Things to Avoid** | 禁 `Any` / 禁已弃用包 (`pkg_resources`, `imp`) / 禁直接改 `db/migrations/*.sql` (要新建 NNN_xxx.sql) / 禁 emoji / 禁 `print` (用 `logging.getLogger(__name__)`) / 禁 agent 间直接共享 DB (走 MCP) / 禁 `requirements.txt` 手改 (用 `uv lock`) / 禁 `.env*` 入仓 |
| 5 | **Agent Collaboration Rules** ⭐新增 | MCP-only 通信; 任何 agent 不得 `from agents.<other>.service import` (违规 CI 拒绝); `mcp_context_id` 全链透传; 子任务调度走 Orchestrator |
| 6 | **Memory & Skills 协议** ⭐新增 | 任何任务前先 `view /memories/repo/`; 复杂搜索用 `runSubagent Explore (thoroughness)`; SKILL.md 命中即必读; 写入 memory 用单行要点 |
| 7 | **Testing Pyramid** ⭐新增 | L0 contract/schema ≥ 30 / L1 gold ≥ 10 / L2 silver / L3 LLM-judge; 新模块 PR 必须证明覆盖 L0+L1; 比例参考 `parse_agent_ga_execution_plan.md §7.5` |
| 8 | **Commit / PR & Secrets** | Conventional Commits (feat/fix/refactor/...); PR 模板必填 risk + rollback + test_plan; secrets 走 `.env.local` (gitignored) + `OPENAI_API_KEY` 等列入禁入仓清单 |
| 9 | **Domain Concepts** | (保留 SiteModel/Asset/ConstraintSet/...) |
| 10 | **Engineering Philosophy** | (保留 Palantir Ontology) |
| 11 | **UI/UX Conventions** | (保留 no-emoji + 浅色调) |

### 1.3 交付物
- `CLAUDE.md` 重写 (11 节), 旧版用 git diff 留痕
- `.github/copilot-instructions.md` 同步精简版 (300 行内,供 Copilot 使用)
- `.github/PULL_REQUEST_TEMPLATE.md` 含 risk/rollback/test_plan 三栏
- `.gitignore` 显式列 `.env*` / `*.local.*`

### 1.4 验收标准 (DoD)
- [ ] 11 节齐全, 每节 ≤ 30 行
- [ ] Commands 节所有命令在干净 venv 中可执行 (CI 跑一次 smoke)
- [ ] grep `CLAUDE.md` 不含 emoji
- [ ] Things-to-Avoid + Agent-Collaboration 每条规则有 1 个反例代码片段
- [ ] CI lint job 验证 `from agents.<X>` 不被其他 agent import (`scripts/check_agent_isolation.py`)
- [ ] PR 通过 review (≥ 1 owner)

### 1.5 工时
0.75 人日 (+0.25 来自新增 3 节 + isolation 检查脚本)。

---

## 任务 2 — ParseAgent 用户交互 Dashboard 设计

### 2.1 用户故事 (6 个核心场景)

| # | 角色 | 故事 |
|---|---|---|
| US-1 | CAD 工程师 | 上传 DWG, 实时看到解析进度 (L1→L5 stage gates) |
| US-2 | CAD 工程师 | 看到 SiteModel 可视化 (Assets / Zones / Annotations 不同颜色) |
| US-3 | 工艺标注员 | 看到分类置信度直方图, 一键筛选 `confidence < 0.4` 的资产做人工纠错 |
| US-4 | Reviewer | 看到 Quarantine 队列, 对 LLM 提议的新词条 approve / reject / merge |
| US-5 | Ops/SRE | 看到 H1-H7 hooks 的命中次数 + H4 LLM 调用费用面板 |
| US-6 | PM | 看到 Gold/Silver/LLM-Judge 三层指标趋势图 (按 commit 对比) |

### 2.2 信息架构 (4 个 Tab)

```
ParseAgent Dashboard
├── ① Run Console     (US-1, US-2)  ← 上传 + 进度 + 3D 预览
├── ② Quality Lab     (US-3, US-6)  ← 置信度分布 + 指标趋势 + diff
├── ③ Review Queue    (US-4)         ← Quarantine CSV 在线人审界面
└── ④ Ops Panel       (US-5)         ← Hooks 命中 + 预算 + 错误 top-N
```

### 2.3 技术选型

| 层 | 选型 | 理由 |
|---|---|---|
| 前端 | Next.js 14 (App Router) + React 18 + TanStack Query + Zustand | 与 `VisualizeUnknow/web/` 已有栈对齐 |
| 3D 视图 | Three.js + react-three-fiber | 与 spike_07 一致 |
| 图表 | Recharts (置信度直方图) + ECharts (指标趋势, 大屏友好) | 轻量 + 富表达 |
| 后端 BFF | FastAPI 路由扩展 `agents/parse_agent/app.py` 新增 `/dashboard/*` | 复用现有 service |
| 实时进度 | WebSocket (FastAPI `WebSocketRoute`) 推送 stage_gate 事件 | <100ms 延迟 |
| 鉴权 | 暂用 token (header `X-Agent-Token`), GA 后接公司 SSO | 不阻塞 PoC |

### 2.4 后端 API 增量 (FastAPI)

| 方法 | 路径 | 用途 | 阶段 |
|---|---|---|---|
| POST | `/dashboard/runs` | 上传 DWG, 返回 `run_id` | W2 |
| GET | `/dashboard/runs/{id}` | 单次运行的详情 (SiteModel + 指标) | W2 |
| GET | `/dashboard/runs` | 历史 runs 分页 | W2 |
| WS | `/dashboard/runs/{id}/stream` | stage_gate / hook_fire 事件 | W2 |
| GET | `/dashboard/quality/trend?metric=gold` | 时间序列指标 | W3 |
| GET | `/dashboard/quarantine` | 待审词条列表 (调用 `promote_taxonomy_terms.aggregate`) | W3 |
| POST | `/dashboard/quarantine/{term_hash}/decision` | approve/reject | W3 |
| GET | `/dashboard/ops/hooks` | H1-H7 命中计数 (从 `result_store` 汇总) | W3 |

### 2.5 前端目录结构 (新增 `agents/parse_agent/dashboard/`)
```
dashboard/
├── package.json
├── next.config.js
├── tsconfig.json
├── src/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx                  # ① Run Console
│   │   ├── quality/page.tsx          # ② Quality Lab
│   │   ├── review/page.tsx           # ③ Review Queue
│   │   └── ops/page.tsx              # ④ Ops Panel
│   ├── components/
│   │   ├── SiteModel3D.tsx
│   │   ├── ConfidenceHistogram.tsx
│   │   ├── StageGateTimeline.tsx
│   │   └── ReviewRow.tsx
│   ├── lib/
│   │   ├── api.ts                    # fetch wrappers
│   │   └── ws.ts                     # WebSocket helper
│   └── types/parse-agent.d.ts        # 由 Pydantic 模型生成
└── tests/                            # vitest + RTL
```

### 2.6 设计约束 (源自 CLAUDE.md UI/UX)
- 无 emoji, 用 SVG icons (heroicons outline)
- 浅色基调 (#f7fafc 背景, #2563eb 强调蓝, #14b8a6 teal)
- Tailwind 配置色板预设
- 留白 ≥ 24px, 卡片阴影 ≤ `shadow-sm`
- **空状态 + 骨架屏强制**: 所有列表/图表组件必须实现 empty / loading / error 三态
- **a11y baseline**: 键盘可达 + ARIA label + 色盲安全配色; CI 跑 axe-core (Lighthouse a11y ≥ 95)
- **i18n 骨架**: i18next, zh-CN 默认, en 仅占位 (key 全量, value 可 TODO)

### 2.6.1 ⭐ Diff 视图 (Quality Lab 子能力)
- 选两个 run_id (同 DWG / 不同 commit) → 并排展示 SiteModel
- 高亮: type 变化 (红/绿)、confidence Δ ≥ 0.1 (橙)、新增/消失资产
- 底层: 通过 `asset_guid` join, fallback 用 (block_name, layer, coords) 模糊匹配
- 没有 diff 视图 = 无法防回归 (必加项)

### 2.6.2 ⭐ 错误恢复 UX
- 上传失败 / ODA timeout / H4 budget 超 / WebSocket 断 → 统一 ErrorBoundary 弹卡
- 必含: 友好文案 + 一键 retry + 复制 `mcp_context_id` 按钮 + "复制错误报告"
- 后端错误响应统一 envelope: `{error_code, message, mcp_context_id, retryable}`

### 2.6.3 ⭐ 可观测性 3 件套 (后端必装)
- **结构化日志**: `structlog` 输出 JSON, 字段含 `mcp_context_id`/`run_id`/`hook`/`stage_gate`
- **Prometheus 指标**: `/metrics` 暴露 `parse_runs_total{status}` / `hook_fires_total{hook}` / `llm_tokens_total` / `request_duration_seconds_bucket`
- **OpenTelemetry trace**: FastAPI middleware 注入 traceparent, 所有 H1-H7 hook 起 span; trace 入 `mcp_context_id` 作为 baggage
- 三者上线后 Ops Panel 才有真数据

### 2.6.4 权限模型 v0 (RBAC)
- 4 角色: `viewer` (只读) / `operator` (上传+触发) / `reviewer` (Quarantine 决策) / `admin`
- 实现: PG row-level security policy + FastAPI `Depends(require_role(...))`
- 接 audit_log: 所有 reviewer 决策入 `audit_log` 表

### 2.6.5 部署兜底
- **WebSocket → SSE 退路**: 通过 env `DASHBOARD_REALTIME_MODE=ws|sse` 切换
- **Feature flag**: Tab④ Ops 默认 hidden, 通过 `ENABLE_OPS_PANEL=true` 开启
- **3D 性能门**: asset > 5000 时启用 InstancedMesh + LOD; > 20000 提示用户切换 2D 平面图模式

### 2.7 里程碑

| 里程碑 | 交付内容 | 完成判定 |
|---|---|---|
| M1 (W2 mid) | API 4 个 + 可观测性 3 件套 + 前端骨架 + Tab① Run Console | E2E 上传 DWG → 3D 预览; `/metrics` 出指标; trace 可在 Jaeger 看到 |
| M2 (W3 mid) | Tab② (含 Diff 视图) + Tab③ Review Queue + WebSocket/SSE | 实时进度 + 置信度直方图 + 两 run diff + Quarantine 人审入 audit_log |
| M3 (W3 end) | Tab④ Ops + RBAC + i18n 骨架 + a11y 通过 | Ops 看 H4 费用; reviewer 角色拦截; axe-core/Lighthouse 全绿 |

### 2.8 验收标准
- 单测覆盖 ≥ 70% (后端) / ≥ 60% (前端组件)
- Lighthouse Accessibility ≥ 95; axe-core 0 critical
- 无 console.error / 无 React key warning
- 通过 PRD 中"无 emoji + 浅色调"复核
- 所有列表/图表实现 empty/loading/error 三态 (UI 走查 checklist)
- 错误响应统一 envelope (后端 contract 测试)
- RBAC 4 角色端到端验证 (4 条 happy + 4 条 forbidden)

### 2.9 工时
后端 4 人日 (含可观测性+RBAC) + 前端 6 人日 (含 diff/i18n/a11y/error UX) = **10 人日**

---

## 任务 3 — 数据架构 / 数据库 / Schema 设计

### 3.1 现状差距
当前仅 `db/migrations/001_initial.sql` 一份初始 DDL, 覆盖 mcp_contexts/site_models/constraint_sets/layout_candidates 表骨架, 但:
- 缺 **PostGIS 空间索引** (Asset.footprint geometry)
- 缺 **TimescaleDB hypertable** (mcp_contexts 时间分区)
- 缺 **审计表** (谁在何时通过 quarantine 词条)
- 缺 **存储分层策略** (热: PG / 温: MinIO / 冷: S3 Glacier 等)
- 缺 **统一 ER 图 + Schema 演进契约**
- 缺 **Alembic 迁移管理** (现裸 SQL 无 down/checksum, 推迟将来代价大)
- 缺 **软删除 + 时间旅行** (工厂图纸频繁修订必须可回溯)
- 缺 **schema_version 列** (字段级契约版本)
- 缺 **数据资产台账** (合规与 DR 用)

### 3.2 数据资产分层 (三层存储)

| 层 | 存储 | 数据类型 | 保留周期 |
|---|---|---|---|
| Hot | PostgreSQL 16 + PostGIS + TimescaleDB | SiteModel / Constraint / Layout / mcp_contexts (近 30d) | 30 天 |
| Warm | MinIO | DWG/DXF 原文件、render 缩略图、SiteModel JSON 快照 | 365 天 |
| Cold | S3 Glacier (or local cold disk) | mcp_contexts (>30d)、PR LLM 回放 | 7 年 (合规) |

### 3.3 数据流 (DFD)
```
DWG/DXF
   │ (POST /mcp/agent/parse)
   ▼
ParseAgent ──► SiteModel (PG) + raw DWG (MinIO) + mcp_context (TimescaleDB)
   │
   │ ParseAgent.tools.propose_taxonomy_term
   ▼
exp/llm_classifications/*.jsonl (本地)
   │ (周聚合: scripts/promote_taxonomy_terms.py)
   ▼
quarantine_terms 表 (PG, 待人审)
   │ (人审 approve)
   ▼
taxonomy_terms 表 (PG, 生效词表) ──► 下次 ParseAgent 启动时加载
```

### 3.4 Schema 设计 (新建 + 演进)

#### 3.4.1 演进规则 (写入 CLAUDE.md Things-to-Avoid)
- **Never edit** `db/migrations/00X_*.sql` 已合入主干的迁移
- 新 schema 改动 → 新建 Alembic revision (`alembic revision -m "..."`); 必须含 `upgrade()` + `downgrade()`
- 字段重命名 = expand → migrate → contract 三步走 (零停机)
- **每张业务表** 必有 `schema_version SMALLINT NOT NULL DEFAULT 1` 列, breaking change 时 ++
- **每张业务表** 必有 `deleted_at TIMESTAMPTZ` (软删除); 查询默认 `WHERE deleted_at IS NULL`
- SiteModel 等高频修订对象用 PG `tstzrange` 表生命周期, 配合 `EXCLUDE USING gist` 防重叠

#### 3.4.1.1 ⭐ Alembic 接管 (W1 必做)
- 新建 `db/alembic.ini` + `db/alembic/env.py` 指向 `shared/db_schemas.py`
- 把现有 `001_initial.sql` 用 `alembic stamp` 标记为 baseline 0001
- 后续 002~005 全部走 `alembic revision --autogenerate`, 人工审 diff 后提交
- CI: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` 三步

#### 3.4.1.2 ⭐ schema_version + 软删除 + check 约束 模板
```sql
-- 每张业务表通用结尾
schema_version  SMALLINT NOT NULL DEFAULT 1,
deleted_at      TIMESTAMPTZ,
mcp_context_id  VARCHAR(100) REFERENCES mcp_contexts(mcp_context_id),
CONSTRAINT confidence_range CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
CONSTRAINT asset_type_enum CHECK (asset_type IN (
    'Equipment','Conveyor','LiftingPoint','Zone','Annotation','Other','Unknown',
    'Wall','Door','Pipe','Column','Window','CncMachine','ElectricalPanel','StorageRack'
))
```

#### 3.4.2 新增表清单 (4 个)

**`db/migrations/002_postgis_spatial.sql`**
```sql
CREATE EXTENSION IF NOT EXISTS postgis;
ALTER TABLE site_models ADD COLUMN bbox geometry(Polygon, 0);
CREATE INDEX idx_site_models_bbox ON site_models USING GIST (bbox);

CREATE TABLE asset_geometries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_model_id VARCHAR(50) REFERENCES site_models(site_model_id),
    asset_guid VARCHAR(50) NOT NULL,
    asset_type VARCHAR(30) NOT NULL,
    footprint geometry(Polygon, 0),
    centroid geometry(Point, 0),
    confidence NUMERIC(4,3),
    classifier_kind VARCHAR(40),
    UNIQUE (site_model_id, asset_guid)
);
CREATE INDEX idx_asset_geom_footprint ON asset_geometries USING GIST (footprint);
CREATE INDEX idx_asset_geom_type ON asset_geometries (asset_type);
```

**`db/migrations/003_timescale_mcp.sql`**
```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
SELECT create_hypertable('mcp_contexts', 'timestamp',
                          chunk_time_interval => INTERVAL '7 days',
                          if_not_exists => TRUE);
SELECT add_retention_policy('mcp_contexts', INTERVAL '30 days');
```

**`db/migrations/004_taxonomy_quarantine.sql`** (示例 SQL, 实际经 Alembic 生成)
```sql
CREATE TABLE taxonomy_terms (
    id BIGSERIAL PRIMARY KEY,
    term TEXT NOT NULL,
    term_normalized TEXT NOT NULL,
    asset_type VARCHAR(30) NOT NULL,
    source VARCHAR(20) NOT NULL,        -- 'gold' | 'llm_promoted' | 'manual'
    approved_by VARCHAR(50),
    approved_at TIMESTAMPTZ,
    enabled BOOLEAN DEFAULT TRUE,
    schema_version SMALLINT NOT NULL DEFAULT 1,
    deleted_at TIMESTAMPTZ,
    UNIQUE (term_normalized, asset_type) WHERE deleted_at IS NULL,
    CONSTRAINT asset_type_enum CHECK (asset_type IN (...))
);

CREATE TABLE quarantine_terms (
    id BIGSERIAL PRIMARY KEY,
    term_hash CHAR(8) NOT NULL,
    term TEXT NOT NULL,
    term_normalized TEXT NOT NULL,
    asset_type VARCHAR(30) NOT NULL,
    count INT NOT NULL DEFAULT 1,
    evidence JSONB NOT NULL DEFAULT '[]',
    first_seen TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    decision VARCHAR(20),              -- NULL=pending|approve|reject|merge
    decided_by VARCHAR(50),
    decided_at TIMESTAMPTZ,
    mcp_context_id VARCHAR(100) REFERENCES mcp_contexts(mcp_context_id),
    schema_version SMALLINT NOT NULL DEFAULT 1,
    deleted_at TIMESTAMPTZ,
    UNIQUE (term_hash, asset_type)
);
CREATE INDEX idx_quar_decision ON quarantine_terms (decision);
CREATE INDEX idx_quar_mcp ON quarantine_terms (mcp_context_id);
```

**`db/migrations/005_audit.sql`**
```sql
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    actor VARCHAR(50) NOT NULL,         -- user_id | agent_name
    actor_role VARCHAR(20),             -- viewer/operator/reviewer/admin
    action VARCHAR(50) NOT NULL,        -- 'approve_term' | 'override_classification' | ...
    target_type VARCHAR(30) NOT NULL,
    target_id VARCHAR(100) NOT NULL,
    payload JSONB DEFAULT '{}',
    mcp_context_id VARCHAR(100) REFERENCES mcp_contexts(mcp_context_id),
    ts TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_audit_target ON audit_log (target_type, target_id);
CREATE INDEX idx_audit_ts ON audit_log (ts DESC);
CREATE INDEX idx_audit_mcp ON audit_log (mcp_context_id);
```

**`db/migrations/006_pgvector_reserve.sql`** ⭐ Phase 5 预留
```sql
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE asset_geometries
  ADD COLUMN embedding vector(384);   -- 留位, 暂不索引
-- Phase 5 启用 search_similar_blocks 时:
--   CREATE INDEX idx_asset_emb ON asset_geometries USING ivfflat (embedding vector_cosine_ops);
```

### 3.5 ER 概览 (Mermaid 草图, 详图 W1 完成 → `docs/data_architecture.md`)
```
mcp_contexts ──┐ (FK 出现在所有业务表, 全链路反查)
               ├─< site_models ──< asset_geometries (含 embedding 预留)
               │
               ├─< constraint_sets
               │
               ├─< layout_candidates
               │
               ├─< quarantine_terms ──(approve)──> taxonomy_terms
               │
               └─< audit_log (谁/何时/对谁/做了什么)
```

### 3.5.1 ⭐ 数据血缘 (lineage) 显式建模
- 任一 LayoutCandidate → `site_model_id` → `mcp_context_id` → `cad_source.dwg_hash` → 上传者
- 在 ER 图中用粗箭头标注 lineage 关键路径
- Dashboard Diff 视图与血缘共享底层 join 逻辑

### 3.6 Pydantic ↔ DDL 同步策略
- `shared/models.py` 是 Pydantic 真源
- 新建 `shared/db_schemas.py` 用 SQLAlchemy 2.0 declarative 映射 (供 ORM/Alembic autogenerate)
- CI 增加 `scripts/check_schema_drift.py`: 比对 Pydantic 字段 vs DDL 列, **`required` 字段缺失 → fail**, 其他差异 → warn (减噪)

### 3.7 备份与恢复
- PG: `pg_basebackup` 每日 + WAL 归档至 MinIO
- MinIO: 跨桶版本化 + 7 天软删
- DR 演练: 每季度一次, 文档记录 RTO/RPO
- 冷数据 (>30d mcp_contexts) 导出为 **Parquet** 写入 S3 Glacier (省 70% 空间, BI 直查)

### 3.8 数据安全
- 所有 PII (用户名、审批记录) AES-256 at-rest
- mcp_contexts.input_payload 中 DWG hash 而非原文件
- TLS 1.3 in-transit
- 角色: `parse_agent_rw` / `dashboard_ro` / `dashboard_rw` / `reviewer` / `admin` 5 类 PG role + RLS
- **数据资产台账** `docs/data_inventory.md`: 字段 → 类别 (PII/business/audit) → 保留期 → 加密方式 → owner

### 3.8.1 ⭐ CDC 通道占位
- 启用 PG `wal_level=logical` + replication slot `parse_agent_cdc`
- 暂不接消费者, Phase 5 接 NATS JetStream → Dashboard 实时推送 (替代轮询)
- 文档化连接参数, 留 `scripts/start_cdc_consumer.py` 占位

### 3.8.2 ⭐ 测试数据夹具
- `db/fixtures/seed.sql` — 1 份金标准 DWG 解析后的 SiteModel + 1 份病态 DWG
- pytest `db_fixture` marker, conftest 提供 `db_session` + auto-rollback
- E2E / demo / 截图 全部基于此 seed, 避免每次找数据

### 3.9 验收标准
- [ ] Alembic 接管, baseline 0001 + 002~006 五份 revision 在干净 PG 16 中 `upgrade head && downgrade -1 && upgrade head` 三步通过
- [ ] 每张业务表都有 `schema_version` + `deleted_at` + `mcp_context_id` 三列
- [ ] `confidence`/`asset_type` CHECK 约束生效 (插入越界值返回 error)
- [ ] `check_schema_drift.py` CI 通过 (required 字段不缺)
- [ ] `check_agent_isolation.py` CI 通过 (无 cross-agent import)
- [ ] ER 图 + lineage 路径归档到 `docs/data_architecture.md`
- [ ] `docs/data_inventory.md` 列全所有 PII/business/audit 字段
- [ ] 备份脚本在测试环境 dry-run 成功
- [ ] CDC slot 创建成功, 消费者占位脚本可运行 (no-op)
- [ ] `db/fixtures/seed.sql` 可被 pytest `db_fixture` marker 加载

### 3.10 工时
Alembic 接管 0.5 人日 + SQL 5 份 + 文档 2 人日 + ORM 同步 + drift/isolation 检查 1 人日 + 数据台账 + CDC 占位 0.5 人日 + 夹具 0.5 人日 = **4.5 人日**

---

## 总体时间线 (r2 重排)

```
Week 1  ┌─────────────┐  ┌─────────────────────────────────────────┐
        │ T1 CLAUDE   │  │ T3 Schema Phase A:                      │
        │ (11 节)     │  │   Alembic 接管 + 002 PostGIS + 003 TS  │
        │             │  │   + soft-delete/schema_version 模板     │
        │             │  │   + ER 图 + data_inventory              │
        └─────────────┘  └─────────────────────────────────────────┘

Week 2  ┌─────────────────────────────────────────┐  ┌──────────────────────┐
        │ T3 Schema Phase B:                      │  │ T2 后端 + 可观测性   │
        │   004 quarantine + 005 audit + 006 vec │  │   FastAPI /dashboard/│
        │   + drift CI + agent isolation CI      │  │   + structlog + OTel │
        │   + db fixtures + CDC slot 占位        │  │   + Prom /metrics    │
        └─────────────────────────────────────────┘  │   + RBAC 4 角色      │
                                                     │   + Tab① 骨架       │
                                                     └──────────────────────┘
        M1: E2E 上传→3D 预览 + /metrics 出指标 + trace 可看

Week 3  ┌──────────────────────────────────────────────────────┐
        │ T2 Dashboard 前端 Tab②(含 Diff)/③/④ + 联调          │
        │ + i18n 骨架 + a11y (axe-core) + 错误恢复 UX           │
        │ + WebSocket→SSE 退路 + Feature flag                  │
        └──────────────────────────────────────────────────────┘
        M2: Quality Lab + Diff + Review Queue 上线
        M3: Ops Panel + RBAC 端到端 + Lighthouse 全绿

Week 3.5 (缓冲)  Demo 数据集入仓 + ADR 写作 + 回滚演练 + DR dry-run
```

总工时: **0.75 (T1) + 10 (T2) + 4.5 (T3) + 1 (跨任务) = 16.25 人日** (≈ 3.3 周, 单人节奏)

---

## 跨任务隐性需求 (r2 新增)

### X.1 CI 三段式 workflow
`.github/workflows/full_quality.yml`:
```
schema-check (alembic + drift + isolation)
  → unit (pytest agents/ shared/)
  → integration (docker-compose up + e2e API)
  → gold-regression (gold_eval thresholds)
```
任一段红 block PR. 已有 `parse_agent_quality.yml` 并入此 pipeline.

### X.2 本地一键启动 `scripts/dev_up.ps1`
- `docker-compose up -d` (PG+PostGIS+TimescaleDB+MinIO+Redis+Jaeger)
- `alembic upgrade head` + 加载 `db/fixtures/seed.sql`
- `uvicorn agents.parse_agent.app:app --reload` (port 8001)
- `cd agents/parse_agent/dashboard && pnpm dev` (port 3010)
- 全部就绪后打印 "http://localhost:3010 ready"

### X.3 Demo 数据集入仓
- `tests/data/demo_golden.dwg` (≤2 MB) — 标准产线
- `tests/data/demo_pathological.dwg` (≤3 MB) — 系统层占 95%, 测降级
- 所有 demo / 截图 / E2E / Dashboard 默认数据 全用此两份
- README 标注: 不得替换, 替换需新 ADR

### X.4 ADR (Architecture Decision Records)
`docs/adr/000N-<topic>.md`, 本计划至少 4 篇:
- ADR-0001 选 Alembic 而非裸 SQL
- ADR-0002 选 Next.js 14 App Router 而非 SPA
- ADR-0003 选 PostGIS + TimescaleDB 而非分库
- ADR-0004 选 OpenTelemetry + structlog + Prom 三件套

### X.5 回滚预案
- Dashboard: env `DASHBOARD_KILLSWITCH=true` → FastAPI 路由全 503; 前端显示维护页
- Schema: 任一 alembic revision 都必须经 `downgrade -1` 测试通过才允许合入
- ParseAgent: 保留上一版 wheel; `agents/parse_agent/agent.json` 旧版 tag 留在 git

---

## 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| PostGIS/TimescaleDB 本地环境缺失 | T3 阻塞 | `docker-compose.yml` 增量服务定义 + dev_up.ps1 |
| Next.js 与现有 `VisualizeUnknow/web` 冲突 | T2 路径混乱 | 独立 `agents/parse_agent/dashboard/` 目录, 端口 3010 |
| Schema drift 检查误报 | CI 噪声 | 仅 fail-on `required` 字段缺失, warn-on 其他 |
| Quarantine 决策审计成本 | T3 复杂度 ↑ | audit_log 表 W2 先建, Dashboard M3 接入 |
| WebSocket 被企业代理封 | M2 实时进度失败 | env 切 SSE 退路, 已设计 |
| Alembic autogenerate 错判 | 误改 schema | 强制人工审 diff, CI 跑 down→up→down 三循环 |
| RBAC 与 PG RLS 配置复杂 | M3 阻塞 | 仅 Dashboard 4 角色 + 1 admin 起步, 不接 SSO |
| 3D 大图纸卡顿 | UX 退化 | InstancedMesh + LOD + >20k 切 2D 模式 |

---

## 与既有计划的衔接

- 与 `parse_agent_ga_execution_plan.md` §7.5 GA 验收并行 (不影响 GA 时间窗)
- T2 Dashboard 复用 `result_store.py` / `llm_quality.py` / `tools/registry.py`
- T3 数据架构上线后, ParseAgent `propose_taxonomy_term` 工具可从 jsonl 改写 `quarantine_terms` 表 (P5 切换, 不在本计划)

---

## 立即可启动项 (建议顺序, r2 重排)

1. **今天**: 重写 CLAUDE.md 11 节 (T1) — 含新增 Agent Collab / Memory&Skills / Testing Pyramid / Commit-Secrets 4 节
2. **W1 中**: Alembic 接管 + baseline 0001 stamp + 002 PostGIS + 003 TimescaleDB (T3 Phase A)
3. **W1 末**: ER 图 + data_inventory + soft-delete/schema_version 模板写入 db_schemas.py
4. **W2 周一**: 启动 Dashboard 后端 + 可观测性 3 件套 (structlog + OTel + Prom) + 004/005/006 migration
5. **W2 中**: drift CI + agent isolation CI + db fixtures + CDC slot 占位
6. **W2 周五**: M1 demo (上传→3D 预览 + 指标 + trace)
7. **W3 周一-周三**: Tab② Quality Lab (含 Diff 视图) + Tab③ Review Queue + RBAC + audit_log 接入 → M2
8. **W3 周四-周五**: Tab④ Ops + i18n 骨架 + a11y axe-core + 错误恢复 UX + Lighthouse → M3
9. **W3.5 缓冲**: Demo 数据集入仓 + ADR 4 篇 + DR dry-run + 回滚演练
