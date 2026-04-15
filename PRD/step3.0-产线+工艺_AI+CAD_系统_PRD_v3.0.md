# 产线+工艺 AI+CAD 系统
## 产品需求文档（PRD）v3.0
### Palantir 工程哲学修正后版本（Ontology × Trust × Action）

---

## 文档信息

| 项目 | 内容 |
|------|------|
| **文档版本** | v3.0 |
| **基于版本** | PRD v2.0 +《基于 Palantir 工程哲学的修正策略报告》（已评审通过） |
| **日期** | 2026年4月13日 |
| **状态** | 已修正待立项（Draft for Build） |
| **适用场景** | 航空总装脉动线 / 飞机部件装配 / 航空发动机总装 / 卫星柔性总装 |
| **关键词** | Ontology、本体驱动、单一真理源（SSOT）、信任令牌（Trust Token）、Action Catalog、决策闭环、可审计 |

### 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|---------|
| v2.0 | 2026-04-09 | 航空场景校准；OKR重建；数据模型补强；技术选型声明；新增MBD路线、知识图谱架构、DRL算法路线、AR接口、涉密合规章节 |
| **v3.0** | 2026-04-13 | **补全 Ontology 章节（PRD-0.6）；交接检查点升级为 Token-Based Trust Gate；补齐 Metric Definition Cards；新增 Action Catalog（可执行动作层）；专家默会知识录入拆为 P1/P2；PRD-5 改造为 Living Decision Board（活体决策工作台）** |

---

# PRD-0：产品总纲（修正）

## 0.1 产品定位

> **核心价值主张**：以 AI+CAD 为核心，为航空制造企业提供从底图解析 → 工艺约束结构化 → 布局优化 → 脉动仿真 → 决策工作台的全链路数字化规划平台，将新型号厂房方案论证周期从 6 个月缩短至 3 周。

| 维度 | 定义 |
|------|------|
| **目标市场** | 中国航空/航天制造业（总装厂、部装车间、发动机总装线）；兼顾高端装备制造 |
| **产品形态** | Web 端 + 私有化部署双模式（军工客户必须私有化） |
| **竞争策略** | 不与 Siemens Plant Sim、达索 3DEXPERIENCE 正面竞争；聚焦 **中文 MBD 工艺解析 + 航空专属约束 + 国产私有化部署** 三大差异化 |
| **工程哲学** | 以 **Ontology（本体）作为唯一真理源（SSOT）**，以 **Trust Token 作为跨模块信任传递**，以 **Action Catalog 把 AI 洞察落为可执行动作** |

## 0.2 差异化价值（保持 v2.0，补充“闭环”）

**vs 传统 CAD 工具（CATIA/AutoCAD）**：
- ✅ AI 驱动自动化：工艺约束结构化提取，减少 80% 人工转述
- ✅ 约束驱动布局优化，而非人工摆放
- ✅ **从“解析”走到“行动”：冲突/违规可触发自动告警、升级、暂停、回滚（Action Layer）**

**vs 竞品（Siemens Plant Sim / iFactory AI）**：
- ✅ 中文 MBD/SOP 解析能力（国产 LLM + 规则/图谱，专为中文工艺文档优化）
- ✅ 航空专属约束库（型架基础、吊车梁约束、脉动线节拍逻辑）
- ✅ 私有化部署满足军工数据安全要求
- ✅ **全链路审计：每条约束、每次锁版、每个决策都有可追溯证据链（Trust Chain）**

## 0.3 产品边界（保持 v2.0，补充“工作台”边界）

| 边界 | 说明 |
|------|------|
| ❌ 不出具法定可研报告 | 输出为“内部决策参考文件/工作台快照”，须由有资质咨询机构签章方可作为法定文件 |
| ❌ 不替代 CAAC 适航文件 | 工艺规程的适航批准须按监管要求单独处理 |
| ❌ 不自研工业级 CAD 几何核 | 集成 ODA / OpenCASCADE / PythonOCC |
| ❌ 不自研 DES 仿真引擎 | Phase 1 集成 FlexSim OEM 授权 |
| ❌ Phase 1 不做多厂房协同 | 先打通单厂房全链路 |
| ❌ 不处理军机涉密工艺数据上云 | 军机场景必须完全离线私有化部署 |

## 0.4 航空制造真实规模基准（保持 v2.0）

（同 v2.0，不再重复）

## 0.5 用户角色与跨模块交接流程（修正：用 Trust Token 表达“可机器验证”）

