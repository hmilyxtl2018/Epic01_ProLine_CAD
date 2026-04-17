# 产线 Multi-Agent 协同闭环系统 — 功能测试计划（按 Agent 能力重构）

**版本**: v1.0  
**创建日期**: 2026-04-15  
**适用范围**: ParseAgent + ConstraintAgent + LayoutAgent + Orchestrator 闭环  
**重构依据**:
- ExcPlan/产线 Multi-Agent 协同 — 三个 Agent 实例化 Profile 设计.md
- ExcPlan/工艺产线 Multi-Agent 协同系统 — 完整实现执行计划.md
- PRD/step3.3-PRD-3：约束驱动布局优化 v3.0 完整文档.md

---

## 1. 重构背景

现有的 [PRD/step5.2-关键技术验证计划.md](../PRD/step5.2-关键技术验证计划.md) 以 Spike 为中心，重点回答“某项技术可不可行”，例如 DWG 解析、MCP 通信、碰撞检测、RAG 检索等。

这种组织方式适合 PoC 阶段，但不适合作为三 Agent 系统的功能测试主计划，原因有三点：

1. Spike 测试围绕技术点拆分，不能直接映射到 Agent 的业务职责。
2. Spike 测试缺少对输入契约、输出契约、状态流转、Gate 条件和审计链路的完整验证。
3. Spike 测试不直接回答“某个 Agent 是否具备可交付的服务能力”。

因此，本计划改为以“功能能力”和“服务输出”组织测试，目标是回答以下问题：

1. ParseAgent 是否能把 CAD 输入稳定转换为可信 SiteModel。
2. ConstraintAgent 是否能对 SiteModel 做可追溯的硬约束校验和软约束评分。
3. LayoutAgent 是否能基于约束结果生成、验证、对比和锁定候选布局方案。
4. 三个 Agent 之间的 mcp_context、Token 和状态流转是否完整闭环。

---

## 2. 文档认知结论

### 2.1 三个 Agent 的功能定位

| Agent | 核心职责 | 输入 | 核心服务能力 | 主要输出 |
|------|------|------|------|------|
| **ParseAgent** | CAD 解析、几何修补、本体识别、语义链接 | CAD 文件 + 坐标系设置 | 格式检测、实体提取、坐标归一化、几何完整性修补、资产识别、关系映射、SiteModel 序列化 | `SiteModel`、`Ontology Graph`、`Confidence Stats`、`mcp_context` |
| **ConstraintAgent** | 约束检查、冲突识别、软约束评分、诊断建议 | `SiteModel` + `ConstraintSet` | 约束集加载、硬/软约束分类、约束图构建、Z3 硬约束校验、UNSAT/冲突识别、软约束评分、违规报告生成 | `Violations`、`Soft Scores`、`Reasoning Chain`、`mcp_context` |
| **LayoutAgent** | 候选布局生成、实时验证、吊运干涉检测、方案对比、锁版 | `SiteModel` / `Violations` / `Soft Targets` / Gate A+B Token | 启动布局会话、候选生成、实时硬约束验证、吊运路径检测、方案对比、推荐方案、Gate C 锁版、失效联动 | `LayoutCandidate[]`、`LayoutViolation[]`、`LAYOUT_LOCK Token`、`Reasoning Chain`、`mcp_context` |

### 2.2 原始设计文档的完整性结论

当前 [ExcPlan/产线 Multi-Agent 协同 — 三个 Agent 实例化 Profile 设计.md](产线%20Multi-Agent%20协同%20—%20三个%20Agent%20实例化%20Profile%20设计.md) 并不完整：

1. Agent1 内容完整，覆盖职责、Action Flow、Schema、完成条件。
2. Agent2 只完整写到约束集加载，后续“硬约束检查”开始处中断。
3. Agent3 在该文件中缺失，需要结合 [ExcPlan/工艺产线 Multi-Agent 协同系统 — 完整实现执行计划.md](工艺产线%20Multi-Agent%20协同系统%20—%20完整实现执行计划.md) 与 [PRD/step3.3-PRD-3：约束驱动布局优化 v3.0 完整文档.md](../PRD/step3.3-PRD-3：约束驱动布局优化%20v3.0%20完整文档.md) 补全。

因此，本测试计划采用“主文档 + 补充设计文档”的联合口径。

---

## 3. 测试总目标

### 3.1 功能目标

1. 证明三个 Agent 各自具备独立可交付的业务能力，而不仅是技术骨架。
2. 证明 Agent 输出满足 JSON/领域契约，可被下游 Agent 消费。
3. 证明系统在失败、降级、人工复核和 Token 失效场景下行为可控。
4. 证明系统具备闭环能力：输入 CAD，最终得到可锁版的布局方案与审计链。

### 3.2 非目标

以下内容不作为本计划主体，但可由专项计划补充：

1. 第三方底层库可行性验证，例如 ODA、IfcOpenShell、PythonOCC 的单独选型试验。
2. LLM Prompt 策略优劣对比。
3. DRL Phase 2 优化效果验证。

---

## 4. 测试设计原则

### 4.1 以服务能力为中心，而不是以模块源码为中心

每个测试项必须回答以下三件事：

1. Agent 提供了什么服务能力。
2. 该能力对外的输入输出契约是什么。
3. 该能力是否在正常、异常、边界条件下都满足业务要求。

### 4.2 以输出可消费性为核心断言

不是只验证“函数返回了值”，而是验证：

1. 输出是否字段完整。
2. 输出是否满足下游使用前提。
3. 输出是否携带溯源、版本、置信度、Token、状态字段。

### 4.3 以 Gate 与状态机为主线组织跨 Agent 测试

关键断言包括：

1. Gate A/B 无效时，Layout 会话不得启动。
2. `hard_violation_count > 0` 时，不得生成 Gate C 锁版结果。
3. 上游对象变更时，下游方案必须自动失效。

---

## 5. 测试范围与层次

| 层次 | 测试目的 | 主要对象 |
|------|------|------|
| **L1 契约测试** | 验证输入输出 Schema、字段、错误码、状态枚举 | 三个 Agent 的 API / Service 契约 |
| **L2 功能测试** | 验证单个 Agent 的业务能力是否成立 | Parse / Constraint / Layout 单 Agent |
| **L3 场景测试** | 验证跨能力组合后的业务场景是否闭环 | 单 Agent 内的多步骤场景 |
| **L4 集成测试** | 验证 Agent 间数据消费、mcp_context、Token 传递 | Agent1→2→3→Orchestrator |
| **L5 验收测试** | 验证系统是否满足交付口径与 Gate 条件 | 端到端闭环 |

---

## 6. 测试数据分层

### 6.0 第一步：Spike-01 用例输入界定

本节只定义第一批测试输入文件，不定义测试步骤，不定义预期结果。

#### 6.0.1 输入界定原则

第一批输入集只从 [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world](../spikes/spike_01_dwg_parse/test_data/real_world) 选择，并遵循以下原则：

1. 必须包含真实业务样本，且强制纳入 `20180109_机加车间平面布局图.dwg`。
2. 优先选择 `.dwg` 作为 ParseAgent 第一阶段主输入，因为当前目标是先界定 CAD 原始输入，而不是 ODA 转换后的 DXF 对照输入。
3. 输入集必须覆盖三类风险：真实车间图、工业产线图、DWG 版本兼容图。
4. 第一批输入集控制在 6 到 8 个文件，避免一开始样本过多导致验证焦点分散。

#### 6.0.2 第一批主输入集

| 输入ID | 文件 | 类型 | 选择原因 | 归属用途 |
|------|------|------|------|------|
| IN-DWG-001 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/20180109_机加车间平面布局图.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/20180109_%E6%9C%BA%E5%8A%A0%E8%BD%A6%E9%97%B4%E5%B9%B3%E9%9D%A2%E5%B8%83%E5%B1%80%E5%9B%BE.dwg) | DWG | 必选真实样本；中文命名；顶层文件中体量最大之一，适合作为真实车间主基线 | 真实业务基线样本 |
| IN-DWG-002 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/fish_processing_plant.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/fish_processing_plant.dwg) | DWG | 大型工业平面图；对应清单显示图层多、结构复杂 | 大规模复杂样本 |
| IN-DWG-003 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/cold_rolled_steel_production.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/cold_rolled_steel_production.dwg) | DWG | 完整生产线布局；适合验证产线级设备与流程区域提取 | 典型产线样本 |
| IN-DWG-004 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/woodworking_plant.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/woodworking_plant.dwg) | DWG | 小体量工业图；适合做快速回归和小样本正确性验证 | 小样本回归基线 |
| IN-DWG-005 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/woodworking_factory_1.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/woodworking_factory_1.dwg) | DWG | 中等复杂度；可与上一条组成中小规模对照组 | 中等规模对照样本 |
| IN-DWG-006 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/example_2000.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/example_2000.dwg) | DWG | R2000 版本参考样本 | 格式兼容样本 |
| IN-DWG-007 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/example_2007.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/example_2007.dwg) | DWG | R2007 版本参考样本 | 格式兼容样本 |
| IN-DWG-008 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/example_2018.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/example_2018.dwg) | DWG | R2018 版本参考样本 | 格式兼容样本 |

#### 6.0.3 补充输入集

