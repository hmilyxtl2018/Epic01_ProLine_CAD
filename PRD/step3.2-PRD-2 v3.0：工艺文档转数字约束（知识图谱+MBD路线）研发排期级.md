

```
╔══════════════════════════════════════════════════════════════════╗
║         产线+工艺 AI+CAD 系统                                     ║
║         PRD-2 v3.0：工艺文档转数字约束                            ║
║         知识图谱 + MBD 路线 · 研发排期级完整版                     ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## 文档信息表

| 字段 | 内容 |
|------|------|
| **文档编号** | PRD-2-v3.0 |
| **模块代号** | S2_工艺约束 |
| **基于版本** | PRD-2 v2.0 + Palantir工程哲学修正策略报告（已评审通过） |
| **日期** | 2026-04-09 |
| **状态** | ✅ 可进入研发排期 |
| **适用场景** | 航空总装脉动线 / 飞机部件装配 / 航空发动机总装 / 卫星柔性总装 |
| **输入依赖** | PRD-1 SiteModel（需携带有效 CP-A Token） |
| **输出产物** | ConstraintSet v3.0（JSON） + 约束知识图谱（Neo4j）+ CP-B Token |
| **Trust Gate 入口** | 须持有 CP-A Token（SiteModel 锁版）方可触发本模块 |
| **Trust Gate 出口** | 本模块通过后签发 CP-B Token，解锁 PRD-3 布局优化模块 |
| **Ontology 版本** | AeroOntology v1.0（见 §2） |
| **作者** | 产品团队 |
| **评审人** | 工艺工程师代表 · 架构师 · 项目经理 |

---

## 版本历史

| 版本 | 日期 | 变更说明 | 变更人 |
|------|------|---------|--------|
| v1.0 | 2026-04-08 | 初始结构 | — |
| v2.0 | 2026-04-09 | 新增MBD路线、知识图谱架构、三层解析架构、航空约束类型库 | — |
| **v3.0** | **2026-04-09** | **🆕 补入 Ontology 层（§2）；检查点升级为 Token-Based Trust Gate（§5）；为全部 KR 配套 Metric Definition Card（§3）；所有 US 补全 API 规格+错误码+审计字段（§7）；新增权限矩阵（§6）；US-2-05 默会知识拆分优先级（§7）；新增 Action Catalog（§17）；新增 Sprint 规划表（§18）；ConstraintSet 数据模型升级为 v3.0（§8）** | 产品团队 |

---

## 如何阅读本文档

- **研发负责人**：重点阅读 §5（Trust Gate）、§7（US + API 规格）、§8（数据模型）、§17（Action Catalog）、§18（Sprint 规划）
- **后端工程师**：§7 API 规格、§8 数据模型、§11 NFR、§12 业务规则、§15 序列图、§16 数据流图
- **前端工程师**：§7 用户故事 AC、§14 原型设计、§6 权限矩阵
- **工艺工程师（客户代表）**：§1 问题陈述、§3 成功指标、§4 目标用户、§9 航空约束类型库
- **QA 工程师**：§7 全部 AC、§11 NFR、§12 异常处理、§3 Metric Definition Cards
- **🆕 标注** = v3.0 相对 v2.0 的新增或重大修改内容

---

## §1 需求背景与问题陈述

### 1.1 问题现状

航空工艺文档转数字约束面临五重特殊挑战，每一重都超出通用 LLM 或 CAD 工具的处理能力边界：

| # | 挑战 | 具体表现 | 现有方案的失效点 |
|---|------|---------|----------------|
| C1 | **主流载体是 MBD 三维模型** | 成飞/商飞/西飞的工艺定义 80% 以上在 CATIA PMI 标注中，而非 PDF | 纯 LLM 文字解析路线完全无效 |
| C2 | **约束六维叠加** | 几何/公差/序列/力矩/安全/环境约束同时存在，相互耦合 | 单一约束模型无法表达复合约束 |
| C3 | **万条级规模冲突** | 单型号约束数万条，Z3 暴力枚举不可行 | 需要分层冲突检测策略 |
| C4 | **默会知识未文档化** | 老工程师 30 年经验仅在口头传授中存在 | 无结构化录入机制，知识随人员流失 |
| C5 | **涉密隔离要求** | 军机工艺文档不得上传任何外部 API 服务 | SaaS LLM 方案不可用 |

### 1.2 v2.0 → v3.0 的结构性问题修正

基于 Palantir 工程哲学评审（已通过），v3.0 重点修复以下三项：

1. **Ontology 缺失**：v2.0 中 `master_device_id` 出现 7 次但实体从未被规范定义 → v3.0 补入 §2 Ontology 层
2. **检查点是人工门禁而非信任传递**：v2.0 检查点为 checkbox 清单 → v3.0 升级为 Token-Based Trust Gate（§5）
3. **AI 洞察停在 Data 层，未到 Action 层**：`auto_suspend_on_violation: true` 仅是字段声明，缺乏执行规格 → v3.0 补入 Action Catalog（§17）

---

## §2 🆕 Ontology 层定义（AeroOntology v1.0）

> **设计原则（Palantir P1）**：所有实体必须先在 Ontology 中被定义，再被数据模型使用。本章是整个 PRD-2 的语义地基，所有后续章节的字段命名均以此为准。

### 2.1 Object Types（对象类型）

```
┌─────────────────────────────────────────────────────────────────┐
│                    AeroOntology v1.0                            │
│                                                                 │
│  ┌──────────┐    PLACED_IN    ┌──────────┐                      │
│  │  Asset   │──────────────▶ │ Station  │                      │
│  │  工装    │                │  站位    │                      │
│  └──────────┘                └──────────┘                      │
│       │                           │                            │
│  GOVERNED_BY                 CONTAINS                          │
│       │                           │                            │
│       ▼                           ▼                            │
│  ┌────────────┐            ┌──────────────┐                    │
│  │ Constraint │            │  Operation   │                    │
│  │   约束     │◀──APPLIES──│   工序       │                    │
│  └────────────┘            └──────────────┘                    │
│       │                           │                            │
│  SOURCED_FROM              DOCUMENTED_IN                       │
│       │                           │                            │
│       ▼                           ▼                            │
│  ┌──────────┐              ┌──────────────┐                    │
│  │ Document │              │ ProcessGraph │                    │
│  │ 工艺文档 │              │  工序图谱    │                    │
│  └──────────┘              └──────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Object Type 规范属性表

#### Asset（工装）— 枢纽实体

| 属性名 | 类型 | 不可空 | 不可变 | 说明 |
|--------|------|--------|--------|------|
| `asset_guid` | UUID v4 | ✅ | ✅ | 系统内唯一标识，生成后不可修改 |
| `master_device_id` | String | ✅ | ✅ | 企业主数据唯一键，跨系统锚点 |
| `lifecycle_state` | Enum | ✅ | ❌ | `PROPOSED` \| `ACTIVE` \| `RETIRED` |
| `category` | Enum | ✅ | ❌ | 见下方 Category 枚举 |
| `authority_source` | Enum | ✅ | ❌ | `PLM` \| `ERP` \| `MANUAL`，标识 master_device_id 来源权威方 |

**Asset.category 枚举（完整）**：
`MAIN_JIGS` \| `SUB_JIGS` \| `CONVEYOR` \| `INSPECTION` \| `STORAGE` \| `UTILITY` \| `AGV` \| `CRANE` \| `TOOLING`

#### Constraint（约束）— 关系实体

| 属性名 | 类型 | 不可空 | 说明 |
|--------|------|--------|------|
| `constraint_id` | UUID v4 | ✅ | 系统生成，不可变 |
| `type` | Enum | ✅ | `HARD` \| `SOFT` \| `PREFERENCE` |
| `authority_level` | Enum | ✅ | **🆕** `PMI > SOP > MBOM_IMPORT > EXPERT_INPUT`，冲突仲裁依据 |
| `confidence` | Float [0,1] | ✅ | 解析置信度，PMI引擎来源默认1.0 |
| `lifecycle_state` | Enum | ✅ | `DRAFT` \| `UNDER_REVIEW` \| `APPROVED` \| `SUPERSEDED` \| `REJECTED` |
| `sourced_from_doc_id` | UUID | ✅ | 关联 Document 对象 |
| `verified_by_user_id` | UUID | ❌ | 人工确认后填充 |
| `verified_at` | ISO8601 | ❌ | 人工确认时间戳 |

#### Document（工艺文档）— 溯源实体

| 属性名 | 类型 | 不可空 | 说明 |
|--------|------|--------|------|
| `doc_id` | UUID v4 | ✅ | |
| `doc_type` | Enum | ✅ | `MBD_CATIA` \| `MBD_NX` \| `PDF_SOP` \| `WORD_SOP` \| `EXCEL_SHEET` \| `MBOM_TC` \| `MBOM_ENOVIA` \| `EXPERT_INPUT` |
| `classification_level` | Enum | ✅ | **🆕** `PUBLIC` \| `INTERNAL` \| `CONFIDENTIAL` \| `SECRET`，驱动 LLM 路由决策 |
| `hash_sha256` | String | ✅ | 文件内容指纹，防篡改验证 |
| `parse_status` | Enum | ✅ | `PENDING` \| `PARSING` \| `COMPLETED` \| `FAILED` \| `PARTIAL` |

#### Station（站位）— 空间实体

| 属性名 | 类型 | 不可空 | 说明 |
|--------|------|--------|------|
| `station_id` | UUID v4 | ✅ | |
| `site_model_ref` | UUID | ✅ | 关联 SiteModel，携带版本号 |
| `station_type` | Enum | ✅ | `ASSEMBLY` \| `INSPECTION` \| `STORAGE` \| `TRANSIT` |
| `boundary_wkt` | WKT Polygon | ✅ | 从 PRD-1 SiteModel 继承 |

#### Operation（工序）— 时间实体

| 属性名 | 类型 | 不可空 | 说明 |
|--------|------|--------|------|
| `operation_id` | UUID v4 | ✅ | |
| `op_type` | Enum | ✅ | `DRILLING` \| `RIVETING` \| `SEALING` \| `TORQUING` \| `INSPECTION` \| `FINAL_CHECK` |
| `cycle_time_min` | Float | ✅ | 标准工时 |
| `skill_level` | Enum | ✅ | `L1` \| `L2` \| `L3` \| `L4`（航空技能等级） |
| `milestone_flag` | Boolean | ✅ | 是否为里程碑节点，影响仿真节拍计算 |

### 2.3 Link Types（关系类型）

