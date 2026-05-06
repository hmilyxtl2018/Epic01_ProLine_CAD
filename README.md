# ProLine CAD — 航空工艺产线 AI 规划平台

> AI-driven aerospace production line lifecycle planning platform.
> 五智能体闭环（Parse → Constraint → Layout → Simulation → Report），
> Orchestrator 统一调度，**MCP 协议为唯一跨 Agent 通道**，全链路 `mcp_context_id` 可追溯。

**当前阶段**：ParseAgent v1.0 GA / ConstraintAgent M0 蓝图（category +
review_status + source hash 已落地）；LayoutAgent / SimAgent / ReportAgent
按 [docs/ROADMAP_3D_SIM.md](docs/ROADMAP_3D_SIM.md) 推进。

---

## 系统架构

```
                                  ┌──────────────────┐
                                  │  Orchestrator     │
                                  │  (Temporal-bound) │
                                  └─────────┬─────────┘
                                            │ MCP only
            ┌────────────────┬──────────────┼──────────────┬────────────────┐
            ▼                ▼              ▼              ▼                ▼
   ┌────────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────────┐
   │  ParseAgent    │ │ Constraint │ │  Layout    │ │ Simulation │ │ ReportAgent     │
   │  DWG/IFC/STEP  │ │   Agent    │ │   Agent    │ │   Agent    │ │ (Feasibility)   │
   │  → SiteModel   │ │  Z3 / KG   │ │  GA / GP   │ │  DES / PINN│ │  PDF / DOCX     │
   └────────┬───────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └────────┬───────┘
            │               │               │               │                  │
            └───────────────┴───────┬───────┴───────────────┴──────────────────┘
                                    ▼
                            ┌─────────────────┐
                            │ Dashboard BFF   │  app/  (FastAPI + Pydantic v2)
                            │ + Web UI        │  web/  (Next.js 14 + React 18)
                            └────────┬────────┘
                                     │
                            ┌────────┴────────┐
                            │ Postgres 16 +   │  PostGIS · TimescaleDB · pgvector
                            │ MinIO · NATS    │  (docker-compose.yml)
                            │ Redis           │
                            └─────────────────┘
```

**铁律**：Agent 之间不允许直接 import / HTTP 调用；所有跨 Agent 数据流以
`mcp_context_id` 为脊椎，由 Orchestrator 派发。详见 [CLAUDE.md](CLAUDE.md) §5。

---

## 快速开始

### 环境要求

- Python ≥ 3.11（推荐 3.13）
- Node.js ≥ 20（前端 dashboard）
- Docker & Docker Compose（PostGIS + MinIO + Redis 等）
- Git

### 安装

```powershell
# 克隆仓库
git clone https://github.com/your-org/proline-cad.git
cd proline-cad

# Python 虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1               # Windows PowerShell
# source .venv/bin/activate                # Linux / macOS

# 全栈安装（按需选 extras）
pip install -e ".[parse,constraint,layout,dev]"

# 前端依赖
npm --prefix web install
```

### 一键启动开发环境

```powershell
# 拉起 PostGIS 容器 + 跑 Alembic 迁移 + 启动 FastAPI (8000)
.\scripts\dev_up.ps1 -ServeApi

# 另一终端：启动 Next.js dashboard (3000)
npm --prefix web run dev
```