以下文件暂不放入第一批主输入集，但保留为第二轮补充样本：

| 文件 | 暂缓原因 | 后续用途 |
|------|------|------|
| [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/807_complex.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/807_complex.dwg) | 更偏“复杂格式/复杂结构参考图”，不优先于真实业务样本 | 复杂结构兼容性补测 |
| [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/cold_rolled_steel_production.dxf](../spikes/spike_01_dwg_parse/test_data/real_world/cold_rolled_steel_production.dxf) | 属于转换后 DXF 对照文件，不是第一步的原始输入 | DWG↔DXF 对照验证 |
| [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/fish_processing_plant.dxf](../spikes/spike_01_dwg_parse/test_data/real_world/fish_processing_plant.dxf) | 同上 | DWG↔DXF 对照验证 |
| [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/woodworking_plant.dxf](../spikes/spike_01_dwg_parse/test_data/real_world/woodworking_plant.dxf) | 同上 | DWG↔DXF 对照验证 |
| [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/woodworking_factory_1.dxf](../spikes/spike_01_dwg_parse/test_data/real_world/woodworking_factory_1.dxf) | 同上 | DWG↔DXF 对照验证 |

#### 6.0.4 第一批输入界定结论

Spike-01 第一阶段 ParseAgent 用例输入，正式界定为以上 8 个 DWG 文件，其中 [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/20180109_机加车间平面布局图.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/20180109_%E6%9C%BA%E5%8A%A0%E8%BD%A6%E9%97%B4%E5%B9%B3%E9%9D%A2%E5%B8%83%E5%B1%80%E5%9B%BE.dwg) 作为主基线样本，必须出现在后续所有 P0 输入集里。

#### 6.0.5 第二步：将 8 个输入映射为正式用例分组

本节把已经确定的输入文件映射到后续测试分组。分组目标不是重新选文件，而是明确每个文件在测试体系中的角色，避免同一文件在不同用例里被重复、随意使用。

##### A. P0 基线组

用途：验证 ParseAgent 最基本、最关键的真实业务输入处理能力。凡是 P0 的解析能力用例，必须至少从本组取样。

| 分组ID | 文件 | 分组理由 |
|------|------|------|
| G-P0-BASE-01 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/20180109_机加车间平面布局图.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/20180109_%E6%9C%BA%E5%8A%A0%E8%BD%A6%E9%97%B4%E5%B9%B3%E9%9D%A2%E5%B8%83%E5%B1%80%E5%9B%BE.dwg) | 指定必选主样本，代表真实车间场景 |
| G-P0-BASE-02 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/cold_rolled_steel_production.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/cold_rolled_steel_production.dwg) | 代表完整工业产线布局 |
| G-P0-BASE-03 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/woodworking_plant.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/woodworking_plant.dwg) | 代表小规模快速回归样本 |

##### B. 规模覆盖组

用途：验证 ParseAgent 在小、中、大不同规模输入下的稳定性。后续性能、资源占用、超时阈值类用例优先从本组取样。

| 分组ID | 文件 | 规模定位 |
|------|------|------|
| G-SIZE-S | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/woodworking_plant.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/woodworking_plant.dwg) | 小规模 |
| G-SIZE-M | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/woodworking_factory_1.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/woodworking_factory_1.dwg) | 中等规模 |
| G-SIZE-L | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/fish_processing_plant.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/fish_processing_plant.dwg) | 大规模复杂图 |
| G-SIZE-XL | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/20180109_机加车间平面布局图.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/20180109_%E6%9C%BA%E5%8A%A0%E8%BD%A6%E9%97%B4%E5%B9%B3%E9%9D%A2%E5%B8%83%E5%B1%80%E5%9B%BE.dwg) | 超大真实车间主样本 |

##### C. 业务语义覆盖组

用途：验证真实工业场景中，设备、区域、墙体、轨道、流程布局等语义对象是否可被稳定提取。后续资产识别、语义映射、低置信路由用例优先从本组取样。

| 分组ID | 文件 | 语义覆盖重点 |
|------|------|------|
| G-SEM-01 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/20180109_机加车间平面布局图.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/20180109_%E6%9C%BA%E5%8A%A0%E8%BD%A6%E9%97%B4%E5%B9%B3%E9%9D%A2%E5%B8%83%E5%B1%80%E5%9B%BE.dwg) | 真实车间设备与区域语义 |
| G-SEM-02 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/cold_rolled_steel_production.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/cold_rolled_steel_production.dwg) | 产线流程型语义对象 |
| G-SEM-03 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/fish_processing_plant.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/fish_processing_plant.dwg) | 多图层复杂工业语义 |
| G-SEM-04 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/woodworking_factory_1.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/woodworking_factory_1.dwg) | 中小规模对象分类对照 |

##### D. 版本兼容组

用途：验证 ParseAgent 的 DWG 版本识别和兼容链路。后续格式检测和兼容性回归用例统一从本组取样。

| 分组ID | 文件 | 版本定位 |
|------|------|------|
| G-VER-2000 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/example_2000.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/example_2000.dwg) | R2000 |
| G-VER-2007 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/example_2007.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/example_2007.dwg) | R2007 |
| G-VER-2018 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/example_2018.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/example_2018.dwg) | R2018 |

##### E. 回归最小集

用途：后续每次代码改动后快速验证主链路是否被破坏。该组故意收缩为 3 个文件，强调执行成本低、覆盖价值高。

| 分组ID | 文件 | 选择理由 |
|------|------|------|
| G-REG-01 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/20180109_机加车间平面布局图.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/20180109_%E6%9C%BA%E5%8A%A0%E8%BD%A6%E9%97%B4%E5%B9%B3%E9%9D%A2%E5%B8%83%E5%B1%80%E5%9B%BE.dwg) | 真实业务主样本 |
| G-REG-02 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/woodworking_plant.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/woodworking_plant.dwg) | 小样本快速回归 |
| G-REG-03 | [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/example_2018.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/example_2018.dwg) | 最新版本兼容回归 |

#### 6.0.6 用例分组使用规则

后续测试设计时，统一按以下规则引用输入文件：

1. P0 功能正确性测试，至少覆盖 A 组和 C 组。
2. 性能与资源占用测试，优先覆盖 B 组。
3. 格式检测与兼容性测试，只从 D 组选取。
4. CI 快速回归默认使用 E 组。
5. 任意 P0 套件都不得移除 [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/20180109_机加车间平面布局图.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/20180109_%E6%9C%BA%E5%8A%A0%E8%BD%A6%E9%97%B4%E5%B9%B3%E9%9D%A2%E5%B8%83%E5%B1%80%E5%9B%BE.dwg) 。

### 6.1 ParseAgent 测试数据

1. 小型 CAD 样本：标准图层、标准坐标、实体少。
2. 中型 CAD 样本：包含多种实体类型、少量坏几何。
3. 大型 CAD 样本：高图层数、大文件、复杂拓扑。
4. 异常样本：损坏文件、格式不支持、坐标混乱。
5. 低置信度样本：图层命名模糊、端口特征不完整。

### 6.2 ConstraintAgent 测试数据

1. 标准 SiteModel + 标准 CS-001。
2. 包含已知硬约束冲突的 SiteModel。
3. 包含软约束可量化差异的 SiteModel。
4. authority 混合来源约束集。
5. 缺失约束引用、版本错配、未覆盖约束场景。

### 6.3 LayoutAgent 测试数据

1. 可行布局空间充足场景。
2. 可行解稀缺场景。
3. 含重载基础、吊车梁、禁区、障碍物场景。
4. 需要手动拖拽修复的单点违规场景。
5. 上游 Token 失效回传场景。

---

## 7. ParseAgent 功能测试计划

### 7.1 服务能力清单

| 能力编号 | 能力名称 | 业务目标 |
|------|------|------|
| P-01 | CAD 格式识别 | 正确识别 DWG/IFC/STEP/DXF 或明确拒绝 |
| P-02 | 几何实体提取 | 建立可消费的实体集合和空间索引 |
| P-03 | 坐标与单位归一化 | 统一到 WCS 和 mm 口径 |
| P-04 | 几何完整性修补 | 对坏几何做自动修补或降级标记 |
| P-05 | 资产识别与置信度评分 | 识别 Asset 并区分需人工复核对象 |
| P-06 | 语义关系映射 | 生成 Ontology Graph 与 Links |
| P-07 | SiteModel 生成与持久化 | 形成下游可消费的 SiteModel |
| P-08 | 失败降级与人工复核路由 | 不支持格式、低置信度等场景可控处理 |

### 7.2 ParseAgent 正式用例编排

本节开始把 ParseAgent 的测试项从能力清单映射为可执行用例。当前阶段先定义用例编号、前置条件、输入组、验证重点和通过口径，不在本节展开详细操作步骤。

#### 7.2.1 用例分组映射规则

| 用例类型 | 优先使用的输入组 | 说明 |
|------|------|------|
| 格式识别与兼容性 | D. 版本兼容组 | 聚焦 DWG 版本识别和兼容链路 |
| 功能正确性 P0 | A. P0 基线组 + C. 业务语义覆盖组 | 至少同时覆盖真实业务样本和工业语义样本 |
| 性能与资源测试 | B. 规模覆盖组 | 统一比较不同规模输入下的处理表现 |
| 快速回归 | E. 回归最小集 | 控制执行成本 |