| 关系名 | 方向 | 基数 | 说明 |
|--------|------|------|------|
| `PLACED_IN` | Asset → Station | N:1 | 工装部署于站位，随布局版本变化 |
| `GOVERNED_BY` | Asset → Constraint | N:M | 工装受约束管辖 |
| `APPLIES_TO` | Constraint → Operation | N:M | 约束作用于工序 |
| `SOURCED_FROM` | Constraint → Document | N:1 | 约束溯源至唯一文档（多文档用多条约束表达） |
| `DOCUMENTED_IN` | Operation → ProcessGraph | N:1 | 工序归属于工序图谱 |
| `USES` | Operation → Asset | N:M | 工序使用工装 |
| `CONFLICTS_WITH` | Constraint ↔ Constraint | N:M | **🆕** 冲突关系，由 Z3 引擎写入 |
| `SUPERSEDES` | Constraint → Constraint | 1:1 | **🆕** 仲裁后高优先级约束取代低优先级约束 |

---

## §3 业务目标与成功指标（OKR + Metric Definition Cards）

### 3.1 Objective

> 实现航空工艺文档（MBD 模型 + 文字 SOP）到可执行数字约束知识图谱的自动化转换，形成**越用越聪明的专属知识资产**。

### 3.2 Key Results + 🆕 Metric Definition Cards

---

#### KR0 · 业务层 · 工程师确认时间

| 字段 | 内容 |
|------|------|
| **指标描述** | 工艺工程师完成约束集审核确认时间：2天 → 2小时 |
| **测量条件** | 标准航空装配工序 100 页 SOP，约束数 ≤ 500 条 |
| **分子** | 工艺工程师从登录系统到点击「锁版确认」的总耗时（分钟） |
| **分母** | 固定测试场景（同一份 SOP，重复测量取中位数） |
| **Ground Truth 来源** | 由 3 名工艺工程师各独立完成 3 次，取平均值 |
| **测量触发** | 每个大版本发布后，使用标准测试 SOP 回归测试 |
| **阈值行为** | 超过 4 小时 → 产品告警；超过 8 小时 → 阻断发版 |
| **监控方式** | 系统内 Session 时长日志自动统计，PM Dashboard 可查 |

---

#### KR1 · 系统层 · 解析速度

| 字段 | 内容 |
|------|------|
| **指标描述** | 文字 SOP ≤ 5 分钟（< 100 页）；含 MBD 解析 ≤ 30 分钟 |
| **分子** | 系统接收文件到输出 ConstraintSet JSON 的服务端耗时（秒） |
| **分母** | 不适用（绝对时间指标） |
| **Ground Truth 来源** | 服务端时间戳日志，不依赖客户端网络延迟 |
| **测量触发** | 每次 CI/CD 构建后自动运行性能回归套件 |
| **阈值行为** | SOP > 8 分钟 → P1 Bug；MBD > 45 分钟 → P1 Bug |
| **监控方式** | Prometheus + Grafana 实时面板，P99 延迟告警 |

---

#### KR2 · 系统层 · 冲突检测率

| 字段 | 内容 |
|------|------|
| **指标描述** | 逻辑类约束冲突检测率 ≥ 95% |
| **分子** | 系统自动检测到的冲突对数量 |
| **分母** | 测试集中由专家标注的全部冲突对数量（Ground Truth） |
| **Ground Truth 来源** | 由 2 名资深工艺工程师对 30 份真实 SOP 进行人工冲突标注，存入版本化测试集库（`/test-datasets/conflict-gt-v1.0/`） |
| **测量触发** | 每次 Z3 引擎版本升级后回归；新增约束类型后回归 |
| **阈值行为** | 低于 90% → 告警；低于 85% → 阻断 CP-B Token 签发 |
| **监控方式** | 每周自动运行测试集，结果写入 QA Dashboard |
| **特别说明** | 公差/力矩类约束不计入本 KR，由专用 Z3 SMT 模型单独统计 |

---

#### KR3 · 系统层 · 溯源成功率

| 字段 | 内容 |
|------|------|
| **指标描述** | 每条约束可追溯至原文段落/PMI 标注，成功率 ≥ 99% |
| **分子** | 成功携带有效 `source_ref`（文档名+页码+原文片段 OR pmi_3d_ref）的约束数量 |
| **分母** | ConstraintSet 中总约束数量 |
| **Ground Truth 来源** | 系统自动统计，无需人工标注 |
| **测量触发** | 每次解析任务完成后实时计算，写入 ConstraintSet 元数据 |
| **阈值行为** | 低于 98% → 解析任务标记为 `PARTIAL`，禁止进入审核队列 |
| **监控方式** | 每条约束创建时服务端自动校验 `source_ref` 非空 |

---

#### KR4 · 系统层 · 人工审核路由准确率

| 字段 | 内容 |
|------|------|
| **指标描述** | 置信度 < 0.80 的约束 100% 自动进入人工审核队列，不得漏过 |
| **分子** | 实际进入审核队列的低置信度约束数 |
| **分母** | 所有置信度 < 0.80 的约束数 |
| **阈值行为** | 漏过率 > 0 → P0 Bug，立即停止该批次解析 |
| **监控方式** | 队列入口强制校验，服务端拦截器实现，不可绕过 |

---

#### KR5 · 工程层 · 约束类型库覆盖

| 字段 | 内容 |
|------|------|
| **指标描述** | 航空专属约束类型库内置 ≥ 6 类，每类 ≥ 5 条模板规则 |
| **验收方式** | 产品演示 + 测试集覆盖报告，可直接验收 |
| **6 类清单** | SEQUENCE / SPATIAL / TORQUE / SAFETY / ENVIRONMENTAL / REGULATORY |

---

## §4 目标用户

| 角色 | 系统角色标识符 | 背景与上下文 | 核心诉求 | 痛点 |
|------|--------------|------------|---------|------|
| 工艺工程师（主） | `ROLE_PROCESS_ENGINEER` | 5年以上航空装配经验，日常使用 CATIA，MBD 能力参差不齐 | 快速将 MBD/SOP 转为结构化约束，减少重复录入和口头传达 | 目前手工整理一份 SOP 需 2 天，且无法量化自己标注了多少条约束 |
| AI Agent（主） | `ROLE_AI_AGENT` | 系统内部消费者，通过 MCP 协议自动消费 ConstraintSet | 约束格式标准、关系可图查询、冲突已解决 | 约束歧义、缺少 source_ref 时无法自信地驱动布局算法 |
| 布局工程师（次） | `ROLE_LAYOUT_ENGINEER` | 依赖 ConstraintSet 作为布局算法输入 | 约束完整无歧义，冲突已仲裁完毕 | 布局算法因约束不完整而产生无效解 |
| 系统管理员 | `ROLE_SYSTEM_ADMIN` | 负责私有化部署运维 | LLM 路由配置、密级文档隔离审计 | 无法确认哪些文档触发了外部 API 调用 |

---

## §5 🆕 Trust Gate 定义

> **设计原则（Palantir P2）**：信任不是人工确认的承诺，而是系统签发的、携带内容哈希的不可变令牌。下游模块不持有有效令牌则无法启动。

### 5.1 本模块消费的 Token：CP-A Token

PRD-2 的启动**前置条件**：PRD-1 必须已签发有效的 CP-A Token。

```json
// CP-A Token 结构（由 PRD-1 签发，PRD-2 在启动时验证）
{
  "token_id": "CP-A-{uuid}",
  "token_type": "CHECKPOINT_A_SITE_TO_CONSTRAINT",
  "status": "VALID | EXPIRED | REVOKED",
  "authorized_by": "user_id_designer_zhang",
  "authorized_at": "2026-04-09T14:30:00Z",
  "locked_inputs": {
    "site_model_id": "SM-001",
    "site_model_version": "v1.2.3",
    "site_model_hash": "sha256:abc123def456"
  },
  "validity_rules": [
    "当 SM-001 内容哈希变更时，本 Token 自动 EXPIRED",
    "Token 有效期：签发后 30 天"
  ],
  "downstream_modules_unblocked": ["PRD-2_ConstraintExtraction"]
}
```

**系统行为**：
- PRD-2 启动 API（`POST /api/v1/constraint-sessions`）在请求头中**强制**校验 `X-CP-A-Token`
- Token 不存在 → `HTTP 403 ERR_CP_A_TOKEN_MISSING`
- Token 已过期 → `HTTP 403 ERR_CP_A_TOKEN_EXPIRED`，提示重新触发 PRD-1 锁版流程
- Token 对应的 SiteModel 哈希与当前 SiteModel 不符 → `HTTP 409 ERR_SITE_MODEL_CHANGED`

### 5.2 本模块签发的 Token：CP-B Token

PRD-2 全部通过后，系统签发 CP-B Token，解锁 PRD-3 布局优化。

```json
// CP-B Token 结构（由 PRD-2 签发）
{
  "token_id": "CP-B-{uuid}",
  "token_type": "CHECKPOINT_B_CONSTRAINT_TO_LAYOUT",
  "status": "VALID",
  "authorized_by": "user_id_engineer_li",
  "authorized_at": "2026-04-09T16:45:00Z",
  "locked_inputs": {
    "constraint_set_id": "CS-001",
    "constraint_set_version": "v3.0.1",
    "constraint_set_hash": "sha256:xyz789",
    "site_model_ref": {
      "id": "SM-001",
      "version": "v1.2.3",
      "hash": "sha256:abc123def456"
    },
    "cp_a_token_id": "CP-A-{uuid}"
  },
  "gate_checks_passed": {
    "hard_constraint_conflicts_resolved": true,
    "human_review_queue_empty": true,
    "constraint_coverage_rate": 1.0,
    "z3_sat_result": "SATISFIABLE",
    "confidence_below_threshold_count": 0
  },
  "validity_rules": [
    "当 CS-001 内容哈希变更时，本 Token 自动 EXPIRED",
    "当关联 CP-A Token 失效时，本 Token 联动 EXPIRED"
  ],
  "downstream_modules_unblocked": ["PRD-3_LayoutOptimization"]
}
```

### 5.3 CP-B Token 签发条件（Gate Checks）

以下**全部**满足，方可签发 CP-B Token：

| # | 检查项 | 检查方式 | 失败行为 |
|---|--------|---------|---------|
| G1 | 所有 HARD 约束冲突已仲裁完毕（冲突数 = 0） | Z3 引擎自动验证 | 阻断签发，显示未解决冲突清单 |
| G2 | 人工审核队列为空（无待审核约束） | 系统自动统计 | 阻断签发，显示待审核清单 |
| G3 | 约束溯源覆盖率 ≥ 99% | 系统自动统计 | 阻断签发 |
| G4 | Z3 SAT 结果为 SATISFIABLE（约束集整体可满足） | Z3 引擎 | 阻断签发，提示不可满足的约束子集 |
| G5 | 置信度 < 0.50 的约束数量 = 0 | 系统自动统计 | 阻断签发，此类约束须被人工驳回或确认 |
| G6 | 工艺工程师已在审核界面点击「锁版确认」 | 人工授权 + 系统记录 | 无人工授权则不触发 Token 签发 |

---

## §6 🆕 权限矩阵

> **设计原则（最小权限）**：每个角色只能执行其业务职责所必需的操作。权限不可由前端绕过，全部在服务端 JWT Claims 中验证。

