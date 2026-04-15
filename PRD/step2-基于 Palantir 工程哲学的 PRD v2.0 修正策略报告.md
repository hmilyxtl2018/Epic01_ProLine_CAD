
# 基于 Palantir 工程哲学的 PRD v2.0 修正策略报告

> **审视视角**：Palantir 的工程理论不是技术堆砌哲学，而是以「Ontology 作为唯一真理源」驱动决策的方法论，其核心三元：**Data × Logic × Action** 构成闭环。以此审视这份 PRD，可以发现结构性的弱点与可系统性修复的路径。

---

## 一、Palantir 工程哲学的五条核心公理

在开始审视之前，先建立评判标准：

| # | 公理 | 含义 |
|---|------|------|
| P1 | **Ontology 优先** | 所有实体必须先在本体（Ontology）中被定义，再被使用 |
| P2 | **决策闭环** | 系统的终点是「可执行决策」，而非数据或报告本身 |
| P3 | **操作化（Operationalization）** | AI 洞察必须被转化为可在真实工作流中执行的 Action |
| P4 | **FDE（前置部署工程师）模型** | 真正的价值在客户现场通过迭代实现，而非文档设计 |
| P5 | **信任链（Trust Chain）** | 每一层数据、每一个约束，必须可追溯其权威来源 |

---

## 二、PRD 当前的结构性问题

### 🔴 问题 1：缺失 Ontology 层 —— 实体定义先于数据流

**Palantir 视角**：
Palantir 的第一个动作永远不是「搭数据管道」，而是定义 **Ontology**：谁是实体？实体有哪些属性？实体之间有哪些关系？这个定义完成之前，任何数据流都是沙上建楼。

**PRD 中的问题**：
PRD-1 的 `SiteModel` 和 PRD-2 的 `ConstraintSet` 是两个独立的 JSON Schema，各自定义，通过 `site_model_ref` 松散引用。但这个产品中真正的核心实体是：

```
工装（Asset）← 这是整个系统的枢纽实体，连接了：
  → 厂房空间位置（SiteModel）
  → 工艺约束（ConstraintSet）
  → 工序节点（ProcessGraph）
  → 资源计划（仿真模块）
  → 决策报告（PRD-5）
```

**问题症状**：PRD 中 `master_device_id` 出现了 **7 次**，但没有一个地方明确定义「工装 Ontology」是什么——它的规范属性集、它的关系类型、它的生命周期状态。这导致下游每个模块都在重新理解同一个实体。

**修正策略**：

在 PRD 之前，先书写 **Ontology 章节（PRD-0.6）**：

```
Object Types（对象类型）：
  - Asset（工装）        ← 枢纽实体
  - Station（站位）      ← 空间实体
  - Operation（工序）    ← 时间实体
  - Constraint（约束）   ← 关系实体
  - Document（工艺文档） ← 溯源实体

Link Types（关系类型）：
  - Asset PLACED_IN Station
  - Asset GOVERNED_BY Constraint
  - Operation USES Asset
  - Operation PRECEDES Operation
  - Constraint SOURCED_FROM Document

Properties（关键属性）：
  - Asset.master_device_id     [唯一键，不可变]
  - Asset.lifecycle_state      [PROPOSED | ACTIVE | RETIRED]
  - Constraint.authority_level [PMI > SOP > EXPERT_INPUT]
  - Constraint.confidence      [0.0 ~ 1.0]
```

---

### 🔴 问题 2：检查点是「人工门禁」，而非「自动化信任传递」

**Palantir 视角**：
Palantir 在军事/工业场景中，最重视的不是检查点存在与否，而是 **信任链（Trust Propagation）**——每当一个检查点通过，它的「授权信号」要能被下游模块机器可读地消费，而不只是人工确认后继续操作。

**PRD 中的问题**：
检查点 A/B/C 的设计是「人工 checkbox 清单」：

```
□ SiteModel版本号已锁定？
□ 坐标系对齐已由设计师目视验证？
→ 以上全部通过，方可进入布局阶段
```

这里有三个工程缺陷：
1. **谁授权？** 人工确认后由谁签字、签到哪里，系统感知不到
2. **下游如何验证？** 布局模块如何知道「已通过检查点A」？靠约定还是靠信号？
3. **回滚触发器缺失**：如果 SiteModel 在检查点通过后被修改，下游是否自动失效？

**修正策略**：

将检查点重新设计为 **Token-Based Trust Gate**：