#### 7.2.2 P0 用例表

| 用例ID | 能力 | 前置条件 | 输入组 | 验证重点 | 通过口径 |
|------|------|------|------|------|------|
| PT-P0-01 | P-01 | ParseAgent 服务可接收 DWG 文件输入 | G-VER-2000, G-VER-2007, G-VER-2018 | 能正确识别 DWG 版本与格式 | `format_detect` 返回正确版本，不误判、不空值 |
| PT-P0-02 | P-02 | 实体提取模块可读取模型空间实体 | G-P0-BASE-01, G-SEM-02 | 多实体、多区域、多图层对象能被提取 | 输出存在稳定的实体集合，`total_entities_parsed > 0` |
| PT-P0-03 | P-03 | 坐标标准化模块启用，允许记录变换信息 | G-P0-BASE-01 | 真实车间图坐标和单位可归一化 | 输出坐标口径统一，存在变换/归一化记录 |
| PT-P0-04 | P-04 | 几何检查与修补链路启用 | G-P0-BASE-02, G-SEM-03 | 闭合、重叠、自交等几何问题可检查并形成修补结果 | 输出 `geometry_integrity_score`，并记录修补候选或修补结果 |
| PT-P0-05 | P-05 | 资产识别规则和置信度模型可用 | G-P0-BASE-01, G-SEM-01, G-SEM-04 | 设备、区域、墙体等对象可识别并带置信度 | `assets[]` 字段齐全，`avg_confidence` 可计算 |
| PT-P0-06 | P-05 | 人工复核路由可用 | G-SEM-03 | 低置信对象不会被静默当作高置信资产 | 低置信资产写入 `low_confidence_items` 或 `NEED_REVIEW` |
| PT-P0-07 | P-06 | Ontology Link 规则启用 | G-SEM-01, G-SEM-02 | 能生成可被下游消费的关系链接 | 输出 `links[]`，且 link type 合法 |
| PT-P0-08 | P-07 | SiteModel 序列化与持久化链路可用 | G-P0-BASE-01 | 完整解析流程能形成下游可消费对象 | 输出 `site_model_id`、`assets`、`links`、`statistics` |
| PT-P0-09 | P-08 | 警告状态和下游准入标记已定义 | G-P0-BASE-02, G-SEM-03 | 可修复缺陷场景下系统降级而非直接失败 | 状态为 `SUCCESS_WITH_WARNINGS` 或等价可处理状态 |

#### 7.2.3 P1 用例表

| 用例ID | 能力 | 前置条件 | 输入组 | 验证重点 | 通过口径 |
|------|------|------|------|------|------|
| PT-P1-01 | P-06 | 语义关系映射规则完整加载 | G-SEM-01, G-SEM-02, G-SEM-03 | 复杂工业关系可生成并分类 | 可生成 `APPLIES_TO`、`PAIR_WITH`、`TRAVERSES` 等关系 |
| PT-P1-02 | P-02/P-05 | 性能采集指标可用 | G-SIZE-S, G-SIZE-M, G-SIZE-L, G-SIZE-XL | 不同规模下处理时间与资源占用可比较 | 能输出规模差异下的处理指标数据 |
| PT-P1-03 | P-01/P-07 | 快速回归入口可执行 | G-REG-01, G-REG-02, G-REG-03 | 每次改动后能用最小样本快速判断主链路是否被破坏 | 回归集均能完成解析并输出最小 SiteModel 摘要 |

#### 7.2.4 当前阶段不纳入的 ParseAgent 用例

以下用例暂不在当前阶段展开：

1. 基于 DXF 对照文件的 DWG↔DXF 一致性比对。
2. 完整的 IFC/STEP 输入链路验证。
3. 人工标注 Ground Truth 下的识别精度量化评测。

这些内容保留到下一轮专项测试计划中处理。

#### 7.2.5 ParseAgent P0 用例模板

以下模板把 P0 用例进一步落为可执行测试卡片。当前阶段统一采用同一结构：测试目标、输入、前置条件、执行步骤、核心断言、失败判定。

##### PT-P0-01: DWG 格式识别与版本判定

| 项目 | 内容 |
|------|------|
| 用例编号 | PT-P0-01 |
| 对应能力 | P-01 |
| 测试目标 | 验证 ParseAgent 能正确识别 DWG 文件格式和版本 |
| 输入组 | G-VER-2000, G-VER-2007, G-VER-2018 |
| 前置条件 | ParseAgent 可接收文件输入；格式识别模块启用 |
| 执行步骤 | 1. 依次输入 example_2000.dwg、example_2007.dwg、example_2018.dwg。2. 调用格式识别能力。3. 记录返回的 format/version。 |
| 核心断言 | 1. 每个输入都有非空识别结果。2. 版本识别与样本版本一致。3. 不出现跨版本误判。 |
| 失败判定 | 返回空值、返回错误版本、把 DWG 误识别为其他格式，任一即失败 |

##### PT-P0-02: 多实体与多图层实体提取

| 项目 | 内容 |
|------|------|
| 用例编号 | PT-P0-02 |
| 对应能力 | P-02 |
| 测试目标 | 验证 ParseAgent 能从真实工业图中提取稳定实体集合 |
| 输入组 | G-P0-BASE-01, G-SEM-02 |
| 前置条件 | 实体提取链路已启用；允许输出实体统计信息 |
| 执行步骤 | 1. 输入 20180109_机加车间平面布局图.dwg。2. 输入 cold_rolled_steel_production.dwg。3. 执行 entity extract。4. 记录实体总数、图层分布、实体类型分布。 |
| 核心断言 | 1. `total_entities_parsed > 0`。2. 至少存在多图层对象。3. 输出结构可继续被坐标归一化和资产识别消费。 |
| 失败判定 | 无实体输出、输出结构不完整、后续步骤无法消费实体结果，任一即失败 |

##### PT-P0-03: 坐标与单位归一化

| 项目 | 内容 |
|------|------|
| 用例编号 | PT-P0-03 |
| 对应能力 | P-03 |
| 测试目标 | 验证真实车间图能够被统一到 WCS/mm 口径 |
| 输入组 | G-P0-BASE-01 |
| 前置条件 | 坐标标准化模块启用；允许输出变换矩阵或归一化记录 |
| 执行步骤 | 1. 输入 20180109_机加车间平面布局图.dwg。2. 执行 coord normalize。3. 检查输出坐标、单位、变换记录。 |
| 核心断言 | 1. 输出对象坐标口径一致。2. 存在可追踪的归一化记录。3. 归一化结果可进入几何修补和资产识别。 |
| 失败判定 | 坐标单位混乱、无变换记录、归一化后对象不可用，任一即失败 |

##### PT-P0-04: 几何完整性检查与修补

| 项目 | 内容 |
|------|------|
| 用例编号 | PT-P0-04 |
| 对应能力 | P-04 |
| 测试目标 | 验证系统能发现并记录坏几何问题，且可输出修补结果或修补候选 |
| 输入组 | G-P0-BASE-02, G-SEM-03 |
| 前置条件 | 几何检查与修补链路启用；允许输出完整性分数和修补列表 |
| 执行步骤 | 1. 输入 cold_rolled_steel_production.dwg。2. 输入 fish_processing_plant.dwg。3. 执行 geometry check/repair。4. 记录 integrity score、repair candidates、repair result。 |
| 核心断言 | 1. 输出 `geometry_integrity_score`。2. 能发现重复/闭合/自交类问题中的至少一类结果记录。3. 修补结果或待修补候选可追踪。 |
| 失败判定 | 既无完整性分数也无问题记录，或修补后结果不可继续处理，任一即失败 |

##### PT-P0-05: 资产识别与置信度评分

| 项目 | 内容 |
|------|------|
| 用例编号 | PT-P0-05 |
| 对应能力 | P-05 |
| 测试目标 | 验证对象能被识别为资产，并输出完整资产字段和置信度 |
| 输入组 | G-P0-BASE-01, G-SEM-01, G-SEM-04 |
| 前置条件 | 资产识别规则、置信度模型和本体映射规则已加载 |
| 执行步骤 | 1. 输入 20180109_机加车间平面布局图.dwg。2. 输入 woodworking_factory_1.dwg。3. 执行 classify entity。4. 记录资产数、类型、置信度、低置信对象。 |
| 核心断言 | 1. `assets[]` 非空。2. 每个资产包含 guid、type、coords、footprint、confidence。3. 可计算 `avg_confidence`。 |
| 失败判定 | 资产结果为空、资产字段缺失、无置信度输出，任一即失败 |

##### PT-P0-06: 低置信对象人工复核路由

| 项目 | 内容 |
|------|------|
| 用例编号 | PT-P0-06 |
| 对应能力 | P-05 / P-08 |
| 测试目标 | 验证低置信对象不会被误当作高置信资产直接放行 |
| 输入组 | G-SEM-03 |
| 前置条件 | 人工复核阈值已配置；低置信路由机制启用 |
| 执行步骤 | 1. 输入 fish_processing_plant.dwg。2. 执行 classify entity。3. 识别低于阈值的对象。4. 检查输出中的复核标记和低置信列表。 |
| 核心断言 | 1. 低置信对象进入 `low_confidence_items` 或 `NEED_REVIEW`。2. 低置信对象不会被静默并入高可信资产集合。 |
| 失败判定 | 低置信对象未被标记，或被当成正常高置信资产放行，任一即失败 |