### 6.1 功能权限矩阵

| 功能项 | `PROCESS_ENGINEER` | `LAYOUT_ENGINEER` | `AI_AGENT` | `SYSTEM_ADMIN` | `AUDITOR` |
|--------|:------------------:|:-----------------:|:----------:|:--------------:|:---------:|
| 上传工艺文档 | ✅ | ❌ | ❌ | ✅ | ❌ |
| 触发解析任务 | ✅ | ❌ | ✅ API-only | ✅ | ❌ |
| 查看约束列表 | ✅ | ✅ 只读 | ✅ | ✅ | ✅ 只读 |
| 编辑 / 手动创建约束 | ✅ | ❌ | ❌ | ❌ | ❌ |
| 审核队列：确认 / 驳回 | ✅ | ❌ | ❌ | ❌ | ❌ |
| 约束冲突仲裁 | ✅ | ❌ | ❌ | ❌ | ❌ |
| 查看原文溯源 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 执行 CP-B 锁版确认 | ✅ 本人 | ❌ | ❌ | ❌ | ❌ |
| 导出 ConstraintSet JSON | ✅ | ✅ | ✅ | ✅ | ❌ |
| 删除约束 | ✅ 草稿态 | ❌ | ❌ | ✅ 任意态 | ❌ |
| 查看审计日志 | ❌ | ❌ | ❌ | ✅ | ✅ |
| 配置 LLM 路由规则 | ❌ | ❌ | ❌ | ✅ | ❌ |
| 管理约束类型库 | ❌ | ❌ | ❌ | ✅ | ❌ |
| 默会知识录入（P1快捷版） | ✅ | ❌ | ❌ | ❌ | ❌ |

### 6.2 数据密级访问矩阵

> 对应 `Document.classification_level` 字段，不同密级文档的可见范围。

| 文档密级 | `PROCESS_ENGINEER` | `LAYOUT_ENGINEER` | `AI_AGENT` | `SYSTEM_ADMIN` | `AUDITOR` |
|---------|:------------------:|:-----------------:|:----------:|:--------------:|:---------:|
| `PUBLIC` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `INTERNAL` | ✅ | ✅ 约束摘要 | ✅ | ✅ | ✅ |
| `CONFIDENTIAL` | ✅ 项目内 | ❌ | ✅ 本项目 | ✅ | ✅ 只读 |
| `SECRET` | ✅ 持证人员 | ❌ | ❌ 禁止 API 传输 | ✅ 审计模式 | ❌ |

**🆕 密级自动路由规则（服务端强制执行）**：

```
if Document.classification_level IN ['CONFIDENTIAL', 'SECRET']:
    llm_route = PRIVATE_QWEN2_LOCAL        # 强制本地 Qwen2，禁止调用任何外部 API
    network_policy = INTRANET_ONLY         # 网络层拦截出站请求
    audit_log_level = FULL_CONTENT         # 记录完整操作内容
else:
    llm_route = configurable               # 可配置 SaaS / 私有化
```

### 6.3 约束生命周期状态与操作权限

```
DRAFT ──[提交审核]──▶ UNDER_REVIEW ──[确认]──▶ APPROVED ──[被替代]──▶ SUPERSEDED
                              │
                         [驳回]
                              │
                              ▼
                          REJECTED
```

| 状态转换操作 | 可执行角色 | 触发条件 |
|------------|----------|---------|
| `DRAFT → UNDER_REVIEW` | `PROCESS_ENGINEER` | 置信度 < 0.80 时系统自动触发；手动提交 |
| `UNDER_REVIEW → APPROVED` | `PROCESS_ENGINEER` | 人工确认审核通过 |
| `UNDER_REVIEW → REJECTED` | `PROCESS_ENGINEER` | 人工驳回，须填写驳回原因 |
| `APPROVED → SUPERSEDED` | `SYSTEM` 自动 | 仲裁时高优先级约束替代低优先级约束 |

---

## §7 使用场景与用户故事（完整 AC + API 规格）

> **格式说明**：每个 US 包含：场景描述 → 验收标准 AC（可测试） → API 端点规格（Method / Path / Request / Response / 错误码）→ 审计字段

---

### US-2-01：MBD 三维工艺解析（P0）

**As a** 工艺工程师  
**I want** 上传 CATIA/NX 三维工艺模型后，系统自动解析 PMI 标注并生成 ConstraintSet  
**So that** 三维工艺信息自动转为布局算法可消费的数字约束，无需人工转述

#### 验收标准 AC（逐条可测试）

| # | AC | 测试方法 |
|---|-----|---------|
| AC-2-01-1 | 系统接受 `.CATProduct` / `.CATPart` / `.prt` / `.jt` 格式上传，文件大小上限 2GB | 上传测试文件集，验证各格式均返回 `parse_status: PARSING` |
| AC-2-01-2 | PMI 引擎自动提取：尺寸公差（±值）、GD&T 标注、装配序列号、力矩要求（Nm 值），每类至少命中 1 条 | 使用含已知 PMI 标注的标准测试模型，对比输出与 Ground Truth |
| AC-2-01-3 | 每条约束携带 `pmi_3d_ref`（格式：`CATIA://model/{filename}#{pmi_id}`），可在 3D 视图中定位 | 点击约束，3D 视图高亮对应 PMI 标注位置 |
| AC-2-01-4 | PMI 引擎解析的约束 `confidence` 默认赋值 `1.0`，`parse_method` 字段值为 `PMI_ENGINE` | 查询返回约束列表，验证字段值 |
| AC-2-01-5 | 解析任务完成后，系统向提交用户发送站内通知，包含：约束总数、PMI 命中数、待审核数 | 提交解析后等待完成，验证通知内容 |
| AC-2-01-6 | MBD 解析总耗时 ≤ 30 分钟（含 PMI 提取 + LLM 辅助描述生成），P99 延迟监控 | CI 性能回归套件，Prometheus 指标 `parse_duration_seconds` |
| AC-2-01-7 | 若 PMI 解析失败（API 不可用 / 格式异常），系统**不静默失败**，返回降级警告并记录 `parse_status: PARTIAL`，提示用户补充文字 SOP | 断开 3DEXPERIENCE API 连接，上传 MBD 文件，验证降级行为 |
| AC-2-01-8 | `SECRET` 级文档上传时，系统在客户端弹出密级确认对话框，用户确认后方触发上传；服务端拦截对任何外部 API 的调用 | 上传标记 `SECRET` 的文件，抓包验证无外部网络请求 |

#### API 规格

**端点 1：创建解析会话**

```
POST /api/v1/constraint-sessions
Authorization: Bearer {jwt_token}
X-CP-A-Token: {cp_a_token_id}           ← 🆕 Trust Gate 强制字段
Content-Type: multipart/form-data

Request Body:
{
  "project_id":    "proj-uuid",          // 必填
  "doc_type":      "MBD_CATIA",          // 必填，枚举见 §2
  "classification":"CONFIDENTIAL",       // 必填，驱动 LLM 路由
  "file":          <binary>,             // 必填，≤ 2GB
  "doc_version":   "v3.1",              // 可选
  "description":   "某型飞机蒙皮装配"    // 可选
}

Response 202 Accepted:
{
  "session_id":    "sess-uuid",
  "status":        "PENDING",
  "estimated_duration_sec": 1200,
  "llm_route":     "PRIVATE_QWEN2_LOCAL", // 由 classification 自动决定
  "created_at":    "2026-04-09T10:00:00Z"
}
```

**错误码**：

| HTTP | 错误码 | 含义 | 前端处理建议 |
|------|--------|------|------------|
| 400 | `ERR_UNSUPPORTED_FORMAT` | 文件格式不在支持列表中 | 提示支持格式清单 |
| 400 | `ERR_FILE_TOO_LARGE` | 文件超过 2GB | 提示压缩或联系管理员 |
| 400 | `ERR_CLASSIFICATION_MISSING` | 未提供文档密级 | 弹出密级选择对话框 |
| 403 | `ERR_CP_A_TOKEN_MISSING` | 未携带 CP-A Token | 提示返回 PRD-1 完成锁版 |
| 403 | `ERR_CP_A_TOKEN_EXPIRED` | CP-A Token 已过期 | 提示重新触发 PRD-1 锁版流程 |
| 409 | `ERR_SITE_MODEL_CHANGED` | SiteModel 哈希与 Token 记录不符 | 提示 SiteModel 已变更，需重新锁版 |
| 413 | `ERR_PAYLOAD_TOO_LARGE` | 超出系统限制 | — |
| 503 | `ERR_PMI_ENGINE_UNAVAILABLE` | PMI 解析引擎不可用 | 提示降级到文字 SOP 路线 |

**端点 2：查询解析任务状态**

```
GET /api/v1/constraint-sessions/{session_id}
Authorization: Bearer {jwt_token}

Response 200:
{
  "session_id":        "sess-uuid",
  "status":            "PARSING | COMPLETED | FAILED | PARTIAL",
  "progress_pct":      78,
  "constraints_found": 342,
  "pending_review":    12,
  "conflicts_found":   3,
  "parse_duration_sec":890,
  "completed_at":      "2026-04-09T10:15:00Z"   // COMPLETED 后填充
}
```

#### 🆕 审计字段（每次操作自动写入审计日志）

```json
{
  "audit_event":    "MBD_PARSE_SESSION_CREATED",
  "actor_user_id":  "user-uuid",
  "actor_role":     "PROCESS_ENGINEER",
  "session_id":     "sess-uuid",
  "doc_hash":       "sha256:...",
  "doc_classification": "CONFIDENTIAL",
  "cp_a_token_id":  "CP-A-uuid",
  "llm_route_used": "PRIVATE_QWEN2_LOCAL",
  "timestamp":      "2026-04-09T10:00:00Z",
  "ip_address":     "192.168.1.100",
  "result":         "SUCCESS | FAILURE",
  "failure_reason": null
}
```

---

### US-2-02：文字 SOP / 工艺规程解析（P0）

**As a** 工艺工程师  
**I want** 上传 PDF/Word 格式的工艺规程后，系统自动提取约束并生成 ConstraintSet  
**So that** 文字工艺信息结构化，冲突自动高亮，无需人工逐页阅读

#### 验收标准 AC

