# ProLine CAD — 航空工艺产线 AI 规划平台

> AI-driven aerospace production line lifecycle planning platform.  
> 三 Agent 闭环系统：CAD 解析 → 约束检查 → 布局优化，实现 **8 分钟端到端交付、0 返工、99.8% 约束遵循度**。

---

## 系统架构

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  CAD 文件    │────▶│  Agent1          │────▶│  Agent2          │
│  DWG/IFC/   │     │  ParseAgent      │     │  ConstraintAgent │
│  STEP/DXF   │     │  本体识别/语义抽取 │     │  Z3 约束验证     │
└─────────────┘     └──────────────────┘     └──────────────────┘
                                                      │
                    ┌──────────────────┐               │
                    │  Orchestrator    │◀──────────────┘
                    │  MCP 流程编排    │
                    │  mcp_context链路  │───────┐
                    └──────────────────┘       │
                                               ▼
                    ┌──────────────────┐     ┌──────────────────┐
                    │  AuditStore      │◀────│  Agent3          │
                    │  审计/追溯/PDF    │     │  LayoutAgent     │
                    └──────────────────┘     │  GA 布局优化     │
                                             └──────────────────┘
```

**核心原则**：MCP-First（Model Context Protocol）— 所有 Agent 间通过 MCP 通信，全链路 `mcp_context_id` 追溯。

---

## 快速开始

### 环境要求

- Python >= 3.11
- Docker & Docker Compose（基础设施服务）
- Git

### 安装

```bash
# 克隆仓库
git clone https://github.com/your-org/proline-cad.git
cd proline-cad

# 创建并激活虚拟环境
python -m venv .venv
# Windows CMD:
.venv\Scripts\activate
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# 安装完整依赖（所有 Agent + 开发工具）
pip install -e ".[all]"

# 或按需安装单个 Agent
pip install -e ".[parse]"       # Agent1: ParseAgent
pip install -e ".[constraint]"  # Agent2: ConstraintAgent
pip install -e ".[layout]"      # Agent3: LayoutAgent
pip install -e ".[dev]"         # 开发工具
```

### 启动基础设施

```bash
# 启动 PostgreSQL、MinIO、Kafka 等
docker-compose up -d

# 仅启动核心服务（轻量开发）
docker-compose up -d postgres minio
```

### 运行测试

```bash
# Spike 技术验证测试（TDD 阶段）
cd spikes && python -m pytest -m p0      # P0 关键测试
cd spikes && python -m pytest            # 全量测试
cd spikes && python -m pytest -m spike3  # 单个 Spike

# Agent 测试（实现阶段）
pytest agents/                           # 所有 Agent 测试
pytest agents/parse_agent/tests/         # 单个 Agent
```

### 代码质量

```bash
ruff check .          # Lint
ruff format .         # Format
mypy agents/ shared/  # 类型检查
```

---

## 项目结构

```
proline-cad/
├── agents/                    # 三个 Agent 服务 + Orchestrator
│   ├── parse_agent/           # Agent1: CAD 解析 → SiteModel
│   ├── constraint_agent/      # Agent2: Z3 约束验证
│   ├── layout_agent/          # Agent3: GA 布局优化
│   └── orchestrator/          # 流程编排 + mcp_context 链路
├── shared/                    # 共享库（数据模型、MCP 协议、审计）
│   ├── models.py              # Pydantic 域模型
│   ├── mcp_protocol.py        # MCP 消息格式
│   ├── audit_store.py         # AuditStore 接口
│   └── schemas/               # JSON Schema 定义
├── spikes/                    # 10 个独立技术验证实验（TDD）
│   ├── spike_01_dwg_parse/    # DWG/DXF 解析
│   ├── spike_02_mcp_e2e/      # MCP 端到端通信
│   ├── spike_03_collision/    # 碰撞检测 (R-Tree)
│   ├── spike_04_des_sim/      # 离散事件仿真 (SimPy)
│   ├── spike_05_llm_extract/  # LLM 约束提取
│   ├── spike_06_temporal/     # Temporal 工作流
│   ├── spike_07_3d_render/    # Three.js 3D 渲染
│   ├── spike_08_pinn/         # PINN 代理模型
│   ├── spike_09_rag/          # RAG 知识检索
│   └── spike_10_report/       # 报告生成
├── db/                        # 数据库 DDL 与迁移
├── PRD/                       # 产品需求文档（中文）
├── ExcPlan/                   # 执行计划文档
├── docker-compose.yml         # 开发环境基础设施
├── pyproject.toml             # Python 依赖管理 (PEP 621)
├── requirements.txt           # Pinned 依赖
├── CLAUDE.md                  # AI 助手项目指南
├── CONTRIBUTING.md            # 贡献指南
└── LICENSE                    # Apache-2.0
```

---

## 执行路线图（10-12 周）

| 阶段 | 时间 | 交付物 | 验收准则 |
|------|------|--------|---------|
| **M0** 项目准备 | Week 1 | CAD 样本 5+，约束库 CS-001 | 15+ 约束条目，infra ready |
| **M1** 基础设施 | Week 2-3 | MCP Toolbelt + AuditStore | PG/Milvus/Kafka 运行 |
| **M2** ParseAgent | Week 4-5 | SiteModel + Ontology Graph | confidence≥0.90, p95≤5s |
| **M3** ConstraintAgent | Week 6-7 | Z3 验证 + 冲突诊断 | 检出率 100%, FP<0.2% |
| **M4** LayoutAgent | Week 8-9 | Top3 方案 + GA 优化 | best score≥0.80 |
| **M5** 编排+LLM+UI | Week 10 | 端到端闭环 | <10min, 链路完整 |
| **M6** 测试+部署 | Week 11-12 | CI/CD + Staging | UAT 通过 |

---

## 核心领域概念

| 术语 | 含义 |
|------|------|
| **SiteModel** | 解析后的底图模型（site_guid: SM-xxx）— 包含 Assets、Obstacles、ExclusionZones |
| **Asset** | 参数化设备（MDI、Footprint、Ports） |
| **ConstraintSet** | 约束集合（CS-xxx），含硬约束（MUST）和软约束（SHOULD） |
| **mcp_context** | MCP 链路上下文，全链路追溯唯一标识符 |
| **CP-A Token** | 信任门令牌 — SiteModel 必须通过所有前置条件才能进入布局阶段 |

---

## 文档索引

- **架构与哲学** → [CLAUDE.md](CLAUDE.md)
- **执行计划** → [ExcPlan/](ExcPlan/)
- **PRD 文档（中文）** → [PRD/](PRD/)
- **技术验证计划** → [PRD/step5.2-关键技术验证计划.md](PRD/step5.2-关键技术验证计划.md)
- **数据模型规范** → [PRD/PRD全局附录_数据模型与接口规范.md](PRD/PRD全局附录_数据模型与接口规范.md)
- **贡献指南** → [CONTRIBUTING.md](CONTRIBUTING.md)

---

## 语言约定

- **代码标识符、API 名称**：英文
- **文档注释、测试描述、PRD**：中文
- **UI**：无 emoji，简洁、留白、淡色调

---

## License

[Apache License 2.0](LICENSE)