打开 [http://localhost:3000](http://localhost:3000)。后端 OpenAPI 文档：
[http://localhost:8000/docs](http://localhost:8000/docs)。

### 运行测试

```powershell
# Agent 单元 / 集成测试
pytest agents/parse_agent/tests/ -q
pytest agents/constraint_agent/tests/ -q

# 数据库不变量（需 POSTGRES_DSN）
pytest tests/db/ -q

# 应用层（BFF）测试
pytest tests/app/ -q

# Spike 验证（参考用，已冻结）
pytest spikes/ -m p0
```

### 代码质量与契约闸门

```powershell
ruff check . ; ruff format . ; mypy agents/ shared/

python scripts/check_constraint_fk_matrix.py  # 约束子系统 FK 矩阵
python scripts/check_schema_drift.py          # Pydantic ↔ DDL 漂移
python scripts/check_agent_isolation.py       # 跨 Agent import 防火墙
python scripts/gold_eval.py                   # L1 gold 回归
```

---

## 项目结构

```
proline-cad/
├── agents/                         # 智能体（彼此隔离，仅 MCP 通信）
│   ├── parse_agent/                # CAD → SiteModel（v1.0 GA）
│   ├── constraint_agent/           # 工艺约束 / Z3 / KG（M0 蓝图）
│   ├── layout_agent/               # 布局优化（占位）
│   └── orchestrator/               # 流程编排 + mcp_context 链路
├── app/                            # Dashboard BFF (FastAPI + Pydantic v2)
│   ├── main.py                     # FastAPI 入口 + lifespan
│   ├── routers/                    # auth / dashboard_runs / quarantine /
│   │                               # constraints / health / metrics
│   ├── schemas/                    # 出入口 DTO
│   ├── services/                   # 业务编排
│   └── observability/              # logging / tracing / metrics 中间件
├── web/                            # 前端 dashboard (Next.js 14 + React 18)
│   └── src/                        # ConstraintsPanel / Sites / Runs / Quarantine
├── shared/                         # 跨 Agent 共享层
│   ├── models.py                   # Pydantic 域模型 + 枚举（单一事实来源）
│   ├── db_schemas.py               # SQLAlchemy 2.0 ORM
│   └── mcp_protocol.py             # MCP 消息格式
├── db/                             # 数据库
│   ├── alembic/versions/           # 0001 → 0021（最新：constraint_source_hash）
│   └── docker-compose.db*.yml      # 独立 DB 启动
├── docs/                           # 工程文档
│   ├── constraint_subsystem_data_model.md   # 约束子系统权威蓝图
│   ├── data_architecture.md
│   ├── parse_agent_steps_overview.md
│   ├── ROADMAP_3D_SIM.md
│   └── adr/                        # ADR 决策记录
├── tests/                          # 跨 Agent / DB / app 集成测试
│   ├── db/                         # 不变量 + FK 矩阵 + RLS
│   └── app/                        # BFF API e2e
├── scripts/                        # 闸门脚本 + 开发辅助
│   ├── dev_up.ps1                  # 一键拉起 dev stack
│   ├── check_constraint_fk_matrix.py
│   ├── check_schema_drift.py
│   ├── check_agent_isolation.py
│   └── gold_eval.py
├── spikes/                         # 冻结 PoC（参考用，新代码不要写在此）
├── PRD/                            # 产品需求文档（中文）
├── ExcPlan/                        # 执行计划
├── docker-compose.yml              # 全栈基础设施
├── pyproject.toml                  # Python 依赖（PEP 621）
├── CLAUDE.md                       # AI 助手 / 工程规约
└── CONTRIBUTING.md                 # 贡献指南
```

---

## 当前里程碑状态（截至 2026-05-06）

| 阶段 | Agent / 子系统 | 交付物 | 状态 |
|---|---|---|---|
| M0 | ParseAgent v1.0 | DWG/DXF/IFC/STEP → SiteModel + Asset 分类 + H4/H5 Validator | **GA** |
| M0 | ConstraintAgent | category / review_status / source_hash 蓝图（migration 0019/0020/0021） | **完成** |
| M0 | Dashboard BFF + Web | runs / quarantine / constraints / RBAC | **运行中** |
| M1 | ConstraintAgent | 上传文档接入 ConstraintSource + LLM 抽取 | 进行中 |
| M2 | LayoutAgent | GA + 干涉检测 + Top-K 候选 | 规划中 |
| M3 | SimAgent | DES + 瓶颈诊断 + PINN 代理 | 规划中 |
| M4 | ReportAgent + Orchestrator | 端到端闭环 + ROI + PDF | 规划中 |

详见 [ExcPlan/](ExcPlan/) 与 [docs/ROADMAP_3D_SIM.md](docs/ROADMAP_3D_SIM.md)。

---

## 核心领域概念

| 术语 | 含义 | 出处 |
|---|---|---|
| **SiteModel** | 解析后的底图模型（`site_seed_xxx`），含 Assets / Obstacles / ExclusionZones | [shared/models.py](shared/models.py) |
| **Asset / AssetType** | 参数化设备（22 闭枚举：CncMachine / WeldingRobot / Conveyor / Buffer / ...） | [shared/models.py](shared/models.py) |
| **ConstraintSet** | 约束集合（`cs_xxx`），版本化聚合根（draft / active / archived） | ADR-0005 |
| **ProcessConstraint** | 单条工艺约束；4 维正交：`kind` × `class` × `category` × `authority` | [docs/constraint_subsystem_data_model.md](docs/constraint_subsystem_data_model.md) |
| **ConstraintCategory** | 业务类别（10 闭枚举：SPATIAL / SEQUENCE / TORQUE / SAFETY / ...） | migration 0019 |
| **ConstraintReviewStatus** | 行级审核生命周期（draft / under_review / approved / rejected / superseded） | migration 0020 |
| **ConstraintSource** | 法规 / 标准 / SOP / MBD 元数据 + MinIO blob；`hash_sha256` 去重 | migration 0021 |
| **ConstraintCitation** | 约束 ↔ 源多对多连接（即 `SOURCED_FROM` 边） | ADR-0006 |
| **ProcessGraph** | DAG 物化缓存（per ConstraintSet），`has_cycle=false` 是 publish gate | ADR-0005 |
| **mcp_context_id** | MCP 链路上下文唯一标识；所有产物必须挂回上游 context | [CLAUDE.md](CLAUDE.md) |

完整实体关系与 INV-1..INV-10 不变量见
[docs/constraint_subsystem_data_model.md](docs/constraint_subsystem_data_model.md)。

---

## 文档索引

- **工程规约 / AI 助手指南** → [CLAUDE.md](CLAUDE.md)
- **数据架构** → [docs/data_architecture.md](docs/data_architecture.md)
- **约束子系统权威蓝图** → [docs/constraint_subsystem_data_model.md](docs/constraint_subsystem_data_model.md)
- **ParseAgent 输入生命周期** → [docs/parse_agent_input_lifecycle.md](docs/parse_agent_input_lifecycle.md)
- **3D / 仿真路线图** → [docs/ROADMAP_3D_SIM.md](docs/ROADMAP_3D_SIM.md)
- **决策记录（ADR）** → [docs/adr/](docs/adr/)
- **执行计划** → [ExcPlan/](ExcPlan/)
- **PRD（中文）** → [PRD/](PRD/)
- **数据模型与接口规范** → [PRD/PRD全局附录_数据模型与接口规范.md](PRD/PRD全局附录_数据模型与接口规范.md)
- **贡献指南** → [CONTRIBUTING.md](CONTRIBUTING.md)

---

## 语言与约定

- **代码标识符 / API 名称 / commit message**：英文
- **PRD / 文档注释 / 测试描述 / UI 文案**：中文（zh-CN）
- **UI**：无 emoji；冷白 + 浅灰 + `#2563eb` / `#14b8a6` 点缀
- **依赖管理**：`pyproject.toml` 单一事实来源，禁止手编 `requirements.txt`
- **迁移**：Alembic 单向；任何已合并 revision 不可修改

---

## License

[Apache License 2.0](LICENSE)