| # | AC | 测试方法 |
|---|-----|---------|
| AC-2-02-1 | 支持中文/英文 PDF（含扫描件OCR）、Word（.docx）、TXT 格式，单文件 ≤ 500MB | 上传各格式测试文件 |
| AC-2-02-2 | 每条输出约束必须携带完整 `source_ref`：`document`（文件名）+ `page`（页码）+ `section`（章节号，可选）+ `text_snippet`（原文 ≤ 200 字） | 随机抽取 10 条约束，验证 `source_ref` 完整性 |
| AC-2-02-3 | 置信度 < 0.80 的约束自动标记 `requires_human_review: true`，进入审核队列；系统不得将此类约束直接推送至布局算法 | 使用含模糊表述的测试 SOP，验证路由行为 |
| AC-2-02-4 | 同类型约束（相同 `category` + 相同实体对）之间的逻辑冲突，系统自动在约束对象上标记 `conflicts_with: ["C_ID"]` | 准备含已知冲突的测试 SOP，验证冲突标记 |
| AC-2-02-5 | 文字 SOP（< 100 页）解析完成时间 ≤ 5 分钟（P95），> 100 页 ≤ 12 分钟（P95） | CI 性能回归套件 |
| AC-2-02-6 | 扫描件（非文字 PDF）触发 OCR 流程，OCR 完成后再执行 LLM 解析；前端进度条区分 OCR 阶段和 LLM 阶段 | 上传扫描件，验证进度条分阶段显示 |
| AC-2-02-7 | 解析完成后，ConstraintSet 元数据中记录 `source_trace_rate`（溯源率），低于 99% 时解析任务状态标记为 `PARTIAL` | 验证元数据字段 |

#### API 规格

（复用 `POST /api/v1/constraint-sessions`，`doc_type` 传 `PDF_SOP` / `WORD_SOP`）

**约束列表查询**：

```
GET /api/v1/constraint-sessions/{session_id}/constraints
Authorization: Bearer {jwt_token}
Query Params:
  status=   DRAFT|UNDER_REVIEW|APPROVED|REJECTED    // 可选，多值逗号分隔
  type=     HARD|SOFT|PREFERENCE                     // 可选
  category= SEQUENCE|SPATIAL|TORQUE|...              // 可选
  has_conflict= true|false                           // 可选
  page=     1                                        // 默认 1
  page_size=50                                       // 默认 50，最大 200

Response 200:
{
  "total": 1284,
  "page": 1,
  "page_size": 50,
  "items": [
    {
      "constraint_id":  "C001",
      "type":           "HARD",
      "category":       "SPATIAL",
      "authority_level":"PMI",
      "confidence":     0.98,
      "lifecycle_state":"APPROVED",
      "conflicts_with": [],
      "source_ref": {
        "document": "蒙皮装配工艺规程_v3.1.pdf",
        "page": 23,
        "text_snippet": "夹具A与设备B之间最小间距..."
      }
    }
  ]
}
```

**错误码（额外）**：

| HTTP | 错误码 | 含义 |
|------|--------|------|
| 400 | `ERR_OCR_FAILED` | 扫描件 OCR 失败，文件质量过低 |
| 400 | `ERR_LANGUAGE_UNSUPPORTED` | 文档语言不在支持列表（当前支持：中文、英文） |
| 422 | `ERR_SOURCE_TRACE_RATE_TOO_LOW` | 溯源率低于阈值，解析结果不可信 |

---

### US-2-03：知识图谱构建与查询（P0）

**As a** AI Agent  
**I want** 通过知识图谱查询任意两个工装之间的全部约束关系  
**So that** 布局算法精确获取约束集，驱动合法布局生成

#### 验收标准 AC

| # | AC | 测试方法 |
|---|-----|---------|
| AC-2-03-1 | 每条 APPROVED 约束写入 Neo4j 知识图谱后，可通过 `GET /kg/constraints?entity_a=MDI-XXX&entity_b=MDI-YYY` 查询到 | 写入后查询，验证节点和边存在 |
| AC-2-03-2 | 图查询支持**间接约束**：A→B 有约束、B→C 有约束，查询 A 与 C 时系统返回 A-B-C 路径上的全部约束，并标注 `is_indirect: true` | 构造三级约束链，验证间接查询结果 |
| AC-2-03-3 | 路径影响查询：给定工序节点 ID，返回变更后影响的所有下游约束链，响应时间 ≤ 2 秒（图节点 ≤ 10,000） | 压力测试 + 响应时间断言 |
| AC-2-03-4 | 知识图谱写入与 ConstraintSet JSON 保持双向一致：图谱任何写入操作同时更新 ConstraintSet 版本号 | 新增约束后，验证 ConstraintSet `version` 自增 |
| AC-2-03-5 | 知识图谱可视化界面：节点 = 工装（按 `category` 着色），边 = 约束（HARD = 红色实线，SOFT = 橙色虚线），支持拖拽节点创建手动约束 | UI 交互测试 |

#### API 规格

**知识图谱约束查询**：

```
GET /api/v1/kg/constraints
Authorization: Bearer {jwt_token}
Query Params:
  entity_a=       MDI-2024-001          // 必填
  entity_b=       MDI-2024-002          // 可选，不填则返回 entity_a 的全部约束
  include_indirect= true                // 默认 false
  constraint_type=  HARD                // 可选过滤
  depth=            3                   // 间接查询最大深度，默认 2，最大 5

Response 200:
{
  "entity_a": "MDI-2024-001",
  "entity_b": "MDI-2024-002",
  "direct_constraints": [
    {
      "constraint_id":   "C001",
      "type":            "HARD",
      "category":        "SPATIAL",
      "rule_summary":    "间距 ≥ 200mm",
      "authority_level": "PMI",
      "is_indirect":     false
    }
  ],
  "indirect_constraints": [
    {
      "constraint_id":   "C045",
      "path":            ["MDI-2024-001","MDI-2024-003","MDI-2024-002"],
      "is_indirect":     true,
      "via_operations":  ["N015"]
    }
  ],
  "total_count": 3,
  "query_duration_ms": 145
}
```

**手动创建约束（UI 拖拽触发）**：

```
POST /api/v1/constraints
Authorization: Bearer {jwt_token}
Content-Type: application/json

Request Body:
{
  "session_id":       "sess-uuid",
  "type":             "SOFT",
  "category":         "SPATIAL",
  "authority_level":  "EXPERT_INPUT",
  "rule": {
    "relation":  "MIN_DISTANCE",
    "entity_a":  "MDI-2024-001",
    "entity_b":  "MDI-2024-002",
    "value":     300,
    "unit":      "mm"
  },
  "source_ref": {
    "document":     "EXPERT_INPUT",
    "text_snippet": "李工：这两台型架间距建议留够300mm，方便检修"
  },
  "confidence":    1.0,               // 专家直接录入，置信度标记为 1.0
  "input_method":  "MANUAL_UI"        // MANUAL_UI | API | VOICE（P1）
}

Response 201 Created:
{
  "constraint_id":  "C-new-uuid",
  "lifecycle_state":"APPROVED",       // 专家手动录入，直接 APPROVED，无需审核队列
  "kg_node_created": true,
  "created_at":     "2026-04-09T11:00:00Z"
}
```

**错误码**：

| HTTP | 错误码 | 含义 |
|------|--------|------|
| 400 | `ERR_ENTITY_NOT_FOUND` | entity_a 或 entity_b 不在 Ontology 中 |
| 400 | `ERR_SELF_REFERENCE` | entity_a 与 entity_b 为同一工装 |
| 409 | `ERR_DUPLICATE_CONSTRAINT` | 相同实体对、相同 category、相同 relation 已存在约束 |
| 409 | `ERR_CONSTRAINT_CONFLICT_DETECTED` | 新建约束与现有约束冲突，返回冲突约束 ID 列表 |

---

### US-2-04：工艺 MBOM 导入（P1）

**As a** 工艺工程师  
**I want** 从 Teamcenter / ENOVIA 导入工艺 MBOM  
**So that** 工序关系直接映射为 ProcessGraph，无需手动重建装配逻辑

#### 验收标准 AC

| # | AC | 测试方法 |
|---|-----|---------|
| AC-2-04-1 | 支持 Teamcenter REST API（TC 12.x+）和 ENOVIA REST API（R2022x+）两种接入方式 | 集成测试（沙箱环境） |
| AC-2-04-2 | MBOM 中每个工序节点映射为 ProcessGraph 中的 Operation 节点，携带：`operation_id`（来自 MBOM）、`cycle_time_min`、`skill_level`、`op_type` | 导入后查询 ProcessGraph，逐字段验证 |
| AC-2-04-3 | MBOM 工序关系（先序/并行/条件）映射为 ProcessGraph 边，类型对应：`SEQUENTIAL` / `PARALLEL` / `CONDITIONAL` | 导入含并行工序的 MBOM，验证图结构 |
| AC-2-04-4 | **MBOM 与 SOP 约束冲突时**，`authority_level: MBOM_IMPORT > SOP`，系统自动标记低优先级约束为 `SUPERSEDED`，并在前端高亮差异供工程师确认 | 准备已知冲突的测试数据集 |
| AC-2-04-5 | MBOM 导入完成后，ProcessGraph 版本号更新，下游 PRD-3 布局模块的相关缓存失效 | 验证缓存失效通知 |

#### API 规格

```
POST /api/v1/process-graphs/import
Authorization: Bearer {jwt_token}
Content-Type: application/json

Request Body:
{
  "session_id":    "sess-uuid",
  "source_system": "TEAMCENTER",      // TEAMCENTER | ENOVIA
  "mbom_id":       "MBOM-2024-001",  // 源系统中的 MBOM ID
  "api_endpoint":  "https://tc.corp.internal/api",
  "credential_ref":"vault://tc-creds" // 凭据引用，不允许明文传输
}

Response 202 Accepted:
{
  "import_job_id":   "job-uuid",
  "status":          "PENDING",
  "estimated_sec":   120
}
```

---

### US-2-05A：默会知识录入 — P1 快捷版（结构化模板）

> 🆕 **v3.0 拆分说明**：原 US-2-05（P2）拆分为 P1 快捷版（本条）和 P2 完整版（US-2-05B），P1 版本复用现有约束录入界面，开发成本极低，可在 Phase 1 启动知识飞轮。

**As a** 工艺工程师  
**I want** 通过标准模板填空录入老工程师的经验规则  
**So that** 5 分钟内完成一条经验约束的结构化录入，无需自由文本理解

#### 验收标准 AC

| # | AC | 测试方法 |
|---|-----|---------|
| AC-2-05A-1 | 系统提供约束快捷模板：**间距类**（实体A、实体B、最小距离、单位）/ **序列类**（工序A先于工序B）/ **安全类**（作业条件描述 + 安全等级）三种，填空即完成录入 | UI 测试，从模板到提交全流程 ≤ 5 分钟 |
| AC-2-05A-2 | 通过模板录入的约束：`confidence: 1.0`（专家直接确认）、`authority_level: EXPERT_INPUT`、`lifecycle_state: APPROVED`，**不进入审核队列** | 验证约束字段值 |
| AC-2-05A-3 | 支持 Excel 批量导入：系统提供标准 `.xlsx` 模板（含三类约束的列定义和示例行），上传后解析并写入知识图谱 | 下载模板，填写 10 条，上传，验证全部写入 |
| AC-2-05A-4 | 批量导入中存在格式错误的行，系统逐行报告错误（行号 + 错误原因），其余合法行正常写入 | 上传含 1 行错误的 Excel |
| AC-2-05A-5 | 每条手动录入约束在知识图谱中生成节点时，同时记录录入者 `user_id` 和录入时间戳，不可篡改 | 查询图谱节点属性 |