```json
// 检查点 A 通过后，系统生成一个不可变的信任令牌
{
  "checkpoint_token": "CP-A-uuid-20260409",
  "checkpoint_type": "SITE_TO_LAYOUT",
  "authorized_by": "user_id_designer_zhang",
  "authorized_at": "2026-04-09T14:30:00Z",
  "locked_inputs": {
    "site_model_id": "SM-001",
    "site_model_version": "v1.2.3",
    "site_model_hash": "sha256:abc123"
  },
  "validity_rule": "当 SM-001 版本变更时，本令牌自动失效",
  "downstream_modules_unblocked": ["PRD-3_布局优化"]
}
```

布局模块在启动时，**必须验证有效的 checkpoint_token**，而非由人工判断「是否可以开始」。这是 Palantir 在 Gotham/Foundry 中处理数据管道授权的核心机制。

---

### 🟡 问题 3：PRD 把「OKR」和「验收标准（AC）」混淆使用

**Palantir 视角**：
Palantir 的 FDE（前置部署工程师）在现场的第一周做的事情，是把客户说的「目标」翻译成 **可在系统中测量的指标（Metric Object）**。这两件事的语言完全不同：

- OKR 是**方向性承诺**（业务层面）
- AC 是**可验证的系统行为**（工程层面）
- Metric Object 是**系统中持续自动测量的数据点**（Palantir 特有）

**PRD 中的问题**：
PRD-1 的 KR 写道：
> KR3：大型障碍物自动识别率≥92%

但这句话有三个未解决的工程问题：
1. 「大型障碍物」的定义是什么（尺寸阈值？类型白名单？）
2. 测量集是「50张航空厂房图」——这50张图从哪来？谁标注了 ground truth？
3. 这个指标在生产环境中如何**持续**监控，还是只在验收时测一次？

**修正策略**：

为每个 KR 配套一张 **Metric Definition Card**：

```
KR3 障碍物识别率
├── 分子定义：系统正确标注语义类别的障碍物数量
├── 分母定义：测试集中所有 footprint > 500mm² 的实体
├── ground_truth 来源：由甲方工艺师手动标注，存入版本化测试集库
├── 测量触发：每次新型号厂房图解析后自动触发回归测试
├── 阈值行为：低于 90% → 告警；低于 85% → 阻断下游流程
└── 监控方式：系统内置 Dashboard，而非仅验收时人工测试
```

---

### 🟡 问题 4：MCP 协议的使用停留在「管道层」，未上升到「行动层（Action Layer）」

**Palantir 视角**：
在 Palantir AIP 架构中，MCP（或等价的 Agent 通信协议）不只是传输 JSON 的管道。其更关键的用途是 **将 AI 洞察连接到可执行的 Action**。在 Palantir 的语言里：

```
Data → Insight → Action
（只有走完这三步，才构成价值闭环）
```

**PRD 中的问题**：
PRD 中 MCP 的用途是：
- `parseCadFile()` → 返回 SiteModel（Data 层）
- `parseWorkInstruction()` → 返回 ConstraintSet（Data 层）

MCP 始终停在「生成结构化数据」这一步，没有定义任何 **MCP Action**——即 AI Agent 识别问题后，它能调用什么行动？

举例：当 Z3 冲突检测引擎发现 C023 vs C045 约束冲突时，系统目前的行为是「高亮并等待人工」。但 Palantir 的设计会问：
- AI Agent 能不能直接调用 `resolveConflict(C023, C045, strategy="MBOM_PRIORITY")` 这个 Action？
- Action 执行后，能否自动通知上游工艺工程师审批？
- 审批结果能否自动回写约束图谱并触发下游重新验证？

**修正策略**：

在 PRD-2 中增加 **Action Catalog（动作目录）**：

```
系统支持的 MCP Action 类型：
┌─────────────────────────────────────────────────────────┐
│ Action                   │ 触发条件       │ 执行主体     │
├─────────────────────────────────────────────────────────┤
│ escalateConstraintConflict │ 冲突置信度>0.9 │ AI Agent 自动 │
│ lockSiteModelVersion      │ 检查点确认     │ 人工授权      │
│ suspendOperation          │ 环境约束违规   │ AI Agent 自动 │
│ requestHumanReview        │ 置信度<0.80   │ AI Agent 自动 │
│ propagateChangeImpact     │ 版本变更时     │ AI Agent 自动 │
└─────────────────────────────────────────────────────────┘
```

其中 `suspendOperation`（对应 AVC-003 温湿度约束违规时自动暂停生产）是最接近 Palantir「Action 闭环」的场景——PRD 中只用了一个字段 `"auto_suspend_on_violation": true`，但没有定义谁执行这个 suspend、suspend 的通知链是什么、如何恢复。

