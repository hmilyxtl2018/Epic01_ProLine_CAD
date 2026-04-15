# Spike-1 底图测试文件策略：三层测试数据方案

> 更新日期: 2026-04-10  
> 解决问题: 纯生成DXF说服力不足，需引入真实DWG文件

---

## 核心观点

**不存在公开的航空工厂 DWG/RVT 底图**。Boeing Everett、Airbus Hamburg、COMAC 浦东的厂房图纸均为 **高度机密资产**（ITAR/EAR管控）。但这不意味着只能用合成数据 — 我们采用 **三层测试策略**，每层解决不同验证目标：

| 层次 | 目的 | 文件来源 | 已获取 |
|------|------|---------|--------|
| **Tier-A** 格式兼容性 | 证明解析器能处理真实AutoCAD输出 | LibreDWG/ezdxf开源仓库 | ✅ 21个文件 |
| **Tier-B** 领域内容验证 | 验证航空车间特有图层/实体提取 | ezdxf生成（已知Ground Truth） | ✅ 5个文件 |
| **Tier-C** 真实客户底图 | 端到端真实场景验证 | 客户/合作方提供 | ⬜ 待获取 |

---

## Tier-A: 真实格式文件（已下载）

### 来源 1: LibreDWG 官方测试库

| 文件 | 版本 | 大小 | 验证点 |
|------|------|------|--------|
| `example_r14.dwg` | R14 | 430KB | 20年以上老旧图纸格式 |
| `example_2000.dwg` | R2000 | 569KB | **最关键**：75%企业仍使用此版本 |
| `example_2004.dwg` | R2004 | 184KB | ObjectDBX新格式 |
| `example_2007.dwg` | R2007 | 445KB | 注释缩放(AnnotationScaling) |
| `example_2010.dwg` | R2010 | 440KB | PDF底图、参数化约束 |
| `example_2013.dwg` | R2013 | 144KB | DirectConnect新特性 |
| `example_2018.dwg` | R2018 | 146KB | 最新格式版本 |
| `sample_2000.dwg` | R2000 | 22KB | 不同实体组合 |
| `sample_2018.dwg` | R2018 | 19KB | 最新格式样例2 |

- **License**: GPLv3（测试用途合规）
- **说服力**: 这些是 **真正的 AutoCAD 二进制 DWG 文件**，由真实 AutoCAD 软件生成，包含完整的文件头、类区段、对象映射等原生结构
- **验证目标**: S1-TC05（多版本兼容）、S1-TC06（格式错误处理对比）

### 来源 2: ezdxf 官方 DXF 特性库

| 文件 | 验证特性 | 说明 |
|------|---------|------|
| `hatches_1.dxf` | HATCH实体 | 工厂底图中区域划分的核心实体 |
| `hatches_2.dxf` | 复杂HATCH | 嵌套边界、交叉填充 |
| `3dface.dxf` | 3DFACE | 三维厂房模型切面 |
| `text.dxf` | TEXT/MTEXT | 标注解析压力测试（各种字体/对齐） |
| `visibility.dxf` | 图层可见性 | 图层冻结/关闭/锁定状态 |
| `colors.dxf` | ACI颜色 | 图层颜色编码识别 |
| `uncommon.dxf` | 罕见实体 | 容错测试 |

- **License**: MIT（完全自由使用）
- **说服力**: 由 ezdxf 作者（DXF领域权威）精心构造的 **边界条件覆盖** 文件

### 来源 3: LibreDWG 实体类型覆盖

| 文件 | 实体类型 | 工厂底图中角色 |
|------|---------|---------------|
| `Line.dwg` | LINE | 墙体、柱网 |
| `Arc.dwg` | ARC | 圆弧墙、转弯通道 |
| `Ellipse.dwg` | ELLIPSE | 椭圆形设备轮廓 |
| `Spline.dwg` | SPLINE | 曲面设备外形 |
| `Leader.dwg` | LEADER | 设备标注引线 |

---

## Tier-B: 领域生成文件（已生成）

这些是用 ezdxf 按航空工业规范生成的测试底图。**关键优势：已知 Ground Truth**（精确知道每个实体的位置、属性、图层），可以自动化验证解析精度。

| 文件 | 复杂度 | Ground Truth |
|------|--------|-------------|
| `tier1_wing_leading_edge_workshop.dxf` | 15 equip / 13 layers | 精确坐标+图层+属性已知 |
| `tier2_fuselage_join_facility.dxf` | 53 equip / 17 layers | NDT辐射区(15m) + 天车轨道 |
| `tier3_pulse_line_fal.dxf` | 42 equip / 19 layers | 脉动线6站 + 辅助厂房 |
| `corrupted_file.dxf` | 错误文件 | 截断+垃圾数据 |
| `reference_points_offset.dxf` | 坐标偏移 | 3参考点+映射JSON |