```
工艺工程师
    │ 上传 SOP/MBD → 解析 → 审核 ConstraintSet
    ▼
[Trust Gate A：ConstraintSet Lock Token]
    │
产线规划设计师
    │ 上传厂房底图 → 解析 → 校核 → 生成 SiteModel
    ▼
[Trust Gate B：SiteModel Lock Token]
    │
布局工程师
    │ 生成 LayoutCandidate → 硬约束验证 → 版本锁定
    ▼
[Trust Gate C：Layout Lock Token]
    │
仿真工程师
    │ 运行脉动仿真 → 产能/瓶颈/误差累积预测
    ▼
[Trust Gate D：SimResult Approval Token]
    │
项目经理/决策者
    │ Living Decision Board（活体决策工作台）
    ▼
输出：内部决策支持（快照 + 决策日志）
```

---

# PRD-0.6：Ontology（本体层，v3.0 新增，P0）

> 目的：建立全链路一致的“世界观”。任何模块中的数据对象必须先在 Ontology 中有定义；下游消费只认 Ontology ID，不认临时字段名。

## 0.6.1 对象类型（Object Types）

| ObjectType | 说明 | 唯一键（示例） | 生命周期（示例） |
|---|---|---|---|
| **Site** | 厂房/区域集合 | `site_id` | DRAFT → LOCKED |
| **Station** | 站位（空间/工位边界） | `station_id`（如 STATION_03） | PROPOSED → ACTIVE |
| **Asset** | 工装/设备（系统枢纽实体） | `master_device_id`（如 MDI-2024-007） | PROPOSED → ACTIVE → RETIRED |
| **Foundation** | 型架/重载基础 | `foundation_id` | ACTIVE |
| **CraneRunway** | 吊车梁/行车系统 | `crane_id` | ACTIVE |
| **RestrictedZone** | 禁区/防爆/洁净等区域 | `zone_id` | ACTIVE |
| **Obstacle** | 柱/墙/设施障碍 | `obstacle_id` | ACTIVE |
| **Document** | SOP/MBD/MBOM/标准 | `document_id`（hash+版本） | ACTIVE |
| **Constraint** | 约束（关系实体） | `constraint_id` | DRAFT → VERIFIED → ENFORCED |
| **Operation** | 工序节点 | `operation_id` | ACTIVE |
| **LayoutCandidate** | 布局方案 | `layout_id` | DRAFT → LOCKED |
| **SimResult** | 仿真结果 | `sim_id` | APPROVED |
| **Decision** | 决策记录（审计） | `decision_id` | FINAL |

## 0.6.2 关系类型（Link Types）

| LinkType | 方向 | 语义 |
|---|---|---|
| `Asset PLACED_IN Station` | Asset → Station | 工装位于某站位 |
| `Asset ANCHORED_TO Foundation` | Asset → Foundation | 工装锚定在基础上 |
| `Constraint GOVERNS Asset/Station/Operation` | Constraint → * | 约束作用对象 |
| `Constraint SOURCED_FROM Document` | Constraint → Document | 溯源 |
| `Operation USES Asset` | Operation → Asset | 工序使用工装 |
| `Operation PRECEDES Operation` | Operation → Operation | 前序关系 |
| `LayoutCandidate REFERENCES Site/Asset/Station` | Layout → * | 布局引用的本体对象 |
| `SimResult EVALUATES LayoutCandidate` | Sim → Layout | 仿真评估某方案 |
| `Decision BASED_ON {SiteModel, ConstraintSet, Layout, Sim}` | Decision → * | 决策依据 |

## 0.6.3 关键属性规范（Properties Contract）

- `master_device_id`：**全链路唯一，不可变**（Immutable Primary Key）
- `alias`：允许多系统别名（DWG/ERP/PLM/SOP）
- `authority_level`（约束权威等级）：`PMI > MBOM > SOP > EXPERT_INPUT`
- `confidence`：LLM/解析置信度（0~1）
- `verification_state`：`AUTO_VERIFIED | NEEDS_REVIEW | HUMAN_VERIFIED`
- `hash`：输入/对象快照的内容哈希（用于信任令牌锁定与回滚）

## 0.6.4 本体落地要求（工程约束）

- PRD-1 SiteModel、PRD-2 ConstraintSet、PRD-3/4/5 的输入输出字段必须映射到上述 Ontology 对象与关系。
- 任意跨模块引用必须使用 Ontology ID（如 `master_device_id`, `station_id`），禁止只用名称字符串。