##### PT-P0-07: 语义关系链接生成

| 项目 | 内容 |
|------|------|
| 用例编号 | PT-P0-07 |
| 对应能力 | P-06 |
| 测试目标 | 验证 ParseAgent 能输出下游可消费的语义关系链接 |
| 输入组 | G-SEM-01, G-SEM-02 |
| 前置条件 | Ontology link 规则已加载；资产识别已完成 |
| 执行步骤 | 1. 分别对 20180109_机加车间平面布局图.dwg 和 cold_rolled_steel_production.dwg 完成资产识别。2. 执行关系映射。3. 检查 links 输出。 |
| 核心断言 | 1. 输出存在 `links[]`。2. `link_type` 属于允许集合。3. 关系对象可被下游知识图谱或 ConstraintAgent 消费。 |
| 失败判定 | 无关系输出、关系类型非法、关系结果不能序列化，任一即失败 |

##### PT-P0-08: SiteModel 完整生成

| 项目 | 内容 |
|------|------|
| 用例编号 | PT-P0-08 |
| 对应能力 | P-07 |
| 测试目标 | 验证完整解析流程能生成可被 Agent2 消费的 SiteModel |
| 输入组 | G-P0-BASE-01 |
| 前置条件 | ParseAgent 全流程启用；序列化和持久化接口可用 |
| 执行步骤 | 1. 输入 20180109_机加车间平面布局图.dwg。2. 依次执行 format detect、entity extract、normalize、repair、classify、link、serialize。3. 检查最终 SiteModel。 |
| 核心断言 | 1. 输出存在合法 `site_model_id`。2. 包含 `assets`、`links`、`geometry_integrity_score`、`statistics`。3. 输出对象能作为 Agent2 输入。 |
| 失败判定 | SiteModel 缺关键字段、不能序列化、不能被下游消费，任一即失败 |

##### PT-P0-09: 警告态降级放行

| 项目 | 内容 |
|------|------|
| 用例编号 | PT-P0-09 |
| 对应能力 | P-08 |
| 测试目标 | 验证在存在可修复缺陷或低置信对象时，系统能以受控警告态输出，而不是直接中断 |
| 输入组 | G-P0-BASE-02, G-SEM-03 |
| 前置条件 | 支持 `SUCCESS_WITH_WARNINGS` 或等价状态；下游准入规则已定义 |
| 执行步骤 | 1. 输入 cold_rolled_steel_production.dwg 或 fish_processing_plant.dwg。2. 执行完整解析链路。3. 检查状态、警告项、下游可消费标记。 |
| 核心断言 | 1. 存在警告态输出。2. 警告内容可追踪。3. 带警告的结果仍可作为受限输入进入 Agent2。 |
| 失败判定 | 有问题但被标成完全成功，或稍有问题就直接不可恢复失败，任一即失败 |

### 7.3 ParseAgent 输出断言

每次通过类用例至少断言以下输出字段：

1. `site_model_id` 存在且格式合法。
2. `assets[]` 中每个对象包含 `asset_guid`、`type`、`coords`、`footprint`、`confidence`。
3. `links[]` 可被 Ontology 图消费。
4. `statistics.low_confidence_items` 与人工复核路由一致。
5. `mcp_context` 记录步骤、耗时、修补数、低置信资产数。

---

## 8. ConstraintAgent 功能测试计划

### 8.1 服务能力清单

| 能力编号 | 能力名称 | 业务目标 |
|------|------|------|
| C-01 | 约束集加载与版本识别 | 正确读取指定 ConstraintSet 版本 |
| C-02 | 硬/软约束分类与依赖图构建 | 建立可验证的约束图 |
| C-03 | 硬约束求解与冲突识别 | 检出全部硬约束违规 |
| C-04 | 冲突溯源与 reasoning chain 生成 | 违规必须能回溯到文档和权威来源 |
| C-05 | 软约束评分 | 对候选方案给出可比较分值 |
| C-06 | 违规报告生成 | 形成下游 Layout 可消费的诊断结果 |
| C-07 | Authority 与版本审计 | 输出中必须保留来源、版本、审批链 |
| C-08 | 异常降级与覆盖率阻断 | 未覆盖约束或求解失败时可控处理 |

### 8.2 ConstraintAgent 正式用例编排

本节把 ConstraintAgent 的能力映射为正式用例。由于 ConstraintAgent 的输入不是原始 CAD 文件，而是 `SiteModel + ConstraintSet` 组合，因此这里先定义输入包，再定义用例和测试卡片。

#### 8.2.1 输入包定义

| 输入包ID | 组成 | 用途 |
|------|------|------|
| CG-IN-01 | 标准 `SiteModel` + 标准 `CS-001` | 基线正确性测试 |
| CG-IN-02 | 存在已知硬约束违规的 `SiteModel` + 标准 `CS-001` | 硬约束检出测试 |
| CG-IN-03 | 存在多约束交叉冲突的 `SiteModel` + 标准 `CS-001` | 冲突核心识别测试 |
| CG-IN-04 | 软约束差异明显的多个 `SiteModel/LayoutCandidate` + 相同约束集 | 软约束评分与排序测试 |
| CG-IN-05 | authority 混合来源约束集 + 标准 `SiteModel` | 溯源与 authority 审计测试 |
| CG-IN-06 | 约束覆盖不完整或版本错配的 `ConstraintSet` + 标准 `SiteModel` | 覆盖率阻断和降级测试 |

#### 8.2.2 用例分组映射规则

| 用例类型 | 优先使用的输入包 | 说明 |
|------|------|------|
| 基线正确性 | CG-IN-01 | 验证约束加载、分类、正常求解 |
| 硬约束违规检出 | CG-IN-02, CG-IN-03 | 验证违规发现和冲突核心识别 |
| 软约束评分 | CG-IN-04 | 验证评分和排序可用性 |
| 溯源与审计 | CG-IN-05 | 验证 authority、文档来源、版本信息 |
| 降级与阻断 | CG-IN-06 | 验证未覆盖约束、版本错配的阻断行为 |

#### 8.2.3 P0 用例表

| 用例ID | 能力 | 前置条件 | 输入包 | 验证重点 | 通过口径 |
|------|------|------|------|------|------|
| CT-P0-01 | C-01 | ConstraintStore 可访问；约束版本元数据可读 | CG-IN-01 | 指定 `CS-001` 可被正确加载和识别版本 | 返回约束集 ID、版本、数量、authority refs |
| CT-P0-02 | C-02 | 约束分类规则可用 | CG-IN-01 | Hard/Soft 分类准确，依赖图可构建 | 输出 hard/soft 分类结果和依赖关系结构 |
| CT-P0-03 | C-03 | Z3 编码与求解链路可用 | CG-IN-01 | SAT 场景不误报违规 | `hard_violation_count = 0` 或等价 SAT 结果 |
| CT-P0-04 | C-03 | 违规检出规则和求解链路可用 | CG-IN-02 | 已知硬约束违规能被检出 | 输出违规对象、约束 ID、违规类型 |
| CT-P0-05 | C-03 | 冲突分析能力可用 | CG-IN-03 | 多约束交叉冲突时能提取核心冲突子集 | 输出冲突核心，不只是笼统 UNSAT |
| CT-P0-06 | C-04 | 约束文档来源和 authority 已入库 | CG-IN-05 | 每条违规都可回溯到文档和权威来源 | `constraint_id`、source、authority 字段完整 |
| CT-P0-07 | C-06 | 违规报告生成链路可用 | CG-IN-02, CG-IN-03 | 违规报告能被 LayoutAgent 直接消费 | 输出 `Violations + Reasoning Chain` 结构完整 |
| CT-P0-08 | C-08 | 覆盖率检查与阻断规则已配置 | CG-IN-06 | 覆盖不足或版本错配时触发阻断而非静默通过 | 返回阻断/人工复核结果 |

#### 8.2.4 P1 用例表

| 用例ID | 能力 | 前置条件 | 输入包 | 验证重点 | 通过口径 |
|------|------|------|------|------|------|
| CT-P1-01 | C-05 | 软约束评分规则和权重已配置 | CG-IN-04 | 不同候选可输出可比较的软约束得分 | `Soft Scores` 完整且可排序 |
| CT-P1-02 | C-07 | 审计字段和版本信息可持久化 | CG-IN-05 | 输出中保留版本、authority、来源文档 | 审计字段完整可查询 |
| CT-P1-03 | C-06/C-07 | 推理链和报告导出接口可用 | CG-IN-02, CG-IN-05 | 报告结果能用于 PDF/审批导出 | `Reasoning Chain` 可序列化且字段完整 |

#### 8.2.5 ConstraintAgent P0 用例模板

##### CT-P0-01: 约束集加载与版本识别