#### API 规格

```
POST /api/v1/constraints/batch-import
Authorization: Bearer {jwt_token}
Content-Type: multipart/form-data

Request:
{
  "session_id": "sess-uuid",
  "file":       <xlsx binary>,          // 使用系统标准模板
  "input_method": "EXCEL_IMPORT"
}

Response 200:
{
  "total_rows":    10,
  "success_count": 9,
  "failure_count": 1,
  "failures": [
    {
      "row": 7,
      "error_code": "ERR_ENTITY_NOT_FOUND",
      "detail": "entity_a 'MDI-9999' 不存在于当前项目"
    }
  ],
  "created_constraint_ids": ["C-uuid-1", "C-uuid-2", ...]
}
```

**错误码**：

| HTTP | 错误码 | 含义 |
|------|--------|------|
| 400 | `ERR_TEMPLATE_VERSION_MISMATCH` | Excel 模板版本与系统



---

### US-2-05B：默会知识录入 — P2 完整版（语音 / 自由文本）

> **v3.0 说明**：P2 完整版，复用三层解析架构基础设施，LLM 解析后进入人工审核队列，与 US-2-02 共享同一后端管道。

**As a** 工艺工程师  
**I want** 通过语音录入或自由文本描述老工程师的经验规则  
**So that** 口头传授的隐性知识被结构化为软约束，纳入知识图谱管理，随型号积累

#### 验收标准 AC

| # | AC | 测试方法 |
|---|-----|---------|
| AC-2-05B-1 | 支持中文语音录入（≤ 5 分钟音频），系统自动完成 ASR 转写，转写文本显示供用户确认后再触发 LLM 解析 | 录入标准测试语音片段，验证 ASR 转写准确率 ≥ 90% |
| AC-2-05B-2 | 语音 / 自由文本录入的约束，`parse_method` 标记为 `EXPERT_INPUT`，`authority_level` 为 `EXPERT_INPUT`（优先级最低），`confidence` 由 LLM 打分 | 查询约束字段值 |
| AC-2-05B-3 | LLM 解析完成后，生成的候选约束**全部**进入人工审核队列（不论置信度高低），工艺工程师确认后方可进入 APPROVED 状态 | 录入任意语音，验证 100% 进入审核队列 |
| AC-2-05B-4 | 工程师确认或驳回的结果自动写入微调训练数据集（`/training-data/expert-feedback/`），数据集版本化管理 | 确认后查询训练数据集，验证新增记录 |
| AC-2-05B-5 | ASR 服务在私有化部署环境下必须使用本地 ASR 引擎（Paraformer 或同等国产模型），禁止调用外部 API | 私有化环境抓包验证无外部 ASR 请求 |

#### API 规格

```
POST /api/v1/constraints/expert-input
Authorization: Bearer {jwt_token}
Content-Type: multipart/form-data

Request:
{
  "session_id":    "sess-uuid",
  "input_type":    "VOICE | TEXT",           // 必填
  "audio_file":    <binary>,                 // input_type=VOICE 时必填，≤ 300MB
  "text_content":  "这两台型架间距建议...",    // input_type=TEXT 时必填
  "expert_name":   "李工",                   // 可选，记录知识来源人
  "context_note":  "来自 2023 年试飞总结会"   // 可选
}

Response 202 Accepted:
{
  "job_id":          "job-uuid",
  "status":          "ASR_PROCESSING | LLM_PARSING | PENDING_REVIEW",
  "transcribed_text": "...",                 // ASR 完成后填充
  "candidate_constraints": [],              // LLM 解析完成后填充
  "review_queue_ids": []                    // 全部进入审核队列
}
```

**错误码**：

| HTTP | 错误码 | 含义 | 前端处理建议 |
|------|--------|------|------------|
| 400 | `ERR_AUDIO_TOO_LONG` | 音频超过 5 分钟 | 提示拆分录入 |
| 400 | `ERR_AUDIO_QUALITY_LOW` | ASR 无法识别（背景噪音过大） | 提示重新录制或改用文字输入 |
| 503 | `ERR_ASR_ENGINE_UNAVAILABLE` | 本地 ASR 引擎不可用 | 提示降级为文字输入 |

#### 🆕 审计字段

```json
{
  "audit_event":    "EXPERT_INPUT_SUBMITTED",
  "actor_user_id":  "user-uuid",
  "input_type":     "VOICE",
  "expert_name":    "李工",
  "audio_duration_sec": 187,
  "asr_engine":     "PARAFORMER_LOCAL",
  "candidate_count": 3,
  "review_queue_ids": ["RQ-001","RQ-002","RQ-003"],
  "timestamp":      "2026-04-09T14:20:00Z"
}
```

---

### US-2-06：🆕 约束冲突仲裁（P0）

> **v3.0 新增**：v2.0 仅描述了冲突检测，未定义仲裁流程。本 US 补全从「冲突发现」到「仲裁完成→约束替代关系写入图谱」的完整闭环。

**As a** 工艺工程师  
**I want** 对 Z3 引擎检测出的约束冲突，按照 authority_level 优先级规则进行半自动仲裁  
**So that** 所有 HARD 约束冲突在 CP-B Token 签发前被解决，布局算法收到无歧义的约束集

#### 验收标准 AC

| # | AC | 测试方法 |
|---|-----|---------|
| AC-2-06-1 | Z3 引擎完成检测后，系统按 `authority_level` 自动推荐仲裁方向：`PMI > SOP > MBOM_IMPORT > EXPERT_INPUT`；页面高亮推荐方向，工程师可一键采纳或手动覆盖 | 准备含已知冲突对的测试集，验证推荐方向正确率 |
| AC-2-06-2 | 仲裁采纳后，系统自动执行：① 高优先级约束状态保持 `APPROVED`；② 低优先级约束状态变更为 `SUPERSEDED`；③ 在知识图谱中写入 `SUPERSEDES` 边 | 仲裁后查询图谱，验证 `SUPERSEDES` 边存在 |
| AC-2-06-3 | 仲裁时工程师必须填写仲裁理由（`arbitration_reason`，≥ 10 字），理由写入审计日志，不可为空 | 不填理由点击确认，验证系统阻断 |
| AC-2-06-4 | 仲裁完成后，受影响的下游模块（PRD-3 布局优化）缓存自动失效，系统推送「约束集已变更，布局方案需重新验证」通知 | 仲裁完成后，验证 PRD-3 缓存失效通知 |
| AC-2-06-5 | CP-B Token 签发检查时，系统校验 `conflicts_count == 0`；若仍有未仲裁冲突，阻断 Token 签发并列出清单 | 保留 1 条未仲裁冲突，尝试签发 CP-B，验证被阻断 |

#### API 规格

**查询冲突清单**：

```
GET /api/v1/constraint-sessions/{session_id}/conflicts
Authorization: Bearer {jwt_token}
Query Params:
  status= UNRESOLVED | RESOLVED | ALL     // 默认 UNRESOLVED

Response 200:
{
  "total_conflicts": 5,
  "unresolved_count": 2,
  "items": [
    {
      "conflict_id":     "CONF-001",
      "constraint_a": {
        "id":              "C023",
        "rule_summary":    "F-007 与 F-008 间距 ≥ 200mm",
        "authority_level": "SOP",
        "source_doc":      "蒙皮装配工艺规程_v3.0.pdf p.18"
      },
      "constraint_b": {
        "id":              "C045",
        "rule_summary":    "F-007 与 F-008 间距 ≥ 500mm",
        "authority_level": "MBOM_IMPORT",
        "source_doc":      "MBOM-2024-001 工序 N015"
      },
      "conflict_type":   "VALUE_CONTRADICTION",
      "recommended_winner": "C045",
      "recommended_reason": "MBOM_IMPORT > SOP，建议采用 C045（500mm）",
      "status":          "UNRESOLVED"
    }
  ]
}
```

**提交仲裁决定**：

```
POST /api/v1/conflicts/{conflict_id}/arbitrate
Authorization: Bearer {jwt_token}
Content-Type: application/json

Request Body:
{
  "winner_constraint_id":  "C045",
  "loser_constraint_id":   "C023",
  "arbitration_reason":    "MBOM来源优先级高于SOP，且500mm间距符合现场实际操作需求",
  "override_recommendation": false        // true 表示人工覆盖系统推荐
}

Response 200:
{
  "conflict_id":      "CONF-001",
  "status":           "RESOLVED",
  "winner":           "C045",
  "loser_new_state":  "SUPERSEDED",
  "kg_edge_created":  "C045 --SUPERSEDES--> C023",
  "downstream_cache_invalidated": ["PRD-3_layout_session_uuid"],
  "resolved_at":      "2026-04-09T15:30:00Z"
}
```

**错误码**：

| HTTP | 错误码 | 含义 | 前端处理建议 |
|------|--------|------|------------|
| 400 | `ERR_ARBITRATION_REASON_TOO_SHORT` | 仲裁理由少于 10 字 | 提示补充理由 |
| 400 | `ERR_CONSTRAINT_NOT_IN_CONFLICT` | 传入的约束 ID 不构成冲突对 | 刷新冲突清单 |
| 409 | `ERR_CONFLICT_ALREADY_RESOLVED` | 该冲突已被仲裁 | 跳转至已解决列表 |
| 422 | `ERR_WINNER_ALREADY_SUPERSEDED` | 拟保留的约束本身已被替代 | 提示选择有效约束 |

#### 🆕 审计字段

```json
{
  "audit_event":              "CONFLICT_ARBITRATED",
  "actor_user_id":            "user-uuid",
  "conflict_id":              "CONF-001",
  "winner_constraint_id":     "C045",
  "loser_constraint_id":      "C023",
  "arbitration_reason":       "MBOM来源优先级高于SOP...",
  "override_recommendation":  false,
  "kg_edge_written":          true,
  "downstream_notified":      ["PRD-3"],
  "timestamp":                "2026-04-09T15:30:00Z"
}
```

---

## §8 数据模型（ConstraintSet v3.0 完整 JSON）

> 🆕 v3.0 相对 v2.0 的新增字段已用注释 `// 🆕 v3.0` 标注。

