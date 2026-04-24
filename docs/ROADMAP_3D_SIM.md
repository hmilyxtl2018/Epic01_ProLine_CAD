# RFC: 3D 布局建模 + 干涉仿真路线图

> **Status**: Draft · 2026-04-22
> **Owners**: Epic-01 ProLine CAD team
> **Scope**: 从「2D 图纸 + LLM 富化」走到「3D 布局 + 运动仿真 + 决策交付」的端到端能力闭环。

---

## 1. 北极星目标

工程师上传一张产线 DWG → 平台 30 分钟内产出：

1. **可编辑的 3D 布局**（设备摆位、管线、通道）
2. **节拍 + 利用率仿真报告**（瓶颈 / 资源冲突 / 干涉点）
3. **可签批的方案差异**（A/B/C 三套布局对比）

不取代 Visual Components / FlexSim 这类专业 DES，但要做到「面向上游，决策快、改动便宜」。

---

## 2. 现状盘点（2026-04-22）

| 能力 | 状态 | 位置 |
|---|---|---|
| DXF/DWG 解析 (M2 ParseAgent) | ✅ | [parse_agent.py](app/services/parse_agent.py) |
| LLM 13 步语义富化 (M2.5) | ✅ | enrichment pipeline |
| 2D 渲染 (MLightCAD) | ✅ | iframe |
| SiteModel / AssetGeometry 表 | ✅ 字段为 2D | PostgreSQL |
| S1 工作台（解析/审核/术语） | ✅ MVP | [sites/[runId]/page.tsx](web/src/app/sites/[runId]/page.tsx) |
| S2/S3/S4/S5 | 🚫 仅 tab 占位 | 同上 |
| Taxonomy 命中率 | 🔴 0% | 词表只有 50 项基线，未喂行业词 |

**结论**：我们已完成「读懂图纸 + 富化标签」，3D 与仿真是两条**新工程线**，不是延伸。

---

## 3. 用户需求拆解

### 需求 1 · 产线布局三维建模
- **3D 表达**：高度 / 姿态 / 接口（出料口、电源、风管）
- **资产库**：每类设备一个 3D 模型（参数化 box / glTF / STEP）
- **编辑能力**：拖拽、旋转、对齐、自动吸附、连接关系

### 需求 2 · 产线运行干涉仿真
- **运动学**：机械臂关节链、AGV 路径、传送带物料流
- **碰撞检测**：mesh vs mesh / swept volume / AABB 扫掠
- **离散事件 (DES)**：物料到达、节拍、瓶颈、资源利用
- **回放 + 报告**：高亮冲突点、给出修改建议

---

## 4. 技术路径

### 🟢 档位 A · MVP（4–8 周）
**目标**：能 demo、能 PoC、不交付。

| 模块 | 选型 | 备注 |
|---|---|---|
| 3D 渲染 | Three.js + react-three-fiber | 与现有 Next.js 栈一致 |
| 几何升维 | 2D bbox → Z 拉伸成 box | 高度来自资产库默认值 |
| 资产库 | 5–10 个参数化原语 | 冲床/传送带/AGV/机器人占位/操作员 |
| 编辑 | drei `<TransformControls>` | 平移/旋转/缩放 |
| 路径规划 | A* over grid | 不接物理引擎 |
| 碰撞 | AABB 扫掠 | 不做 mesh 级 |
| 时间轴 | 关键帧 + requestAnimationFrame | 不接 DES 内核 |
| 输出 | "X 在 t=12.3s 与 Y 冲突" | JSON + 高亮 |

### 🔴 档位 B · 工程级（6+ 个月，按需启动）
- 资产库团队（采购/建模 100+ 真实设备 glTF/STEP）
- 物理引擎 Rapier / cannon-es（mesh 级碰撞）
- DES 引擎 SimPy / salabim（节拍仿真）
- URDF + IK（ikpy）做机械臂
- 或外购 Visual Components / FlexSim SDK 集成

---

## 5. 关键判断

1. **LLM 富化是稀缺资产**——它能告诉 3D 引擎「这个聚类是冲床」，VC 之流没有这一层。
2. **S2 工艺约束是 S3/S4 前提**——没有约束模型，仿真只是动画。
3. **2D→3D 升维 ground truth 缺失**——DWG 没有高度。三个来源择一：
   - (a) 资产库默认值（推荐 MVP）
   - (b) 用户填写
   - (c) 上传立面图 / IFC
4. **Garbage in → garbage out**：先把 taxonomy 命中率从 0% 拉到 60%+，否则 3D 阶段全靠瞎猜。

---

## 6. 执行顺序（已对齐）

按依赖图最稳的顺序：

### Phase 1 · 把 S1 真正可用 ⏱ 2 周
- **P1.1** Taxonomy 词表 50→200 项（覆盖冲压/焊接/装配/物流五大类）
- **P1.2** softmatch 阈值 + few-shot 注入，命中率从 0% 提到 ≥60%
- **P1.3** 资产高度默认表（每个 taxonomy 一个 `default_height_m`）

### Phase 2 · S2 工艺约束 schema + 编辑器 ⏱ 2 周
- **P2.1** schema：`{predecessor, resource, takt, exclusion}` 四类约束
- **P2.2** 后端表 `process_constraints` + CRUD API
- **P2.3** 前端：表格编辑 + 甘特预览
- **P2.4** 验证器：循环依赖 / 资源争抢检测