---

### 🟡 问题 5：PRD-5（决策报告）与全链路数据的连接过于薄弱

**Palantir 视角**：
Palantir Foundry 最核心的产出物不是「漂亮的报告」，而是 **与实时数据绑定的决策工作台（Decision Board）**。报告一旦导出为 PDF，就与数据脱节，就死了。

**PRD 中的问题**：
PRD-0 的产品定位最后一步是「生成内部决策报告」（PRD-5），但整个 PRD 对 PRD-5 几乎没有描述。更危险的是：

> 「输出为内部决策参考文件，须由有资质咨询机构签章方可作为法定文件」

这个边界声明本身没有问题，但它掩盖了一个工程问题：**决策报告如果是静态文档，那整个数字化平台的价值就在打印时消失了。**

**修正策略**：

将 PRD-5 重新定义为 **活体决策工作台（Living Decision Board）**，包含三个层次：

```
Layer 1: 快照报告（传统需求）
  → 可导出 PDF/Word，供签字流程使用
  → 包含：布局方案比对、约束满足率、仿真结论、投资估算

Layer 2: 活体看板（Palantir 增量）
  → 与 SiteModel/ConstraintSet 实时绑定
  → 任何上游数据变更，自动触发「报告已过期」提示
  → 项目经理可在报告上直接标注「已采纳/否决」某方案

Layer 3: 决策日志（审计要求）
  → 每个关键决策节点记录：谁在什么时间基于哪个版本的数据做了什么决策
  → 形成不可篡改的决策链，满足军工质量审计要求
```

---

### 🔵 问题 6：「默会知识录入」（US-2-05）是高价值功能，但被降级为 P2

**Palantir 视角**：
Palantir 在军事/工业场景反复验证的一个核心洞见：**系统中最有价值的数据，往往是那些最难数字化的数据**——即老专家的经验判断、战场态势感知、生产一线的异常直觉。Palantir 的 FDE 模型中，大量时间花在「把人脑中的模型变成系统中的对象」。

**PRD 中的问题**：
US-2-05（专家默会知识录入）被定为 P2，意味着它可能在 Phase 1 中被砍掉。但这恰恰是最可能形成竞争壁垒的功能——因为竞品无法复制客户自己的知识积累。

**修正策略**：

将 US-2-05 拆解为两个优先级不同的子功能：

```
P1: 结构化经验录入（快捷版）
  → 提供标准约束模板（间距类/序列类/安全类）
  → 工程师填空式录入，无需自由文本
  → 5分钟内完成一条经验约束录入
  → 最低可行版本：Excel 导入模板

P2: 语音/自由文本经验提取（完整版）
  → LLM 解析后，进入人工审核队列
  → 与现有三层解析架构共用基础设施
```

P1 版本的开发成本极低（复用现有约束录入界面），但能在 Phase 1 就开始积累客户专属知识图谱——这是产品「越用越聪明」的飞轮启动点。

---

## 三、修正路线图（优先级排序）

```
修正优先级
│
├── 🔴 必须在 Phase 1 完成（影响架构根基）
│     ├── M1: 书写 Ontology 章节 (PRD-0.6)
│     │     定义 Asset/Station/Constraint/Operation 对象类型和关系类型
│     │     工期估算: 1周（由产品+工艺工程师联合定义）
│     │
│     └── M2: 检查点重设计为 Token-Based Trust Gate
│           取代当前「人工 checkbox」模式
│           工期估算: 2周（后端 + 前端联动）
│
├── 🟡 应在 Phase 1 中完成（影响产品可信度）
│     ├── M3: 为每个 KR 配套 Metric Definition Card
│     │     含 ground truth 构建计划 + 持续监控机制
│     │
│     ├── M4: 在 PRD-2 中增加 Action Catalog
│     │     至少定义 suspendOperation 和 escalateConflict 两个动作的完整规格
│     │
│     └── M5: 将默会知识录入拆分，P1 版本纳入 Phase 1
│
└── 🔵 Phase 2 完成（增强产品差异化）
      └── M6: PRD-5 升级为 Living Decision Board
            含活体看板 + 决策日志两层
```

---

## 四、一句话核心判断

> 这份 PRD 目前是**高质量的「功能需求文档」**，但还不是 Palantir 意义上的**「决策基础设施规格书」**。两者的差距，不在于功能多少，而在于：数据是否以 Ontology 为中心被组织？每个 AI 洞察是否都有对应的可执行 Action？每个决策节点是否都留下可审计的信任链？

修正这三点，PRD v3.0 就具备了真正的 Palantir 基因。