```json
{
  "constraint_set_id":   "cs-uuid-v4-2024-001",
  "version":             "v3.0.1",
  "parent_version":      "v2.0.1",
  "hash_sha256":         "sha256:xyz789abc",           // 🆕 v3.0 内容指纹，CP-B Token 锁定
  "ontology_version":    "AeroOntology-v1.0",          // 🆕 v3.0 本体版本声明

  "trust_gate": {                                       // 🆕 v3.0 Trust Gate 元数据块
    "cp_a_token_id":     "CP-A-uuid",
    "cp_a_validated_at": "2026-04-09T10:05:00Z",
    "cp_b_token_id":     null,                         // 签发后填充
    "cp_b_issued_at":    null,
    "gate_checks": {
      "hard_conflicts_resolved":    false,
      "review_queue_empty":         false,
      "source_trace_rate":          0.991,
      "z3_sat_result":              "UNKNOWN",
      "low_confidence_count":       3
    }
  },

  "site_model_ref": {
    "id":      "SM-001",
    "version": "v1.2.3",
    "hash":    "sha256:abc123def456"                   // 🆕 v3.0 哈希绑定，防 SiteModel 静默变更
  },

  "meta": {                                             // 🆕 v3.0 解析质量元数据
    "total_constraints":      1284,
    "approved_count":         1247,
    "under_review_count":     3,
    "rejected_count":         12,
    "superseded_count":       22,
    "source_trace_rate":      0.991,
    "conflict_count_total":   5,
    "conflict_count_unresolved": 2,
    "parse_completed_at":     "2026-04-09T10:28:00Z"
  },

  "sop_sources": [
    {
      "doc_id":              "doc-uuid-001",            // 🆕 v3.0 关联 Document 对象
      "filename":            "某型飞机蒙皮装配工艺规程_v3.1.pdf",
      "doc_type":            "PDF_SOP",
      "classification_level":"CONFIDENTIAL",            // 🆕 v3.0 密级字段，驱动 LLM 路由
      "version":             "v3.1",
      "hash_sha256":         "sha256:doc001hash",       // 🆕 v3.0 文档指纹
      "parsed_at":           "2026-04-09T10:00:00Z",
      "parse_method":        "LLM",
      "llm_route_used":      "PRIVATE_QWEN2_LOCAL"      // 🆕 v3.0 实际路由记录
    }
  ],

  "constraints": [
    {
      "constraint_id":       "C001",                    // 🆕 v3.0 字段名从 id 改为 constraint_id
      "type":                "HARD",
      "category":            "SPATIAL",
      "authority_level":     "PMI",                     // 🆕 v3.0 权威来源级别
      "priority":            95,
      "lifecycle_state":     "APPROVED",                // 🆕 v3.0 生命周期状态
      "conflicts_with":      [],                        // 🆕 v3.0 冲突关联（由 Z3 写入）
      "supersedes":          null,                      // 🆕 v3.0 替代关系
      "superseded_by":       null,                      // 🆕 v3.0 被替代关系
      "rule": {
        "relation":  "MIN_DISTANCE",
        "entity_a":  "MDI-2024-001",
        "entity_b":  "MDI-2024-002",
        "value":     200,
        "unit":      "mm",
        "flexibility":"FIXED",
        "condition": null
      },
      "source_ref": {
        "doc_id":       "doc-uuid-001",
        "document":     "某型飞机蒙皮装配工艺规程_v3.1.pdf",
        "page":         12,
        "section":      "5.2.3",
        "text_snippet": "夹具A与设备B之间最小间距不得低于200mm",
        "pmi_3d_ref":   "CATIA://model/wing_skin.CATProduct#PMI-00234"
      },
      "confidence":          0.98,
      "parse_method":        "PMI_ENGINE",
      "requires_human_review":false,
      "verified_by":         "user-uuid-engineer",
      "verified_at":         "2026-04-09T11:30:00Z",
      "regulatory_ref":      "HB/Z 223-2013",
      "consequence_of_violation": "SAFETY_CRITICAL",
      "created_at":          "2026-04-09T10:05:00Z",
      "updated_at":          "2026-04-09T11:30:00Z",
      "mcp_context_id":      "ctx-uuid-002"
    }
  ],

  "aviation_specific_constraints": [
    {
      "id":               "AVC-003",
      "category":         "ENVIRONMENTAL",
      "type":             "HARD",
      "authority_level":  "SOP",                        // 🆕 v3.0
      "lifecycle_state":  "APPROVED",                   // 🆕 v3.0
      "rule":             "复合材料铺层区域温湿度控制：温度18-28°C，湿度<65%",
      "sensor_binding":   "ENV_SENSOR_ZONE_A",
      "action_on_violation": {                          // 🆕 v3.0 替代原 auto_suspend_on_violation 布尔值
        "action_type":        "SUSPEND_OPERATION",      // 对应 Action Catalog §17
        "target_operations":  ["N012","N013","N014"],
        "notify_roles":       ["PROCESS_ENGINEER","SYSTEM_ADMIN"],
        "resume_condition":   "传感器读数恢复正常范围持续 ≥ 30 分钟",
        "escalation_after_min": 60
      }
    },
    {
      "id":               "AVC-004",
      "category":         "CONFINED_SPACE_SAFETY",
      "type":             "HARD",
      "authority_level":  "SOP",
      "lifecycle_state":  "APPROVED",
      "rule":             "油箱内部作业，必须双人配合，通风换气≥30分钟后方可入内",
      "safety_level":     "LIFE_CRITICAL",
      "requires_permit":  true,
      "action_on_violation": {                          // 🆕 v3.0
        "action_type":        "ESCALATE_TO_HUMAN",
        "notify_roles":       ["PROCESS_ENGINEER","SYSTEM_ADMIN"],
        "block_downstream":   true,
        "escalation_after_min": 0                       // 立即升级，无延迟
      }
    }
  ],

  "process_graph": {
    "graph_id":    "pg-uuid-001",
    "version":     "v1.0.0",                            // 🆕 v3.0 ProcessGraph 独立版本号
    "granularity": "OPERATION",
    "nodes": [
      {
        "id":             "N001",
        "operation_id":   "op-uuid-001",                // 🆕 v3.0 关联 Ontology Operation 对象
        "device_ref":     "MDI-2024-001",
        "operation_name": "蒙皮钻孔",
        "op_type":        "DRILLING",
        "cycle_time_min": 45,
        "skill_level":    "L3",                         // 🆕 v3.0 枚举对齐 Ontology
        "parallel_capable": true,
        "milestone_flag": false                         // 🆕 v3.0 字段名对齐 Ontology
      }
    ],
    "edges": [
      {
        "from":          "N001",
        "to":            "N002",
        "constraint_id": "C001",
        "edge_type":     "SEQUENTIAL"
      }
    ],
    "milestone_nodes": ["N020","N035"]
  },

  "knowledge_graph_ref": {
    "uri":         "neo4j://kg/constraint_graph_v3.0.1",
    "node_count":  892,
    "edge_count":  1284,
    "last_sync":   "2026-04-09T11:45:00Z"             // 🆕 v3.0 同步时间戳
  },

  "mcp_context_id":  "ctx-uuid-002",
  "created_by":      "user-uuid-engineer",
  "created_at":      "2026-04-09T10:00:00Z",
  "updated_at":      "2026-04-09T15:30:00Z"
}
```

---

## §9 航空专属内容

### 9.1 工艺文档类型分级处理策略

| 文档类型 | 代表格式 | 解析技术 | LLM 角色 | 优先级 | 密级路由 |
|---------|---------|---------|---------|--------|---------|
| MBD 三维模型 | `.CATProduct` / `.prt` | PMI 解析引擎 | 辅助描述生成 | **P0** | 按文件密级路由 |
| 工艺规程（文字） | PDF / Word | LLM + OCR | 主要解析引擎 | **P0** | 按文件密级路由 |
| 工序卡（表格） | Excel / Word 表格 | 结构化提取 | 辅助理解表头 | P1 | 按文件密级路由 |
| 工艺 MBOM | Teamcenter / ENOVIA API | 系统集成导入 | 无需 LLM | P1 | 内网 API，无外发 |
| 装配手册（参考） | PDF | RAG 知识库（向量检索） | 知识问答 | P1 | 按文件密级路由 |
| 专家默会知识（快捷版） | Excel 模板导入 | 结构化解析 | 无需 LLM | **P1（已升）** | 本地处理 |
| 专家默会知识（完整版） | 语音 / 自由文本 | ASR + LLM 提取 | 主要提取引擎 | P2 | 本地 ASR + 私有 LLM |

### 9.2 三层解析架构（v3.0 增强版）

```
输入文档（MBD / SOP / MBOM / 专家语音）
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│  第一层：确定性提取（准确率 ≥ 99%，置信度默认 1.0）          │
│  · MBD → PythonOCC + 3DEXPERIENCE API → PMI 引擎             │
│  · MBOM → Teamcenter / ENOVIA REST API → 结构化映射           │
│  · Excel 工序卡 → 表格解析器 → 字段直接映射                   │
└────────────────────────┬─────────────────────────────────────┘
                         │ 未能提取的部分
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  第二层：LLM 语义解析                                         │
│  · 置信度 > 0.80 → 直接输出 DRAFT → 自动 APPROVED            │
│  · 置信度 0.50 ~ 0.80 → 标记 requires_human_review → 第三层  │
│  · 置信度 < 0.50 → 标记 REJECTED_DRAFT，阻止进入布局算法     │
│  LLM 路由：classification ∈ {CONFIDENTIAL, SECRET}           │
│            → 强制 PRIVATE_QWEN2_LOCAL                        │
│            否则 → 可配置 SaaS / 私有化                        │
└────────────────────────┬─────────────────────────────────────┘
                         │ 低置信度约束
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  第三层：人工审核队列                                         │
│  · 工艺工程师逐条确认 / 驳回                                  │
│  · 确认结果 → APPROVED，写入知识图谱                         │
│  · 驳回结果 → REJECTED，记录驳回原因                         │
│  · 所有操作回流微调训练数据集（形成知识飞轮）                 │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
        最终 ConstraintSet（100% 覆盖，准确率分级标注）
        → 触发 Z3 冲突检测 → 冲突仲裁（US-2-06）
        → Gate Checks 全通过 → 签发 CP-B Token
```

### 9.3 航空专属约束类型库 v3.0

| 类别 | 代码 | 典型规则示例 | 违规后果等级 | 来源规范 |
|------|------|------------|------------|---------|
| SEQUENCE | SEQ | 蒙皮铆接前必须完成钻孔检验 | `QUALITY_DEFECT` | HB/Z 223 |
| SPATIAL | SPA | 相邻型架间距 ≥ 200mm | `EFFICIENCY_LOSS` | 企业规范 |
| TORQUE | TRQ | 发动机安装螺栓十字交叉拧紧 [8,16,25]Nm | `SAFETY_CRITICAL` | GJB |
| SAFETY | SAF | 油箱作业双人配合 + 通风 ≥ 30 分钟 | `LIFE_CRITICAL` | GJB 9001 |
| ENVIRONMENTAL | ENV | 复材铺层区温度 18-28°C，湿度 < 65% | `QUALITY_DEFECT` | 企业规范 |
| REGULATORY | REG | 适航关键件每批次 100% 检验 | `REGULATORY_VIOLATION` | CAAC |
| FIXTURE_CONFLICT | FXC | F-007 占位时，相邻 2/4 站位禁止起吊 | `SAFETY_CRITICAL` | 企业规范 |
| CRITICAL_FASTENER | CFN | 每铆接点完成后目视检查，合格后进行下一孔 | `SAFETY_CRITICAL` | HB/Z 223 |
| CONFINED_SPACE | CSP | 密闭空间作业须持证，并有专人监护 | `LIFE_CRITICAL` | GJB 9001 |