---

# PRD-0.7：Metric Definition Cards（指标定义卡，v3.0 新增，P0）

> 每个 KR 必须“可测量、可回归、可阻断”。

## KR 指标卡模板

- **KR 编号**：
- **Metric 名称**：
- **严格定义（分子/分母/阈值）**：
- **Ground Truth 来源**：
- **测量触发（何时测）**：
- **生产监控（Dashboard/告警）**：
- **阈值行为（低于阈值系统如何动作）**：

## PRD-1 样例：KR3 大型障碍物自动识别率

- **KR 编号**：PRD-1 / KR3  
- **Metric 名称**：Obstacle Auto-Recognition Recall  
- **定义**：  
  - 分母：测试集中所有 `Obstacle` 且 footprint 面积 ≥ 0.25㎡（阈值可配置）的 ground truth 数量  
  - 分子：系统正确识别且分类正确（type 正确）的数量  
- **Ground Truth 来源**：甲方规划设计师在标注工具中确认后固化为 `testset_obstacle_v1`（版本化）  
- **触发**：每次解析引擎版本发布、规则库更新、或客户新增 1 张底图 → 自动回归  
- **监控**：内置 Dashboard：按厂房、按图层、按障碍类型统计  
- **阈值行为**：  
  - < 0.90：触发告警 + 强制人工校核  
  - < 0.85：阻断 Trust Gate B（禁止输出可锁版 SiteModel）

（其余 KR 在项目落地时按同模板补齐；Phase 1 至少覆盖 KR1/KR2/KR3/KR4 的指标卡。）

---

# PRD-0.8：Trust Gate（信任令牌机制，v3.0 新增，P0）

> 取代 v2.0 的人工勾选检查单。检查点不是“流程”，而是“可机器验证的授权信号”。

## 0.8.1 Trust Token 数据结构

```json
{
  "token_id": "CP-A-uuid-20260413-001",
  "token_type": "CONSTRAINTSET_LOCK | SITEMODEL_LOCK | LAYOUT_LOCK | SIM_APPROVAL",
  "authorized_by": "user_id_xxx",
  "authorized_at": "2026-04-13T09:30:00Z",
  "locked_inputs": {
    "object_id": "SM-001",
    "object_version": "v1.2.3",
    "object_hash": "sha256:..."
  },
  "validity_rule": "当 object_version 或 object_hash 变化时自动失效",
  "downstream_unblocked": ["PRD-3_LAYOUT_OPT"]
}
```

## 0.8.2 Gate 规则（Phase 1 必须实现）

- **Gate A（ConstraintSet 锁版）**：无 `HARD` 约束的 `NEEDS_REVIEW` 状态；冲突已仲裁；token 生成后，PRD-3 才可消费。
- **Gate B（SiteModel 锁版）**：坐标精度验证通过；`master_device_id` 匹配率达标；关键航空要素已确认；token 生成后，PRD-3 才可消费。
- **Gate C（Layout 锁版）**：硬约束 violation = 0；吊运路径干涉检测完成；token 生成后，PRD-4 才可消费。
- **Gate D（SimResult 审批）**：仿真参数集版本化；关键 KPI 达标；token 生成后，PRD-5 才可输出快照。

---

# PRD-0.9：Action Catalog（动作目录，v3.0 新增，P0）

> 让 AI 洞察在工作流中可执行。所有自动化动作通过 MCP Action 调用完成，并写入审计日志。

## 0.9.1 Action 分类

| Action | 触发条件 | 执行主体 | 输出 | 是否可阻断 |
|---|---|---|---|---|
| `requestHumanReview(constraint_id)` | `confidence < 0.80` 或 `NEEDS_REVIEW` | Agent 自动 | 审核任务 | ✅ |
| `escalateConstraintConflict(conflict_id)` | 冲突无法自动仲裁 | Agent 自动 | 工艺负责人通知 | ✅ |
| `resolveConflict(conflict_id, strategy)` | 权威等级明确（MBOM>…） | 人工确认/半自动 | 冲突结论 | ✅ |
| `lockObject(object_id, version)` | Gate 条件满足 | 人工授权 | Trust Token | ✅ |
| `invalidateDownstream(token_id)` | 上游版本变化 | 系统自动 | 下游失效标记 | ✅ |
| `suspendOperation(op_id, reason)` | 安全/环境硬约束违规 | 系统/Agent | 生产暂停指令 | ✅ |
| `notifyStakeholders(event)` | Gate 通过/失效/告警 | 系统自动 | 消息通知 | ❌ |