> **为什么不能只用真实DWG？** 因为真实DWG没有Ground Truth——你不知道里面"应该"有多少个设备、每个坐标是否解析正确。生成文件是验证 **解析精度** 的唯一可靠方法。

---

## Tier-C: 真实客户底图（待获取）

### 获取路径

| 渠道 | 优先级 | 可行性 | 具体操作 |
|------|--------|--------|---------|
| **①客户提供** | ★★★★★ | 最高 | 签NDA后获取1~2张真实车间底图 |
| **②Autodesk Factory Design** | ★★★★ | 高 | 安装试用版，内置工厂布局样例项目 |
| **③Revit官方样例** | ★★★ | 中 | `rac_advanced_sample_project.rvt`（建筑，非工厂） |
| **④CAD共享站付费下载** | ★★ | 低 | bibliocad.com 工业建筑类（需付费会员） |
| **⑤合作院校/研究所** | ★★★ | 中 | 与航空院所合作获取脱敏底图 |

### 推荐优先路径

**首选: Autodesk Factory Design Utilities 试用版**

```
Autodesk Factory Design Utilities 2025
├── 安装后自带 Sample Factory Layout 项目
├── 包含: 工厂厂房 + 设备布局 + 物流路线
├── 格式: DWG (AutoCAD) / RVT (Revit互通)
├── 试用期: 30天免费
└── 下载: https://www.autodesk.com/products/factory-design-utilities/free-trial
```

这是**最接近真实工厂底图**的合法免费来源。Autodesk Factory Design Utilities 是专门为**工厂布局设计**开发的工具，其样例项目包含：
- 真实比例的工厂厂房结构
- 标准工业设备图块库（CNC、传送带、工作台等）
- 物流动线、安全区域标注
- 多图层分层（建筑/设备/管线/安全区）

**备选: 联系既有客户/合作方**

建议在 PoC 启动时向客户方请求：
- 1~2张 **脱敏后的车间底图**（去除敏感信息如具体设备型号）
- 签订测试数据使用 NDA
- 这将成为最终验收的"真实场景"测试用例

---

## 三层策略在测试用例中的映射

| 测试用例 | Tier-A (真实DWG) | Tier-B (领域生成) | Tier-C (客户底图) |
|---------|----------------|------------------|-----------------|
| S1-TC01 基础解析 | ✅ example_2000.dwg | ✅ tier1 (验精度) | ✅ (终验) |
| S1-TC02 实体提取 | ✅ hatches/text/3dface | ✅ tier2 (验完整性) | |
| S1-TC03 图层提取 | ✅ visibility.dxf | ✅ tier1-3 (验图层) | |
| S1-TC04 坐标校准 | | ✅ reference_points | ✅ (真实偏移) |
| S1-TC05 多版本 | ✅ R14~R2018全覆盖 | | |
| S1-TC06 异常处理 | ✅ uncommon.dxf | ✅ corrupted_file | |

---

## 文件清单汇总

```
test_data/
├── real_world/                      ← Tier-A: 真实格式文件
│   ├── libredwg/                    ← 9 个真实 DWG (R14~R2018)
│   │   ├── example_2000.dwg  (569KB)
│   │   ├── example_2004.dwg  (184KB)
│   │   ├── example_2007.dwg  (445KB)
│   │   ├── example_2010.dwg  (440KB)
│   │   ├── example_2013.dwg  (144KB)
│   │   ├── example_2018.dwg  (146KB)
│   │   ├── example_r14.dwg   (430KB)
│   │   ├── sample_2000.dwg    (22KB)
│   │   └── sample_2018.dwg    (19KB)
│   ├── ezdxf/                       ← 7 个 DXF 特性文件
│   │   ├── hatches_1.dxf     (127KB)
│   │   ├── hatches_2.dxf     (204KB)
│   │   ├── 3dface.dxf        (130KB)
│   │   ├── text.dxf          (227KB)
│   │   ├── visibility.dxf    (119KB)
│   │   ├── colors.dxf        (148KB)
│   │   └── uncommon.dxf      (335KB)
│   ├── libredwg_entities/           ← 5 个实体类型 DWG
│   │   ├── Line.dwg, Arc.dwg, Ellipse.dwg, Spline.dwg, Leader.dwg
│   └── manifest.json
│
├── tier1_wing_leading_edge_workshop.dxf    ← Tier-B: 领域生成
├── tier2_fuselage_join_facility.dxf
├── tier3_pulse_line_fal.dxf
├── corrupted_file.dxf
├── reference_points_offset.dxf
└── reference_points_mapping.json
```

**总计: 26 个测试文件（21个真实 + 5个领域生成）**