---

## §10 技术选型声明

> 以下选型在 v2.0 基础上，增加了**选型约束条件**和**集成风险等级**两列，为研发排期提供决策依据。

| 功能模块 | 选型方案 | 选型理由 | 备选方案 | 集成风险 |
|---------|---------|---------|---------|---------|
| MBD PMI 解析（CATIA） | PythonOCC 7.7 + 3DEXPERIENCE API R2023x | CATIA 是成飞/商飞主流；PythonOCC 开源可控；API 覆盖 CATProduct/CATPart | CATIA VBA 宏（稳定性差，无法服务化） | 🔴 高：3DEXPERIENCE API 许可证成本高，私有化部署需甲方授权配合 |
| MBD PMI 解析（NX） | Siemens Open API + JT Open Toolkit 11.x | JT 轻量化格式可提取几何+PMI；Open API 官方支持 NX 2306+ | NX Open C++ API（本地依赖，难以服务化） | 🟡 中：JT 格式覆盖 NX，但 NX Open API 需要 NX 安装环境 |
| LLM 文字解析（SaaS） | GPT-4o（Azure OpenAI 中国区） | 中文理解强，POC 快速验证，API 稳定 | Claude 3.7 Sonnet | 🟢 低：REST API 接入，风险可控 |
| LLM 文字解析（私有化） | Qwen2.5-72B-Instruct + LoRA 微调 | 开源可控；中文航空工艺术语微调效果已验证；支持 vLLM 推理加速 | Llama 3.1-70B（中文偏弱）；DeepSeek-V3（推理成本高） | 🟡 中：72B 模型需 4×A100/H100，GPU 资源是关键依赖 |
| ASR 语音转文字（私有化） | FunASR Paraformer-Large（阿里达摩院，开源） | 国产最优中文 ASR，完全离线，WER < 5%（普通话） | Whisper Large v3（英文偏强，中文工业术语弱） | 🟢 低：开源，本地部署，无外部依赖 |
| 约束知识图谱 | Neo4j 5.x Enterprise（私有化）/ Community（SaaS） | 专为图关系查询优化；Cypher 查询语言成熟；APOC 插件支持复杂图算法 | PostgreSQL + Apache AGE（运维复杂）；TigerGraph（许可证贵） | 🟡 中：Enterprise 版许可证需采购；Community 版缺高可用支持 |
| 向量检索（RAG） | pgvector 0.7+（PostgreSQL 16 扩展） | 统一数据库，减少运维组件数；IVFFlat/HNSW 索引满足千万级向量检索 | Milvus 2.4（独立部署，运维成本高） | 🟢 低：PostgreSQL 扩展，无额外服务依赖 |
| 冲突检测引擎 | 自研分层规则引擎 + Z3 SMT Solver 4.12 | Z3 做 SAT/SMT 约束可满足性检验，学术验证充分；分层策略解决万条级性能问题 | CLP(FD)（Prolog 生态，工程集成难） | 🟡 中：Z3 Python binding 性能在万条级约束下需做分块优化 |
| 工艺 MBOM 接口 | Teamcenter REST API（TC 12.x+）/ ENOVIA REST API（R2022x+） | 航空央企（成飞/商飞/西飞）的主流 PLM 系统 | SOAP API（TC 老版本，已逐步淘汰） | 🔴 高：需要甲方 IT 开放 API 权限，通常需 2-4 周审批周期 |
| 约束审核 UI 框架 | React 18 + Ant Design Pro 5.x | 团队现有技术栈；Ant Design Pro 提供表格/表单/图谱组件 | Vue 3 + Element Plus | 🟢 低 |
| 知识图谱可视化 | AntV G6 5.x | 专为图可视化设计，支持万节点渲染；与 React 集成成熟 | Cytoscape.js（功能偏基础）；vis.js（大图性能差） | 🟢 低 |
| MCP 协议实现 | Anthropic MCP SDK（Python / TypeScript） | 官方 SDK，协议版本锁定，与 AI Agent 生态对接标准 | 自研 JSON-RPC（维护成本高） | 🟢 低 |
| 数据存储（主库） | PostgreSQL 16 | 结构化约束数据+版本快照；支持 JSONB 存储灵活扩展字段 | MySQL 8（JSON 支持弱） | 🟢 低 |
| 消息队列（异步任务） | Redis 7 + Celery 5 | 解析任务异步化；Redis 同时承担缓存和 Token 有效期管理 | RabbitMQ（运维复杂度更高） | 🟢 低 |

**🆕 私有化部署最低硬件规格（军工场景）**：

| 组件 | 最低配置 | 推荐配置 |
|------|---------|---------|
| LLM 推理服务（Qwen2.5-72B） | 4× NVIDIA A100 80GB | 8× H100 80GB |
| 应用服务器 | 32 核 CPU / 128GB RAM | 64 核 / 256GB RAM |
| Neo4j 图数据库 | 16 核 / 64GB RAM / 2TB NVMe SSD | 32 核 / 128GB RAM / 4TB NVMe SSD |
| PostgreSQL | 16 核 / 64GB RAM / 4TB SSD | 32 核 / 128GB RAM / 8TB SSD |
| 网络隔离 | 内网部署，无出站互联网访问 | 独立物理网络分区 |

---

## §11 非功能性需求（NFR）

### 11.1 性能需求

| 指标 | 要求 | 测量方式 | 违反后果 |
|------|------|---------|---------|
| 文字 SOP 解析（< 100 页） | P95 ≤ 5 分钟 | Prometheus `parse_duration_seconds` | P1 Bug |
| 文字 SOP 解析（100-500 页） | P95 ≤ 12 分钟 | 同上 | P1 Bug |
| MBD 解析（含 PMI 提取） | P95 ≤ 30 分钟 | 同上 | P1 Bug |
| 知识图谱单次约束查询 | P99 ≤ 500ms（图节点 ≤ 10,000） | Grafana 监控 | P2 Bug |
| 知识图谱路径影响查询 | P99 ≤ 2s（深度 ≤ 5 跳） | 同上 | P2 Bug |
| CP-B Token 签发（Gate Checks） | ≤ 10s | 服务端时间戳 | P2 Bug |
| 约束列表 API 响应 | P99 ≤ 200ms（page_size ≤ 200） | API 网关监控 | P2 Bug |
| Z3 冲突检测（≤ 1000 条约束） | ≤ 60s | 任务日志 | P2 Bug |
| Z3 冲突检测（1000-10000 条） | ≤ 10 分钟（分块并行） | 任务日志 | P2 Bug |
| 系统并发用户 | ≥ 50 用户同时操作，无降级 | 压力测试（k6） | P1 Bug |

### 11.2 安全需求

| 场景 | 要求 |
|------|------|
| 传输安全（民用 SaaS） | TLS 1.3，禁止 TLS 1.0/1.1；OAuth 2.0 + PKCE；JWT 有效期 ≤ 8 小时 |
| 传输安全（军工私有化） | 国密 SM4 加密传输；内网物理隔离，禁止任何出站互联网请求 |
| 存储安全 | 约束数据 AES-256 静态加密；`SECRET` 级文档加密存储，密钥由 HSM 管理 |
| API 安全 | 所有接口 Rate Limit：100 req/min/user；HARD 约束删除操作需二次确认 token |
| 审计日志 | 全部写操作（创建/修改/删除/仲裁）记录不可篡改审计日志，保留 ≥ 3 年 |
| LLM 调用安全 | `CONFIDENTIAL`/`SECRET` 文档强制路由私有化 LLM，服务端网络层拦截外部请求，审计日志记录每次 LLM 路由决策 |
| Token 管理 | CP-A / CP-B Token 携带内容哈希，验证时双重校验（Token 签名 + 内容哈希匹配） |

### 11.3 可靠性需求

| 指标 | 要求 |
|------|------|
| 服务可用性 | ≥ 99.5%（SaaS）；≥ 99.9%（私有化，含客户 IT 保障） |
| 解析任务失败重试 | 自动重试 3 次，指数退避（1s/2s/4s），第 4 次失败后发送告警 |
| 数据持久性 | 约束数据 + 知识图谱双活备份，RPO ≤ 1 小时，RTO ≤ 4 小时 |
| 异步任务可见性 | 所有解析任务状态实时可查，无「静默失败」，失败必有错误码 |

### 11.4 可扩展性需求

| 扩展维度 | 要求 |
|---------|------|
| 约束类型扩展 | 新增约束类别无需修改核心代码，通过配置文件注册新类型 |
| LLM 模型切换 | LLM 路由层抽象，新增模型只需实现统一 `LLMAdapter` 接口 |
| 规范库扩展 | 行业规范（GJB/HB/CAAC）版本化更新，支持热加载，不中断服务 |
| 图谱规模 | 架构支持单图谱 ≥ 100 万节点 / ≥ 500 万边，通过 Neo4j 分片扩展 |

### 11.5 合规需求

| 合规要求 | 实现方式 |
|---------|---------|
| 军工数据安全（保密法） | 完全私有化部署，数据不出厂区网络，操作人员实名制绑定 |
| 适航追溯（CAAC AC-21-03） | 每条适航关键约束携带 `regulatory_ref`，变更历史完整保留 |
| 数字签名完整性 | CP-B Token 使用 RSA-2048 签名，签名公钥由客户 PKI 基础设施管理 |

---

## §12 业务规则与异常处理

### 12.1 核心业务规则

| # | 规则 | 执行层 | 可否配置 |
|---|------|--------|---------|
| BR-01 | 未持有有效 CP-A Token，禁止创建解析会话 | 服务端强制 | ❌ |
| BR-02 | `authority_level` 冲突仲裁顺序：`PMI > SOP > MBOM_IMPORT > EXPERT_INPUT`，不可逆转 | 服务端强制 | ❌ |
| BR-03 | 置信度 < 0.50 的约束禁止进入布局算法（不论是否人工确认） | 服务端强制 | ❌ |
| BR-04 | `LIFE_CRITICAL` 级约束违规时，系统必须立即升级至人工（`ESCALATE_TO_HUMAN`），不允许 AI 自动处置 | 服务端强制 | ❌ |
| BR-05 | `SECRET` 级文档，LLM 路由必须为 `PRIVATE_*`，服务端网络层同步拦截 | 服务端强制 | ❌ |
| BR-06 | CP-B Token 签发需 6 项 Gate Check 全部通过（见 §5.3），任意一项失败即阻断 | 服务端强制 | ❌ |
| BR-07 | 约束被 `SUPERSEDED` 后，不可再被编辑，只可查看历史 | 服务端强制 | ❌ |
| BR-08 | 同一实体对、同 `category`、同 `relation` 不允许存在两条 `APPROVED` 状态的约束（由 `ERR_DUPLICATE_CONSTRAINT` 拦截） | 服务端强制 | ❌ |
| BR-09 | MBOM 导入完成后，ProcessGraph 版本号自动递增，相关 PRD-3 布局缓存自动失效 | 服务端强制 | ❌ |
| BR-10 | 仲裁时必须填写 `arbitration_reason`（≥ 10 字），否则提交被阻断 | 服务端 + 前端双校验 | ❌ |
| BR-11 | 解析任务超过 2 倍预计耗时未完成，系统自动发送超时告警，任务继续运行 | 可配置超时倍率 | ✅ |
| BR-12 | 专家手动录入（快捷版模板）的约束直接进入 `APPROVED` 状态，不进入审核队列 | 服务端 | ✅ 可关闭直接审批 |