| 项目 | 内容 |
|------|------|
| 用例编号 | CT-P0-01 |
| 对应能力 | C-01 |
| 测试目标 | 验证 ConstraintAgent 能正确加载指定 `CS-001` 及其版本元数据 |
| 输入包 | CG-IN-01 |
| 前置条件 | ConstraintStore 可访问；`CS-001` 已入库 |
| 执行步骤 | 1. 提供标准 `SiteModel`。2. 指定 `constraint_set_id = CS-001`。3. 执行约束集加载。4. 记录版本、约束数、authority refs。 |
| 核心断言 | 1. 返回约束集 ID 正确。2. 存在版本号。3. 返回 hard/soft 数量和 authority 来源。 |
| 失败判定 | 加载失败、版本为空、约束数量异常或 authority 缺失，任一即失败 |

##### CT-P0-02: 硬软约束分类与依赖图构建

| 项目 | 内容 |
|------|------|
| 用例编号 | CT-P0-02 |
| 对应能力 | C-02 |
| 测试目标 | 验证约束能被正确分为 Hard/Soft，且可形成依赖图 |
| 输入包 | CG-IN-01 |
| 前置条件 | 分类规则与依赖图构建逻辑已启用 |
| 执行步骤 | 1. 加载标准 `SiteModel + CS-001`。2. 执行约束分类。3. 构建 constraint graph。4. 检查约束类型和依赖关系。 |
| 核心断言 | 1. Hard/Soft 分类结果非空。2. 依赖图可输出节点和边。3. 依赖图结构能支持后续违规分析。 |
| 失败判定 | 分类错误、依赖图为空或结构不可用，任一即失败 |

##### CT-P0-03: SAT 正常场景求解

| 项目 | 内容 |
|------|------|
| 用例编号 | CT-P0-03 |
| 对应能力 | C-03 |
| 测试目标 | 验证在满足全部硬约束时，系统不会误报违规 |
| 输入包 | CG-IN-01 |
| 前置条件 | Z3 编码和求解器调用正常 |
| 执行步骤 | 1. 输入标准 `SiteModel + CS-001`。2. 编码约束为求解问题。3. 执行 solve。4. 记录 SAT/UNSAT 结果和违规列表。 |
| 核心断言 | 1. 返回 SAT 或等价“无硬违规”结果。2. `Violations` 为空或 `hard_violation_count = 0`。 |
| 失败判定 | 满足约束场景被误判为违规，或输出与 SAT 结果矛盾，任一即失败 |

##### CT-P0-04: 已知硬约束违规检出

| 项目 | 内容 |
|------|------|
| 用例编号 | CT-P0-04 |
| 对应能力 | C-03 |
| 测试目标 | 验证已知违规场景中的硬约束会被完整检出 |
| 输入包 | CG-IN-02 |
| 前置条件 | 已知违规样本及对应约束 Ground Truth 已准备 |
| 执行步骤 | 1. 输入存在已知硬违规的 `SiteModel`。2. 加载标准 `CS-001`。3. 执行求解。4. 检查违规输出。 |
| 核心断言 | 1. 输出非空 `Violations`。2. 每条违规关联具体 `constraint_id` 和对象。3. 违规类型与预置场景相符。 |
| 失败判定 | 已知违规未检出、检出对象错误、违规记录不可定位，任一即失败 |

##### CT-P0-05: 多约束交叉冲突核心识别

| 项目 | 内容 |
|------|------|
| 用例编号 | CT-P0-05 |
| 对应能力 | C-03 |
| 测试目标 | 验证多个约束交叉冲突时，系统能识别核心冲突子集 |
| 输入包 | CG-IN-03 |
| 前置条件 | UNSAT core 或等价冲突核心提取逻辑已启用 |
| 执行步骤 | 1. 输入交叉冲突样本。2. 执行求解和冲突分析。3. 记录 UNSAT core 或核心冲突集合。 |
| 核心断言 | 1. 输出核心冲突集合。2. 集合规模小于或等于全部违规约束集合。3. 可用于后续改进建议。 |
| 失败判定 | 只返回笼统失败、不返回冲突核心、返回结果不可解释，任一即失败 |

##### CT-P0-06: 违规溯源与 authority 校验

| 项目 | 内容 |
|------|------|
| 用例编号 | CT-P0-06 |
| 对应能力 | C-04 |
| 测试目标 | 验证每条违规都能回溯到文档来源和 authority |
| 输入包 | CG-IN-05 |
| 前置条件 | 约束集已关联 source document 和 authority level |
| 执行步骤 | 1. 输入带多来源 authority 的约束集。2. 执行验证。3. 抽取违规报告中的 source 和 authority 字段。 |
| 核心断言 | 1. 每条违规包含 `constraint_id`。2. 存在来源文档、章节或等价溯源字段。3. 存在 authority 信息。 |
| 失败判定 | 违规不可追溯、authority 缺失、来源字段不完整，任一即失败 |

##### CT-P0-07: 违规报告生成与下游可消费性

| 项目 | 内容 |
|------|------|
| 用例编号 | CT-P0-07 |
| 对应能力 | C-06 |
| 测试目标 | 验证约束检查结果能形成 LayoutAgent 可消费的标准输出 |
| 输入包 | CG-IN-02, CG-IN-03 |
| 前置条件 | 违规报告和 reasoning chain 生成逻辑可用 |
| 执行步骤 | 1. 分别输入单违规和多冲突场景。2. 执行完整约束检查流程。3. 检查最终报告结构。 |
| 核心断言 | 1. 输出包含 `Violations`。2. 输出包含 `Reasoning Chain`。3. 结构可被 LayoutAgent 消费而无需人工补充字段。 |
| 失败判定 | 报告字段残缺、无推理链、下游无法消费，任一即失败 |

##### CT-P0-08: 覆盖率不足与版本错配阻断

| 项目 | 内容 |
|------|------|
| 用例编号 | CT-P0-08 |
| 对应能力 | C-08 |
| 测试目标 | 验证未覆盖硬约束、约束版本错配等场景会触发阻断或人工复核 |
| 输入包 | CG-IN-06 |
| 前置条件 | 覆盖率阈值、版本一致性规则、人工复核路由已配置 |
| 执行步骤 | 1. 输入标准 `SiteModel`。2. 加载覆盖不完整或版本错配的 `ConstraintSet`。3. 执行完整校验。4. 检查状态和阻断信息。 |
| 核心断言 | 1. 不会被静默标记为通过。2. 返回阻断原因或人工复核标记。3. 下游 Layout 不应被继续触发。 |
| 失败判定 | 覆盖不足仍标记通过、版本错配未告警、下游未被阻断，任一即失败 |

### 8.3 ConstraintAgent 输出断言

每次通过类用例至少断言以下内容：

1. `Violations` 中每条记录可定位到具体约束与对象。
2. `Soft Scores` 可直接被 Layout 方案排序消费。
3. `Reasoning Chain` 可用于 PDF 审批和审计导出。
4. `mcp_context` 中记录约束版本、求解耗时、覆盖率、来源文档集合。
5. 任何“未覆盖硬约束”都不能被标记为通过。

---

## 9. LayoutAgent 功能测试计划

### 9.1 服务能力清单

| 能力编号 | 能力名称 | 业务目标 |
|------|------|------|
| L-01 | 布局会话启动与上游 Token 校验 | 基于有效 Gate A/B 启动布局流程 |
| L-02 | 候选方案自动生成 | 产出足量可行布局候选 |
| L-03 | 实时硬约束验证 | 拖拽或改坐标时即时发现违规 |
| L-04 | 吊运路径干涉检测 | 保证吊装路径安全与净高合规 |
| L-05 | 方案对比与推荐 | 支持量化比较与推荐方案标记 |
| L-06 | Gate C 锁版 | 只有完全合规方案才能生成锁版 Token |
| L-07 | 上游失效联动 | 上游变更必须使相关布局失效 |
| L-08 | 审计与状态控制 | 锁版后不可直接改写，变更必须新版本 |

### 9.2 LayoutAgent 正式用例编排

本节把 LayoutAgent 的能力转换成正式用例。LayoutAgent 的输入不是单一对象，而是由 `SiteModel`、Constraint 结果、候选方案状态、上游 Token、吊运检测结果共同组成，因此先定义输入包。

#### 9.2.1 输入包定义

| 输入包ID | 组成 | 用途 |
|------|------|------|
| LG-IN-01 | 有效 Gate A/B Token + 标准 `SiteModel` + 标准 Constraint 结果 | 布局会话启动与基线生成 |
| LG-IN-02 | 可行空间充足的 `SiteModel` + 无硬违规约束结果 | 候选方案自动生成 |
| LG-IN-03 | 可行空间不足或搜索空间受限的 `SiteModel` + 约束结果 | 候选不足和降级提示 |
| LG-IN-04 | 单点可控硬违规的 `LayoutCandidate` | 实时验证与修复 |
| LG-IN-05 | 含 `CraneRunway`、障碍物、高度属性的 `LayoutCandidate` | 吊运路径干涉检测 |
| LG-IN-06 | 多个候选方案及评分结果 | 对比、推荐和排序 |
| LG-IN-07 | 满足 Gate C 条件的 `LayoutCandidate` + 上游 Token | 锁版与 Token 生成 |
| LG-IN-08 | 上游 Token 失效事件 + 已生成布局方案 | 失效联动和状态切换 |

#### 9.2.2 用例分组映射规则