### Phase 3 · MVP 3D 视图 ⏱ 2 周
- **P3.1** react-three-fiber + drei 集成；S3 tab 启用
- **P3.2** SiteModel → 拉伸盒子；按 LLM cluster 着色；点选联动右栏
- **P3.3** 5 件资产原语库（box/cylinder 组合）
- **P3.4** TransformControls 编辑；保存到新表 `layout_3d_placements`
- **P3.5** 相机/网格/光照预设；性能预算 60fps @ 5k 设备

### Phase 4 · 静态干涉检查 ⏱ 1 周
- **P4.1** AABB-vs-AABB 全配对扫描；O(n log n) 网格分桶
- **P4.2** 通道 / 安全距离规则（可配置）
- **P4.3** 冲突列表 + 3D 高亮 + 跳转

### Phase 5 · 动态仿真 (MVP) ⏱ 2 周
- **P5.1** AGV / 传送带路径定义（在 3D 视图画线）
- **P5.2** 关键帧动画引擎；时间轴控件；播放/暂停/拖拽
- **P5.3** AABB 扫掠（swept volume）冲突检测
- **P5.4** 冲突时刻 → 截图 + JSON 报告

### Phase 6 · DES 接入（可选，按需）⏱ 3 周
- **P6.1** 后端集成 SimPy；从 S2 约束生成模型
- **P6.2** 输出：节拍 / 瓶颈 / 资源利用率
- **P6.3** 与 3D 时间轴对齐

### Phase 7 · S5 决策工作台 ⏱ 1 周
- 方案 A/B/C 多版本；指标雷达图；签批流；导出 PDF

**总计**：MVP 全闭环 9 周；接 DES 12 周。

---

## 7. 数据模型增量

### 新表
```sql
-- 资产库（可复用的 3D 原语 + 默认参数）
CREATE TABLE asset_catalog (
  id UUID PRIMARY KEY,
  taxonomy_term TEXT NOT NULL,            -- 关联 LLM 富化术语
  display_name TEXT NOT NULL,
  primitive_kind TEXT NOT NULL,           -- 'box' | 'cylinder' | 'composite'
  default_dims JSONB NOT NULL,            -- {w, d, h} (m)
  ports JSONB,                            -- 出/入料口、电源接口
  gltf_url TEXT,                          -- 升级到真实模型后填
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3D 摆位（每个 SiteModel 一份布局）
CREATE TABLE layout_3d_placements (
  id UUID PRIMARY KEY,
  site_model_id UUID NOT NULL REFERENCES site_models(id) ON DELETE CASCADE,
  cluster_id TEXT,                        -- 来自 D_cluster_proposals
  asset_catalog_id UUID REFERENCES asset_catalog(id),
  position JSONB NOT NULL,                -- {x, y, z}
  rotation JSONB NOT NULL,                -- {rx, ry, rz} (rad)
  scale JSONB,                            -- 可选 override
  metadata JSONB,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 工艺约束
CREATE TABLE process_constraints (
  id UUID PRIMARY KEY,
  site_model_id UUID NOT NULL REFERENCES site_models(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,                     -- 'predecessor' | 'resource' | 'takt' | 'exclusion'
  payload JSONB NOT NULL,
  created_by TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 仿真运行结果
CREATE TABLE simulation_runs (
  id UUID PRIMARY KEY,
  site_model_id UUID NOT NULL REFERENCES site_models(id) ON DELETE CASCADE,
  layout_snapshot JSONB NOT NULL,
  conflicts JSONB,                        -- [{t, a, b, kind, severity}]
  metrics JSONB,                          -- {takt, utilization, throughput}
  status TEXT NOT NULL,
  duration_ms INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### `asset_catalog` 默认高度（Phase 1.3 用）
| taxonomy | h (m) | 备注 |
|---|---|---|
| stamping_press | 4.0 | 冲压机 |
| welding_robot | 2.4 | 焊接机器人 |
| conveyor_belt | 1.0 | 传送带 |
| agv | 0.5 | AGV 小车 |
| operator_station | 1.8 | 操作工位 |
| ... | ... | 见 P1.1 词表 |

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| Taxonomy 命中率上不去 | 3D 全靠默认 box | Phase 1 优先；接受人工确认兜底 |
| 用户拒绝在 2D 上"凭空"加高度 | 3D 失真 | 资产库默认值 + 一键覆盖；MVP 不追求精度 |
| MLightCAD iframe 与 3D 视图状态同步复杂 | UX 割裂 | 共用 Zustand store；选中态双向广播 |
| Three.js 性能在 5k+ 设备掉帧 | 卡顿 | InstancedMesh + LOD + frustum culling |
| DES 学习成本高 | Phase 6 滞后 | 先发 Phase 5（关键帧版本），DES 作为 v2 |

---

## 9. 验收标准（每个 Phase）

每个 Phase 必须满足：
1. 端到端 demo 视频 ≤ 3 分钟
2. 至少一份真实客户图纸跑通
3. 单元测试覆盖关键算法（碰撞、约束验证、升维）
4. 性能预算文档化（fps / 内存 / API 延迟）
5. 用户文档（操作手册片段）

---

## 10. 立即下一步

**Phase 1.1**：扩 taxonomy 词表 50→200 项。下一条 commit 开始。