## 0.9.2 最小必做 Action（Phase 1）

- `requestHumanReview`
- `lockObject`（生成 Trust Token）
- `invalidateDownstream`
- `escalateConstraintConflict`

---

# PRD-1：语义化底图解析与环境构建（v3.0 修正）

**模块代号**：S1_SITE  
**版本**：v3.0  
**优先级**：P0

## 1. 需求背景与问题陈述（同 v2.0）

## 2. 业务目标与成功指标（OKR，保留 + 指标卡落地）

Objective 同 v2.0。KR 表保留，但必须关联到 PRD-0.7 指标卡。

## 3. 目标用户（同 v2.0）

## 4. 使用场景与用户故事（修正：把“锁版”写成 Trust Gate）

- US-1-01/02/03/04 保持，但新增：

**US-1-05（P0）**：SiteModel 锁版（Trust Gate B）
- **As a** 产线规划设计师  
- **I want** 在完成人工校核后，一键锁版输出 `SITEMODEL_LOCK` Token  
- **So that** 布局模块只能消费已锁版、可审计的 SiteModel

**AC**：
- 生成 `SITEMODEL_LOCK` Token（含 version + hash + authorized_by）
- 任何后续增量更新会 **自动使 token 失效** 并通知下游（`invalidateDownstream`）

## 5. 技术选型声明（同 v2.0）

## 6. 数据模型（SiteModel v3.0，修正：对齐 Ontology + hash）

```json
{
  "site_id": "SM-001",
  "site_guid": "uuid-v4",
  "version": "v1.3.0",
  "parent_version": "v1.2.3",
  "base_file_hash": "sha256:abc123",
  "object_hash": "sha256:siteModelContentHash",
  "change_summary": "…",
  "coordinate_system": { "unit": "mm", "reference": "GCP-001", "precision_general_mm": 1.0, "precision_critical_mm": 0.1 },
  "stations": [{ "station_id": "STATION_03", "polygon_wkt": "POLYGON((...))" }],
  "assets": [{ "master_device_id": "MDI-2024-001", "asset_guid": "uuid-v4", "aliases": { "erp_id": "2000001" } }],
  "restricted_zones": [{ "zone_id": "RZ-001", "type": "EXPLOSION_PROOF", "polygon_wkt": "POLYGON((...))" }],
  "created_at": "…",
  "mcp_context_id": "ctx-uuid-001"
}
```

> 注：v2.0 的 aviation_special_elements/obstacles 等字段保留，但需按 0.6.1 的对象类型拆分并具备稳定 ID。

## 7~14（规则库、NFR、流程、异常、图）保持 v2.0，新增一条工程要求：
- 所有输出对象必须携带 `object_hash`，用于 Trust Token 锁定。

---

# PRD-2：工艺文档转数字约束（v3.0 修正）

**模块代号**：S1_CONSTRAINT  
**版本**：v3.0  
**优先级**：P0

## 1~3（背景、OKR、用户）保持 v2.0，但 KR 必须具备指标卡（PRD-0.7）。

## 4. 使用场景与用户故事（修正：默会知识拆分 + Gate A）

**US-2-06（P0）**：ConstraintSet 锁版（Trust Gate A）
- **As a** 工艺工程师  
- **I want** 在完成冲突仲裁与低置信度审核后锁版约束集  
- **So that** 布局优化只消费“可审计且稳定”的约束集

**AC**：
- 无 `HARD` 约束处于 `NEEDS_REVIEW`
- 冲突列表为空或已仲裁并记录 decision
- 生成 `CONSTRAINTSET_LOCK` Token（含 object_hash）

**US-2-05 拆分（v3.0 调整优先级）**
- **US-2-05a（P1）结构化经验录入（快捷版）**：表单/Excel 模板导入，直接生成 `SOFT/HARD` 约束，强制选择 category/relation，避免自由文本歧义。
- **US-2-05b（P2）语音/自由文本经验提取（完整版）**：语音转写 + LLM → `requestHumanReview` 队列。

## 6. 数据模型（ConstraintSet v3.0，修正：对齐 Ontology + authority + hash）