| 用例类型 | 优先使用的输入包 | 说明 |
|------|------|------|
| 会话与上游校验 | LG-IN-01, LG-IN-08 | 验证 Gate A/B 和失效传播 |
| 候选生成 | LG-IN-02, LG-IN-03 | 验证可行解生成和降级提示 |
| 实时验证 | LG-IN-04 | 验证硬约束实时反馈与修复 |
| 吊运检测 | LG-IN-05 | 验证干涉检测和净高检查 |
| 方案对比与锁版 | LG-IN-06, LG-IN-07 | 验证对比、推荐、Gate C 锁版 |

#### 9.2.3 P0 用例表

| 用例ID | 能力 | 前置条件 | 输入包 | 验证重点 | 通过口径 |
|------|------|------|------|------|------|
| LT-P0-01 | L-01 | Gate A/B 校验逻辑可用 | LG-IN-01 | 有效 Token 下可成功创建布局会话 | 返回 `session_id`、`layout_id`、`mcp_context_id` |
| LT-P0-02 | L-01 | Token 失效检测逻辑可用 | LG-IN-08 | 任一上游 Token 失效时禁止启动会话 | 返回明确错误并阻断 |
| LT-P0-03 | L-02 | 候选生成器和约束消费链路可用 | LG-IN-02 | 可生成不少于 20 个且无硬违规的候选 | 候选数 `>= 20`，每个 `hard_violation_count = 0` |
| LT-P0-04 | L-02 | 降级提示逻辑可用 | LG-IN-03 | 无法生成足量候选时给出可解释提示 | 返回候选不足信息和建议放宽软约束 |
| LT-P0-05 | L-03 | 实时验证链路与画布更新逻辑可用 | LG-IN-04 | 单点硬违规能被实时发现并展示 | 在时限内返回违规和溯源信息 |
| LT-P0-06 | L-03 | 违规修复更新逻辑可用 | LG-IN-04 | 违规修复后能实时清零并解除高亮 | `hard_violation_count` 归零且状态更新 |
| LT-P0-07 | L-04 | 吊运检测引擎可用 | LG-IN-05 | 能输出干涉路径和净高余量 | 返回干涉结果、净高、检测版本 hash |
| LT-P0-08 | L-04 | 检测失败阻断逻辑可用 | LG-IN-05 | 吊运检测失败时不得锁版 | `crane_check_done = false` 且 Gate C 被阻断 |
| LT-P0-09 | L-06 | Gate C 条件检查和审批链可用 | LG-IN-07 | 满足条件时能生成 `LAYOUT_LOCK` Token | Token 生成成功，状态变为 `LOCKED` |
| LT-P0-10 | L-06 | Gate C 阻断规则可用 | LG-IN-04, LG-IN-05 | 有硬违规或未检测时禁止锁版 | 返回阻断原因，不生成 Token |
| LT-P0-11 | L-07 | 失效联动逻辑可用 | LG-IN-08 | 上游更新能使布局方案与 Token 失效 | 状态变为 `SUPERSEDED`，Token 失效 |

#### 9.2.4 P1 用例表

| 用例ID | 能力 | 前置条件 | 输入包 | 验证重点 | 通过口径 |
|------|------|------|------|------|------|
| LT-P1-01 | L-05 | 多方案对比视图可用 | LG-IN-06 | 支持排序、筛选、并排对比 | 指标展示完整可操作 |
| LT-P1-02 | L-05 | 推荐方案标记逻辑可用 | LG-IN-06 | 用户可标记推荐方案并记录操作人 | `is_recommended` 与审计字段正确 |
| LT-P1-03 | L-08 | 版本控制与 object hash 机制可用 | LG-IN-07 | 锁版后修改必须生成新版本 | 原版本不可直接修改，hash 变化可追踪 |

#### 9.2.5 LayoutAgent P0 用例模板

##### LT-P0-01: 布局会话启动与 Gate A/B 校验

| 项目 | 内容 |
|------|------|
| 用例编号 | LT-P0-01 |
| 对应能力 | L-01 |
| 测试目标 | 验证在 Gate A/B 有效时可成功启动布局会话 |
| 输入包 | LG-IN-01 |
| 前置条件 | Gate A/B Token 校验服务可用；标准 `SiteModel` 和 Constraint 结果已准备 |
| 执行步骤 | 1. 提供有效 `site_model_token_id` 与 `constraint_set_token_id`。2. 调用布局会话创建接口。3. 记录返回的会话和上下文字段。 |
| 核心断言 | 1. 会话创建成功。2. 返回 `session_id`、`layout_id`、`mcp_context_id`。3. 会话头部可关联上游 Token 摘要。 |
| 失败判定 | Token 有效却无法创建会话，或返回字段缺失，任一即失败 |

##### LT-P0-02: 上游 Token 失效阻断

| 项目 | 内容 |
|------|------|
| 用例编号 | LT-P0-02 |
| 对应能力 | L-01 |
| 测试目标 | 验证任一上游 Token 失效时，布局会话会被阻断 |
| 输入包 | LG-IN-08 |
| 前置条件 | Token 失效检测逻辑和错误码映射已启用 |
| 执行步骤 | 1. 构造 SiteModel 或 ConstraintSet Token 失效场景。2. 调用布局会话创建。3. 检查错误码和阻断提示。 |
| 核心断言 | 1. 不创建新会话。2. 返回明确失效原因。3. 不允许绕过继续布局。 |
| 失败判定 | Token 失效仍能创建会话，或提示含糊不清，任一即失败 |

##### LT-P0-03: 候选方案自动生成

| 项目 | 内容 |
|------|------|
| 用例编号 | LT-P0-03 |
| 对应能力 | L-02 |
| 测试目标 | 验证可行空间充足时系统能自动生成足量候选 |
| 输入包 | LG-IN-02 |
| 前置条件 | 候选生成器、约束消费和评分链路均可用 |
| 执行步骤 | 1. 输入可行空间充足场景。2. 调用 `generateLayoutCandidates()`。3. 记录候选数量和每个候选的关键指标。 |
| 核心断言 | 1. 候选数不少于 20。2. 每个候选 `hard_violation_count = 0`。3. 每个候选存在 `soft_violation_score` 和 `object_hash`。 |
| 失败判定 | 候选数不足、出现硬违规候选、缺关键字段，任一即失败 |

##### LT-P0-04: 候选不足时的可解释降级

| 项目 | 内容 |
|------|------|
| 用例编号 | LT-P0-04 |
| 对应能力 | L-02 |
| 测试目标 | 验证可行空间不足时系统能返回可解释降级结果 |
| 输入包 | LG-IN-03 |
| 前置条件 | 候选生成失败分支和建议提示逻辑已配置 |
| 执行步骤 | 1. 输入可行空间不足场景。2. 调用候选生成。3. 检查返回候选数和建议信息。 |
| 核心断言 | 1. 系统不会静默失败。2. 返回候选不足说明。3. 返回“建议放宽软约束”或等价提示。 |
| 失败判定 | 直接超时无结果、候选不足但无解释、错误归因不清，任一即失败 |

##### LT-P0-05: 实时硬约束验证

| 项目 | 内容 |
|------|------|
| 用例编号 | LT-P0-05 |
| 对应能力 | L-03 |
| 测试目标 | 验证拖拽或坐标修改时，系统能实时发现硬违规 |
| 输入包 | LG-IN-04 |
| 前置条件 | 实时验证链路启用；溯源信息可返回 |
| 执行步骤 | 1. 构造一个单点可控硬违规候选。2. 触发拖拽或坐标更新。3. 检查违规反馈与延迟。 |
| 核心断言 | 1. 在阈值时间内返回违规。2. 返回 `constraint_id` 和来源溯源。3. 高亮和计数同步更新。 |
| 失败判定 | 违规迟迟不返回、无溯源、UI/状态不同步，任一即失败 |

##### LT-P0-06: 违规修复后的状态回收

| 项目 | 内容 |
|------|------|
| 用例编号 | LT-P0-06 |
| 对应能力 | L-03 |
| 测试目标 | 验证违规修复后系统能及时解除高亮并恢复合规状态 |
| 输入包 | LG-IN-04 |
| 前置条件 | 违规修复反馈逻辑可用 |
| 执行步骤 | 1. 在已触发违规的候选上回退到合法位置。2. 再次触发校验。3. 检查计数和高亮状态。 |
| 核心断言 | 1. `hard_violation_count` 归零。2. 高亮消除。3. 候选恢复可继续使用状态。 |
| 失败判定 | 违规已修复但状态未恢复，或高亮残留，任一即失败 |

##### LT-P0-07: 吊运路径干涉检测

| 项目 | 内容 |
|------|------|
| 用例编号 | LT-P0-07 |
| 对应能力 | L-04 |
| 测试目标 | 验证系统能执行吊运路径干涉检测并输出关键结果 |
| 输入包 | LG-IN-05 |
| 前置条件 | `CraneRunway`、障碍物和高度属性已准备；检测引擎可用 |
| 执行步骤 | 1. 输入包含吊车梁与障碍物的候选方案。2. 执行吊运检测。3. 检查干涉路径和净高余量输出。 |
| 核心断言 | 1. 输出干涉路径列表。2. 每条路径可看到净高余量。3. 记录检测版本 hash。 |
| 失败判定 | 无检测结果、结果缺净高字段、无版本记录，任一即失败 |