### 12.2 异常处理完整矩阵

| 异常场景 | 检测时机 | 系统行为 | 用户提示 | 审计记录 |
|---------|---------|---------|---------|---------|
| CP-A Token 缺失 | 创建会话时 | HTTP 403，拒绝创建 | 「请先完成 PRD-1 SiteModel 锁版，获取 CP-A Token」 | ✅ |
| CP-A Token 对应的 SiteModel 哈希已变更 | 创建会话时 | HTTP 409，拒绝创建 | 「SiteModel 已更新，请重新锁版以获取新 CP-A Token」 | ✅ |
| MBD PMI 解析引擎不可用 | 解析任务启动时 | 降级为文字 SOP 路线，标记 `parse_method: LLM_FALLBACK` | 「PMI 引擎暂不可用，已自动降级为文字解析，精度可能降低」 | ✅ |
| LLM 解析置信度全批次 < 0.50 | 解析完成后 | 解析任务标记 `FAILED`，不输出约束集 | 「文档解析质量过低，建议检查文档格式或联系技术支持」 | ✅ |
| Z3 冲突检测超时（> 10 分钟） | 冲突检测任务中 | 任务超时，已检测部分保留，未检测部分标记 `CONFLICT_CHECK_PENDING` | 「约束数量超大，冲突检测超时，请分批提交或联系管理员增加算力」 | ✅ |
| 知识图谱写入失败（Neo4j 不可用） | 约束写入时 | 约束保存至 PostgreSQL 降级存储，标记 `kg_sync: PENDING` | 「图谱同步暂时中断，约束数据已安全保存，将在图谱恢复后自动同步」 | ✅ |
| 涉密文档误触发外部 LLM 路由 | 路由决策时 | 服务端强制中止请求，记录安全事件，告警 `SYSTEM_ADMIN` | 「检测到涉密文档，已阻断外部传输，请在私有化环境中操作」 | ✅ 安全级别 |
| 批量 Excel 导入格式错误 | 导入解析时 | 逐行报告错误，合法行正常写入 | 显示错误行清单（行号+错误原因），提供修正后的重传入口 | ✅ |
| CP-B Token 签发被 Gate Check 阻断 | 锁版确认时 | 返回未通过的 Gate Check 清单，阻断签发 | 显示具体阻断原因（如「剩余 2 条未仲裁冲突」），跳转至对应处理界面 | ✅ |
| 工程师删除 `APPROVED` 状态约束 | 删除操作时 | 阻断删除，提示应使用「废止」操作 | 「APPROVED 约束不可直接删除，请通过「废止」操作将状态改为 SUPERSEDED」 | ✅ |
| MBOM 导入 PLM 连接超时 | 导入任务中 | 任务失败，返回 `ERR_PLM_TIMEOUT`，不创建任何数据 | 「PLM 系统连接超时，请检查内网连通性或联系 IT 管理员」 | ✅ |

---

## §13 假设、风险与依赖

### 13.1 假设

| # | 假设内容 | 失效影响 | 验证方式 |
|---|---------|---------|---------|
| A1 | 客户 MBD 模型包含有效的 PMI 标注（非空白模型） | PMI 引擎无法提取约束，需全量依赖 LLM 文字解析 | 项目启动前抽样验证甲方 MBD 模型质量 |
| A2 | 文字 SOP 为中文或英文，无第三语言 | LLM 解析率下降 | 项目合同中明确文档语言范围 |
| A3 | 甲方可提供 PLM 系统（TC/ENOVIA）的 API 访问权限 | MBOM 导入功能无法实现 | 商务阶段确认 IT 访问条款 |
| A4 | 私有化部署客户具备 GPU 计算资源（≥ 4×A100 80GB） | Qwen2.5-72B 无法运行，需降级为更小模型（准确率降低） | 项目 POC 阶段确认硬件清单 |
| A5 | `master_device_id` 在企业主数据中唯一且规范（非自由文本） | Ontology 实体关联失败，约束图谱无法建立 | 对接 PLM 前验证主数据质量 |

### 13.2 风险登记册

| 风险 ID | 风险描述 | 概率 | 影响 | 综合等级 | 缓解措施 | 责任人 |
|--------|---------|------|------|---------|---------|--------|
| R-01 | 航空企业 MBD 覆盖率参差不齐，部分历史型号仍是纸质图纸扫描件 | 高 | 高 | 🔴 | 支持 OCR + LLM 组合处理扫描件；扫描件解析质量单独评估 | 产品 + 算法 |
| R-02 | Qwen2.5-72B 航空专业术语准确率不足 | 中 | 高 | 🔴 | 6 个月内完成航空工艺 SOP 领域 LoRA 微调；微调数据集目标 ≥ 10 万条 | 算法团队 |
| R-03 | 3DEXPERIENCE API 许可证成本超预算 | 中 | 中 | 🟡 | 优先推进 PythonOCC 开源路线；与甲方协商共用许可证 | 商务 + 架构 |
| R-04 | PLM 系统 API 开放审批周期过长（2-4 周） | 高 | 中 | 🟡 | 项目启动时同步推进 API 申请；Phase 1 提供手动 MBOM 导入（Excel）作为降级方案 | PM |
| R-05 | Z3 在万条级约束下性能不足 | 中 | 中 | 🟡 | 实施分块检测策略（按约束类别并行）；设置超时保护机制 | 架构 |
| R-06 | 工艺工程师拒绝录入默会知识（认为是泄露个人经验） | 中 | 低 | 🟢 | 产品设计中突出「个人贡献积分」激励机制；管理层推动 | 产品 + PM |
| R-07 | Neo4j Enterprise 许可证采购周期影响交付 | 低 | 中 | 🟢 | Phase 1 使用 Community 版，Phase 2 升级 Enterprise | 架构 |

### 13.3 外部依赖

| 依赖项 | 依赖类型 | 提供方 | 依赖说明 | 阻塞模块 |
|--------|---------|--------|---------|---------|
| PRD-1 CP-A Token | 内部模块依赖 | PRD-1 团队 | 本模块启动的前置条件 | 全部 |
| Teamcenter REST API | 外部系统集成 | 甲方 IT | MBOM 导入所需 | US-2-04 |
| 3DEXPERIENCE API | 商业 API | 达索系统 | CATIA PMI 精确解析 | US-2-01 |
| GPU 计算资源 | 基础设施 | 甲方（私有化）/ 云厂商（SaaS） | Qwen2.5-72B 推理 | US-2-01/02/05B |
| 航空工艺 SOP 样本数据 | 训练数据 | 甲方提供（脱敏后） | LLM 微调数据集构建 | KR2 指标达成 |

---

## §14 原型设计（Wireframe 描述）

### 14.1 主界面布局（三栏结构）

```
┌─────────────────────────────────────────────────────────────────────────┐
│  顶部导航栏                                                              │
│  [项目名] [CP-A Token 状态: ✅ 有效] [解析进度] [锁版确认] [导出JSON]    │
├──────────┬──────────────────────────────────────┬────────────────────────┤
│ 左侧面板  │          中间主工作区                 │    右侧面板             │
│          │                                      │                        │
│ 文件上传  │  Tab1: 约束列表                      │  原文溯源               │
│ ┌──────┐ │  ┌────────────────────────────────┐  │  ┌──────────────────┐  │
│ │MBD   │ │  │ [筛选: 类型/状态/冲突] [搜索]  │  │  │ 文档名: xxx.pdf  │  │
│ │SOP   │ │  ├────┬──────┬──────┬─────┬──────┤  │  │ 第12页 §5.2.3    │  │
│ │MBOM  │ │  │ID  │类型  │类别  │置信 │状态  │  │  │                  │  │
│ │专家  │ │  ├────┼──────┼──────┼─────┼──────┤  │  │ "夹具A与设备B之  │  │
│ └──────┘ │  │C001│HARD  │SPATIAL│0.98│✅    │  │  │  间最小间距不得  │  │
│          │  │C002│SOFT  │SEQ   │0.75│⚠️审核│  │  │  低于200mm"      │  │
│ 解析进度  │  │C023│HARD  │SPATIAL│0.92│🔴冲突│  │  └──────────────────┘  │
│ ████░░░  │  └────┴──────┴──────┴─────┴──────┘  │                        │
│  65%     │                                      │  3D PMI 定位            │
│          │  Tab2: 知识图谱可视化                 │  ┌──────────────────┐  │
│ 审核队列  │  ┌────────────────────────────────┐  │  │  [PMI 高亮视图]   │  │
│ 12条待审  │  │                                │  │  │                  │  │
│ 3条冲突  │  │  [工装节点图]                  │  │  └──────────────────┘  │
│          │  │  HARD=红线 SOFT=橙虚线         │  │                        │
│ Gate检查  │  │  节点按 category 着色          │  │  人工审核队列           │
│ ○G1未解  │  │  [拖拽创建约束]                │  │  ┌──────────────────┐  │
│ ●G2通过  │  └────────────────────────────────┘  │  │ C002 置信度:0.75  │  │
│ ○G3待统  │                                      │  │ LLM依据: "..."    │  │
│          │  Tab3: 冲突仲裁                       │  │ [✅确认] [❌驳回]  │  │
│          │  ┌────────────────────────────────┐  │  └──────────────────┘  │
│          │  │ CONF-001: C023 vs C045         │  │                        │
│          │  │ 推荐保留: C045 (MBOM > SOP)    │  │                        │
│          │  │ [采纳推荐] [手动覆盖] [查看原文] │  │                        │
│          │  └────────────────────────────────┘  │                        │
└──────────┴──────────────────────────────────────┴────────────────────────┘
```

### 14.2 关键交互说明

| 交互 | 触发方式 | 系统响应 |
|------|---------|---------|
| 上传 MBD/SOP 文件 | 拖拽或点击上传区 | 弹出密级确认对话框 → 确认后触发解析任务，进度条实时更新 |
| 点击约束行 | 单击列表中任意约束 | 右侧原文溯源面板跳转至对应文档页码 + PMI 3D 高亮（如有） |
| 拖拽图谱两节点连线 | 在知识图谱 Tab2 中操作 | 弹出「创建约束」快速填写面板（约束类型/关系