```json
{
  "constraint_set_id": "CS-001",
  "version": "v2.1.0",
  "object_hash": "sha256:constraintSetContentHash",
  "site_model_ref": { "site_id": "SM-001", "version": "v1.3.0" },
  "sources": [
    { "document_id": "DOC-xxx", "type": "MBD_CATIA", "authority_level": "PMI", "hash": "sha256:..." }
  ],
  "constraints": [
    {
      "constraint_id": "C001",
      "type": "HARD",
      "category": "SPATIAL",
      "authority_level": "PMI",
      "rule": { "relation": "MIN_DISTANCE", "entity_a": "MDI-2024-001", "entity_b": "MDI-2024-002", "value": 200, "unit": "mm" },
      "confidence": 0.92,
      "verification_state": "AUTO_VERIFIED",
      "source_ref": { "document_id": "DOC-xxx", "page": 12, "pmi_3d_ref": "..." }
    }
  ],
  "knowledge_graph_ref": "neo4j://kg/constraint_graph_v2.1.0",
  "mcp_context_id": "ctx-uuid-002"
}
```

## 9. 三层解析架构（保持 v2.0，补充 Action）

- 第二层输出若 `confidence < 0.80`：必须触发 `requestHumanReview(constraint_id)`  
- 冲突无法自动仲裁：触发 `escalateConstraintConflict(conflict_id)`

---

# PRD-3：约束驱动布局优化（v3.0：补全与 Gate 对齐）

> v2.0 中仅在原型/导航出现，本节为 v3.0 补全“可交付定义”，以便全链路闭环。

**模块代号**：S2_LAYOUT  
**版本**：v3.0  
**优先级**：P0（Phase 1 需最小可用）

## 1. 输入与前置条件（强制）

- 必须持有有效 `SITEMODEL_LOCK` Token（Gate B）
- 必须持有有效 `CONSTRAINTSET_LOCK` Token（Gate A）

## 2. 输出

- `LayoutCandidate`（含 object_hash）
- 约束验证报告：`hard_violation_count`, `soft_violation_score`
- 可生成 `LAYOUT_LOCK` Token（Gate C）

## 3. 最小功能范围（Phase 1）

- 基于约束的可行性验证（硬约束 SMT/Z3 或规则引擎）
- 布局候选集管理（≥ 20 个候选）
- 关键场景：吊运净高/吊运路径干涉检测（最小版：几何碰撞 + clearance）
- 允许人工调整 + 实时校验

（DRL 多目标优化作为 Phase 2，保留路线但不作为 Phase 1 验收点）

---

# PRD-4：脉动仿真验证（v3.0：与 Token 对齐）

**模块代号**：S3_SIM  
**版本**：v3.0  
**优先级**：P1（Phase 1 可集成最小闭环）

- 输入：有效 `LAYOUT_LOCK` Token
- 输出：`SimResult`（版本化参数集 + object_hash）
- Gate D：生成 `SIM_APPROVAL` Token

---

# PRD-5：决策报告 → Living Decision Board（v3.0 重大修正，P1）

> v2.0 只强调“报告”，v3.0 改为“活体决策工作台 + 快照导出 + 决策日志”。

## 5.1 产出物分层

- **Layer 1：快照报告（PDF/Word）**：用于签字流程，引用锁版 token。
- **Layer 2：活体看板（Decision Board）**：与 SiteModel/ConstraintSet/Layout/SimResult 实时绑定；上游 token 失效时自动标记“过期”。
- **Layer 3：决策日志（Audit Log）**：记录谁在什么时间基于哪些 token 做了哪些决策（不可篡改）。

---

# 附录 A：MCP 接口（v3.0 补充 Action）

## A.1 数据类接口（沿用 v2.0）

- `parseCadFile() -> SiteModel`
- `parseWorkInstruction() -> ConstraintSet`

## A.2 动作类接口（v3.0 新增）

- `requestHumanReview(constraint_id) -> review_task_id`
- `lockObject(object_id, version, object_hash) -> trust_token`
- `invalidateDownstream(token_id) -> event_id`
- `escalateConstraintConflict(conflict_id) -> ticket_id`
- `suspendOperation(op_id, reason) -> suspend_event_id`

---

# 附录 B：交付清单（Phase 1 建议）

1. Ontology 服务（对象/关系/属性契约）+ ID 规范
2. Trust Token 服务（签发/验证/失效/审计）
3. PRD-1 SiteModel 解析 MVP（含 hash、版本、规则库）
4. PRD-2 ConstraintSet 解析 MVP（含 authority、confidence、review/action）
5. 布局可行性验证 MVP（不含 DRL）
6. Decision Board MVP（活体绑定 + 快照导出 + 决策日志）