##### LT-P0-08: 吊运检测失败阻断锁版

| 项目 | 内容 |
|------|------|
| 用例编号 | LT-P0-08 |
| 对应能力 | L-04 |
| 测试目标 | 验证吊运检测失败时系统不能继续 Gate C 锁版 |
| 输入包 | LG-IN-05 |
| 前置条件 | `crane_check_done` 状态和 Gate C 阻断逻辑已启用 |
| 执行步骤 | 1. 构造吊运检测失败或异常场景。2. 检查检测状态。3. 尝试提交锁版申请。 |
| 核心断言 | 1. `crane_check_done = false`。2. Gate C 申请被阻断。3. 返回检测失败原因。 |
| 失败判定 | 检测失败仍可锁版，或失败原因不可见，任一即失败 |

##### LT-P0-09: Gate C 锁版成功

| 项目 | 内容 |
|------|------|
| 用例编号 | LT-P0-09 |
| 对应能力 | L-06 |
| 测试目标 | 验证满足 Gate C 条件时可成功生成 `LAYOUT_LOCK` Token |
| 输入包 | LG-IN-07 |
| 前置条件 | Gate C 条件检查、审批工作流、Token 生成服务可用 |
| 执行步骤 | 1. 输入满足全部条件的候选方案。2. 提交锁版申请。3. 完成审批。4. 检查 Token 和布局状态。 |
| 核心断言 | 1. 成功生成 `LAYOUT_LOCK` Token。2. 布局状态变为 `LOCKED`。3. Token 引用上游 Token 与布局 hash。 |
| 失败判定 | 条件满足却无法生成 Token、状态未更新、Token 缺关键信息，任一即失败 |

##### LT-P0-10: Gate C 阻断规则校验

| 项目 | 内容 |
|------|------|
| 用例编号 | LT-P0-10 |
| 对应能力 | L-06 |
| 测试目标 | 验证存在硬违规或缺失吊运检测时，会被 Gate C 阻断 |
| 输入包 | LG-IN-04, LG-IN-05 |
| 前置条件 | Gate C 阻断条件已配置 |
| 执行步骤 | 1. 准备存在硬违规的候选。2. 准备未完成吊运检测的候选。3. 分别提交锁版申请。 |
| 核心断言 | 1. 两类场景均被阻断。2. 返回具体阻断条件。3. 不生成 Token。 |
| 失败判定 | 不合规候选仍生成 Token，或阻断原因不明确，任一即失败 |

##### LT-P0-11: 上游失效联动

| 项目 | 内容 |
|------|------|
| 用例编号 | LT-P0-11 |
| 对应能力 | L-07 |
| 测试目标 | 验证上游 SiteModel/ConstraintSet 更新后，相关布局和 Token 自动失效 |
| 输入包 | LG-IN-08 |
| 前置条件 | `invalidateDownstream` 或等价失效传播机制已启用 |
| 执行步骤 | 1. 准备已锁版布局方案。2. 触发上游 Token 失效事件。3. 检查布局状态、Token 状态和通知结果。 |
| 核心断言 | 1. 布局状态切换为 `SUPERSEDED`。2. 已有 `LAYOUT_LOCK` Token 失效。3. 失效事件被记录和通知。 |
| 失败判定 | 上游更新后下游仍保持有效，或无审计/通知记录，任一即失败 |

### 9.3 LayoutAgent 输出断言

每次通过类用例至少断言以下内容：

1. `LayoutCandidate` 包含 `layout_id`、`object_hash`、`hard_violation_count`、`soft_violation_score`、`space_utilization_rate`。
2. `crane_check_done` 和检测版本 hash 可追踪。
3. Gate C Token 中引用上游 Gate A/B Token。
4. 布局状态只能按 `DRAFT -> VALIDATED -> LOCKED -> SUPERSEDED` 等规则流转。
5. 任意字段变更会触发新的 `object_hash`。

---

## 10. Orchestrator 与闭环测试计划

### 10.1 闭环服务能力

| 能力编号 | 能力名称 | 业务目标 |
|------|------|------|
| O-01 | Agent 链路编排 | Agent1 输出可自动触发 Agent2，再触发 Agent3 |
| O-02 | mcp_context 贯通 | 全链路可回溯 |
| O-03 | 重试与超时控制 | 单 Agent 异常时行为可预期 |
| O-04 | 失败阻断与人工介入 | 不合规结果不得继续下游 |
| O-05 | 审计归档 | 闭环结果可导出审批和追责证据 |

### 10.2 Orchestrator 与闭环正式用例编排

#### 10.2.1 输入包定义

| 输入包ID | 组成 | 用途 |
|------|------|------|
| OG-IN-01 | 标准 CAD 输入 + 正常三 Agent 服务 | 标准闭环执行 |
| OG-IN-02 | ParseAgent 输出警告态 `SUCCESS_WITH_WARNINGS` | 风险标记透传 |
| OG-IN-03 | ConstraintAgent 输出硬违规结果 | 下游阻断验证 |
| OG-IN-04 | 满足 Gate C 的完整闭环结果 | 锁版与审计验证 |
| OG-IN-05 | 单 Agent 超时或重试场景 | 超时、重试、脏状态验证 |
| OG-IN-06 | 完整 mcp_context 链 | 回溯查询验证 |
| OG-IN-07 | 上游 Token 重新锁版或失效事件 | 下游失效传播验证 |

#### 10.2.2 用例分组映射规则

| 用例类型 | 优先使用的输入包 | 说明 |
|------|------|------|
| 标准闭环 | OG-IN-01, OG-IN-04 | 验证 Parse→Constraint→Layout 主链路 |
| 风险透传 | OG-IN-02, OG-IN-03 | 验证 warning 和 hard violation 不会丢失 |
| 韧性与恢复 | OG-IN-05 | 验证超时、重试和状态一致性 |
| 追溯与失效传播 | OG-IN-06, OG-IN-07 | 验证 context 和 invalidateDownstream |

#### 10.2.3 P0 用例表

| 用例ID | 场景 | 前置条件 | 输入包 | 验证重点 | 通过口径 |
|------|------|------|------|------|------|
| OT-P0-01 | CAD 导入后自动触发 Parse→Constraint→Layout | Orchestrator、三 Agent、消息通道可用 | OG-IN-01 | 链路按顺序执行，状态机正确流转 | 每步都被触发且状态流转正确 |
| OT-P0-02 | ParseAgent `SUCCESS_WITH_WARNINGS` 透传 | warning 状态和风险标记定义完成 | OG-IN-02 | warning 不丢失并进入 Agent2 | Agent2 能看到并保留风险标记 |
| OT-P0-03 | ConstraintAgent 输出存在硬违规 | 下游阻断规则已配置 | OG-IN-03 | Layout 候选不能被锁版 | 不进入 Gate C 成功态 |
| OT-P0-04 | Layout 生成后满足 Gate C | Gate C、审批、审计归档可用 | OG-IN-04 | 成功生成 `LAYOUT_LOCK`，审计完整 | Token 生成且审计记录完整 |
| OT-P0-05 | mcp_context 回溯查询 | context 存储与查询接口可用 | OG-IN-06 | 能完整查看父子链和步骤摘要 | context 链无断点、顺序正确 |
| OT-P0-06 | 上游重新锁版导致下游失效 | 失效传播机制可用 | OG-IN-07 | 失效事件传播至布局与审计系统 | 下游状态失效、通知和审计完整 |

#### 10.2.4 P1 用例表

| 用例ID | 场景 | 前置条件 | 输入包 | 验证重点 | 通过口径 |
|------|------|------|------|------|------|
| OT-P1-01 | 任一 Agent 超时 | 重试策略和超时阈值已配置 | OG-IN-05 | 重试符合预期且不产生脏状态 | 重试次数、最终状态与策略一致 |

#### 10.2.5 闭环 P0 用例模板

##### OT-P0-01: 标准闭环编排

| 项目 | 内容 |
|------|------|
| 用例编号 | OT-P0-01 |
| 对应能力 | O-01 |
| 测试目标 | 验证 CAD 输入后系统会按顺序触发 Parse、Constraint、Layout |
| 输入包 | OG-IN-01 |
| 前置条件 | 三 Agent 服务可用；Orchestrator 路由已配置 |
| 执行步骤 | 1. 输入标准 CAD。2. 触发 Orchestrator。3. 观察 Agent1、2、3 的调用顺序和状态机变化。 |
| 核心断言 | 1. 三个 Agent 按顺序执行。2. 上一步输出成为下一步输入。3. 状态机无跳步、无回退异常。 |
| 失败判定 | 调用顺序错误、状态错乱、上游输出未被下游消费，任一即失败 |

##### OT-P0-02: Warning 风险标记透传

| 项目 | 内容 |
|------|------|
| 用例编号 | OT-P0-02 |
| 对应能力 | O-04 |
| 测试目标 | 验证 ParseAgent 的 warning 结果不会在链路中丢失 |
| 输入包 | OG-IN-02 |
| 前置条件 | warning 字段和风控标识已定义 |
| 执行步骤 | 1. 让 ParseAgent 输出 `SUCCESS_WITH_WARNINGS`。2. 继续触发 Agent2。3. 检查 Agent2 输入与审计信息。 |
| 核心断言 | 1. warning 被保留。2. Agent2 能识别风险标记。3. 审计链中可看到该 warning。 |
| 失败判定 | warning 在链路中丢失或被误当作完全成功，任一即失败 |

##### OT-P0-03: 硬违规阻断下游锁版

| 项目 | 内容 |
|------|------|
| 用例编号 | OT-P0-03 |
| 对应能力 | O-04 |
| 测试目标 | 验证 ConstraintAgent 检出硬违规后，不会进入成功锁版路径 |
| 输入包 | OG-IN-03 |
| 前置条件 | Layout 下游阻断规则已配置 |
| 执行步骤 | 1. 输入会触发硬违规的闭环场景。2. 执行到 ConstraintAgent。3. 观察 Layout 和 Gate C 行为。 |
| 核心断言 | 1. Layout 不会生成可锁版结果。2. Gate C 不会成功。3. 阻断原因可追踪。 |
| 失败判定 | 硬违规结果仍进入锁版成功路径，任一即失败 |

##### OT-P0-04: Gate C 成功与审计归档

| 项目 | 内容 |
|------|------|
| 用例编号 | OT-P0-04 |
| 对应能力 | O-05 |
| 测试目标 | 验证满足条件的闭环结果能生成 `LAYOUT_LOCK` 并完成审计归档 |
| 输入包 | OG-IN-04 |
| 前置条件 | Gate C、审批流、AuditStore 可用 |
| 执行步骤 | 1. 执行完整闭环直到 Layout 合规。2. 提交 Gate C。3. 完成审批并查询审计记录。 |
| 核心断言 | 1. 成功生成 `LAYOUT_LOCK`。2. 审计包含关键 `mcp_context_id` 和决策结果。3. 下游可消费该 Token。 |
| 失败判定 | Token 成功但无审计，或审计字段不完整，任一即失败 |

##### OT-P0-05: mcp_context 全链路回溯

| 项目 | 内容 |
|------|------|
| 用例编号 | OT-P0-05 |
| 对应能力 | O-02 |
| 测试目标 | 验证系统可按父子关系完整回溯整条 Agent 链 |
| 输入包 | OG-IN-06 |
| 前置条件 | mcp_context 持久化和查询接口可用 |
| 执行步骤 | 1. 执行一条标准闭环。2. 从最终 context_id 反向查询链路。3. 检查父子关系和步骤摘要。 |
| 核心断言 | 1. context 链完整。2. 顺序正确。3. 每一步包含时间、状态、摘要。 |
| 失败判定 | context 断链、顺序错误、步骤摘要缺失，任一即失败 |

##### OT-P0-06: 上游失效传播到下游

| 项目 | 内容 |
|------|------|
| 用例编号 | OT-P0-06 |
| 对应能力 | O-04 / O-05 |
| 测试目标 | 验证上游重新锁版或失效事件会传播到布局结果和审计系统 |
| 输入包 | OG-IN-07 |
| 前置条件 | `invalidateDownstream` 和通知机制已启用 |
| 执行步骤 | 1. 准备已完成闭环且已锁版的结果。2. 触发上游失效事件。3. 查询布局状态、Token 状态、审计日志和通知。 |
| 核心断言 | 1. 下游布局进入失效状态。2. Token 失效。3. 审计和通知同时存在。 |
| 失败判定 | 上游失效不影响下游，或仅部分系统感知失效，任一即失败 |

---

## 11. 测试执行优先级

### 11.1 P0 必测集

P0 用于判断系统是否具备最小交付能力，必须覆盖：

1. ParseAgent 完整输入输出契约。
2. ConstraintAgent 硬约束检出与违规溯源。
3. LayoutAgent 候选生成、实时验证、吊运检测、Gate C 锁版。
4. Orchestrator 的 mcp_context 链路与失效传播。

### 11.2 P1 增强集

P1 用于提高系统可运维性和可决策性：

1. 多候选对比与推荐逻辑。
2. 锁版后版本管理。
3. 性能压测、并发测试、长链路重试。
4. 审计导出和 PDF reasoning chain 完整性。

---

## 12. 通过准则

### 12.1 Agent 级通过准则

| Agent | 通过条件 |
|------|------|
| **ParseAgent** | 能输出可消费的 `SiteModel`，低置信与坏几何场景处理可控 |
| **ConstraintAgent** | 能 100% 检出测试集中的硬约束违规，并输出可追溯违规报告 |
| **LayoutAgent** | 能产出可比较候选，且仅在 Gate C 条件满足时锁版 |

### 12.2 系统级通过准则

1. 端到端闭环可以从 CAD 输入走到 `LAYOUT_LOCK`。
2. 全链路 `mcp_context` 完整，无断链。
3. 上游对象变化能触发下游失效。
4. 任一关键失败场景都不会产生“看似成功、实际不可用”的输出。

---

## 13. 与现有 Step5.2 的关系

本计划不是替代技术 Spike，而是覆盖其上层：

1. [PRD/step5.2-关键技术验证计划.md](../PRD/step5.2-关键技术验证计划.md) 继续保留，回答“底层技术可不可行”。
2. 本计划回答“Agent 能不能交付业务能力”。
3. 建议后续把 Step5.2 的测试资产重新挂接到本计划的能力项下，例如：
   - Spike-1 挂到 ParseAgent 的 P-01/P-02/P-03。
   - Spike-2 挂到 Orchestrator 的 O-02。
   - Spike-3 挂到 LayoutAgent 的 L-04。

---

## 14. 推荐落地顺序

1. 先建立 Agent 能力测试目录，而不是继续按 Spike 目录扩展。
2. 先做 P0 功能测试资产，再补专项性能与技术验证。
3. 先把“输出契约 + Gate 条件 + 审计链路”测通，再追求算法最优。
4. 每个功能测试用例必须绑定一个明确的输出断言，避免只测 NotImplementedError 或空壳返回。

---

## 15. TDD 下一步建议

### 15.1 共识

下一步应当进入“编写功能测试用例”阶段，而不是继续扩写测试计划文档。

但如果采用测试驱动开发，最合适的做法不是同时铺开全部 Agent 的测试，而是先选择一条最小 P0 功能链路，写出第一批可执行的红灯测试，再围绕这批测试逐步实现。

### 15.2 我对下一步的挑战

如果下一步直接大面积编写全部功能测试文件，风险有三个：

1. 很容易写成大量结构正确、但没有真实断言价值的占位测试。
2. 由于上游实体模型、约束样本、候选方案样本尚未完全固化，测试会频繁返工。
3. 一次铺开 ParseAgent、ConstraintAgent、LayoutAgent，会让 TDD 失去“最小反馈回路”的优势。

所以我建议的下一步不是“写所有功能测试”，而是“先写最小闭环的第一批功能测试”。

### 15.3 推荐的 TDD 执行顺序

#### 阶段 A：先写 ParseAgent 的第一批红灯测试

优先级建议：

1. PT-P0-01：DWG 格式识别与版本判定
2. PT-P0-02：多实体与多图层实体提取
3. PT-P0-08：SiteModel 完整生成

原因：

1. 这是整条链路的最小入口。
2. 输入文件已经界定完成，尤其是 [Epic01_ProLine_CAD/spikes/spike_01_dwg_parse/test_data/real_world/20180109_机加车间平面布局图.dwg](../spikes/spike_01_dwg_parse/test_data/real_world/20180109_%E6%9C%BA%E5%8A%A0%E8%BD%A6%E9%97%B4%E5%B9%B3%E9%9D%A2%E5%B8%83%E5%B1%80%E5%9B%BE.dwg) 已经确定为主基线样本。
3. 只有先得到稳定的 SiteModel 输出，ConstraintAgent 和 LayoutAgent 的功能测试才有可信输入。

#### 阶段 B：再写 ConstraintAgent 的最小可执行测试

优先级建议：

1. CT-P0-01：约束集加载与版本识别
2. CT-P0-03：SAT 正常场景求解
3. CT-P0-04：已知硬约束违规检出

原因：

1. 这三条测试直接定义 ConstraintAgent 是否真的具备“检查能力”。
2. 先不写软约束评分和复杂冲突核心提取，避免一开始测试样本设计过重。

#### 阶段 C：最后写 LayoutAgent 的最小业务闭环测试

优先级建议：

1. LT-P0-01：布局会话启动与 Gate A/B 校验
2. LT-P0-03：候选方案自动生成
3. LT-P0-09：Gate C 锁版成功

原因：

1. 这是布局模块最核心的功能目标。
2. 实时拖拽验证、吊运干涉检测、推荐方案等能力可以作为第二层测试递进补上。

### 15.4 下一步的实际动作建议

如果按 TDD 落地，下一步最合理的具体动作是：

1. 在 ParseAgent 对应测试目录下先创建 3 个 P0 功能测试。
2. 这些测试必须直接绑定已经选定的 DWG 输入文件，而不是使用空 bytes 或假文件名。
3. 先接受 RED 状态，再反推最小实现。

### 15.5 结论

所以你的方向是对的：下一步就是开始编写功能测试用例。

我的挑战点只在于节奏控制：

不要一次性写完整套功能测试，而是先写 ParseAgent 的第一批最小 P0 红灯测试，用最短反馈回路逼出第一版真实实现。

---

*文档结束*