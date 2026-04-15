# ProLine CAD 关键技术验证 — 详细测试用例设计

**版本**：v1.0  
**日期**：2026-04-10  
**关联文档**：关键技术验证计划 v1.0、TEST_PLAN.md v1.0、PRD v1.2  
**状态**：待评审  

---

## 文档说明

本文档为 ProLine CAD 航空制造产线智能规划系统的完整测试用例设计，覆盖 10 个 Spike 验证点 + 跨 Spike 集成测试。  
每条测试用例包含以下 10 个字段：

| 字段 | 说明 |
|------|------|
| **用例编号** | 格式 `S{Spike}-TC{序号}` (已有) / `S{Spike}-RT{组}{序号}` (新增真实数据) / `INT-{序号}` (集成) |
| **名称** | 测试用例中文名称 |
| **所属功能模块** | Spike 编号 + 模块名称 |
| **版本** | 用例版本号 |
| **测试目的** | 验证的技术点和业务价值 |
| **测试类型** | 功能 / 性能 / 异常 / 兼容性 / 集成 / 精度 |
| **前置关联** | 依赖的其他测试用例编号（无则填 "无"） |
| **前置条件** | 环境、工具、数据等前提条件 |
| **测试数据** | 具体使用的测试数据文件及关键参数 |
| **通过条件设定** | 明确的量化验收标准（来自 Go/No-Go 阈值） |

---

## 一、Spike-1：DWG/DXF 底图解析

> **模块**：Spike-1 DWG/DXF 底图解析  
> **优先级**：P0（阻塞型）  
> **Go/No-Go 阈值**：实体差异 ≤1%、图层识别率 ≥85%、坐标误差 ≤10mm、大文件内存 ≤2GB、大文件耗时 ≤30s  

### 1.1 已有测试用例

#### S1-TC01 — DWG/DXF 基础解析（合成数据）

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-TC01 |
| **名称** | DWG/DXF 基础实体解析验证 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证 ezdxf 对 DXF 文件的基础解析能力：图层提取、实体统计、实体类型识别 |
| **测试类型** | 功能 |
| **前置关联** | 无 |
| **前置条件** | Python 3.11+、ezdxf 1.4.3 已安装；DWGParser 模块可导入 |
| **测试数据** | `tier1_wing_leading_edge_workshop.dxf` (99 实体)、`tier2_fuselage_join_facility.dxf` (286 实体)、`tier3_pulse_line_fal.dxf` (358 实体) |
| **通过条件设定** | 1. 每份文件提取实体数量偏差 ≤ `Thresholds.S1_ENTITY_DIFF_PCT` (1%)<br>2. 返回 `layer_count > 0`<br>3. 返回实体类型集合非空<br>4. 5 个子方法全部 PASS: `test_tc01_tier1_parse`, `test_tc01_tier2_parse`, `test_tc01_tier3_parse`, `test_tc01_entity_types`, `test_tc01_layer_names` |

---

#### S1-TC02 — 图层语义映射（合成数据）

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-TC02 |
| **名称** | 图层语义分类准确率验证 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证 LayerSemanticMapper 将非标图层名映射到 structure/equipment/exclusion/auxiliary 四大类的准确率 |
| **测试类型** | 功能 |
| **前置关联** | S1-TC01（解析完成后才能做图层映射） |
| **前置条件** | LayerSemanticMapper 模块可导入；LAYER_SEMANTIC_MAP 配置已加载 |
| **测试数据** | `tier2_fuselage_join_facility.dxf`（合成图层名） |
| **通过条件设定** | 1. 图层分类准确率 ≥ `Thresholds.S1_LAYER_CLASSIFY_RATE` (85%)<br>2. 四大类 (structure/equipment/exclusion/auxiliary) 至少各分类出 1 个图层<br>3. 3 个子方法全部 PASS: `test_tc02_classify_rate`, `test_tc02_known_layers`, `test_tc02_semantic_categories` |

---

#### S1-TC03 — 大文件性能基线（合成数据）

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-TC03 |
| **名称** | 大文件解析性能基线验证 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证 DWGParser 解析大文件时的内存和耗时不超标 |
| **测试类型** | 性能 |
| **前置关联** | S1-TC01 |
| **前置条件** | tracemalloc 可用；tier3 合成 DXF 存在 |
| **测试数据** | `tier3_pulse_line_fal.dxf` (358 实体，合成大文件) |
| **通过条件设定** | 1. 峰值内存 ≤ `Thresholds.S1_LARGE_FILE_MEMORY_MB` (2048 MB)<br>2. 解析耗时 ≤ `Thresholds.S1_LARGE_FILE_TIME_S` (30s)<br>3. 2 个子方法全部 PASS: `test_tc03_memory`, `test_tc03_elapsed_time` |

---

#### S1-TC04 — 坐标系对齐精度

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-TC04 |
| **名称** | 仿射变换坐标对齐精度验证 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证 CoordinateAligner 通过参考点仿射变换将 DWG 坐标对齐到实际坐标系的精度 |
| **测试类型** | 精度 |
| **前置关联** | S1-TC01 |
| **前置条件** | numpy 已安装；CoordinateAligner 模块可导入 |
| **测试数据** | `reference_points_offset.dxf` + `reference_points_mapping.json` (≥3 组参考点对) |
| **通过条件设定** | 1. 最大对齐误差 ≤ `Thresholds.S1_COORD_ERROR_MM` (10mm)<br>2. 平均误差 ≤ 5mm<br>3. 仿射变换矩阵行列式 > 0（非退化）<br>4. 4 个子方法全部 PASS: `test_tc04_max_error`, `test_tc04_mean_error`, `test_tc04_transform_valid`, `test_tc04_inverse_transform` |

---

#### S1-TC06 — 损坏文件优雅失败

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-TC06 |
| **名称** | 损坏 DXF 文件优雅失败验证 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证解析器遇到损坏文件时不崩溃，返回结构化错误码 |
| **测试类型** | 异常 |
| **前置关联** | 无 |
| **前置条件** | corrupted_file.dxf 存在 |
| **测试数据** | `corrupted_file.dxf` |
| **通过条件设定** | 1. 不抛出未捕获异常（无 crash）<br>2. 返回错误码 = `Thresholds.S1_ERROR_CODE_CORRUPT` (5001)<br>3. 错误信息包含文件路径<br>4. 3 个子方法全部 PASS: `test_tc06_no_crash`, `test_tc06_error_code`, `test_tc06_error_message` |

---

#### S1-RW01 — 真实 DXF 文件解析

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RW01 |
| **名称** | 真实工业 DXF 参考集解析验证 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证解析器对 ezdxf 官方参考 DXF 文件集的兼容性 |
| **测试类型** | 兼容性 |
| **前置关联** | S1-TC01 |
| **前置条件** | `spike_01_dwg_parse/test_data/real_world/ezdxf/` 目录包含参考 DXF 文件 |
| **测试数据** | `hatch_complex.dxf`, `hatch_patterns.dxf`, `custom_blocks.dxf`, `viewport_layers.dxf`, `entities_all.dxf` 等 |
| **通过条件设定** | 1. 所有文件均可被 `ezdxf.readfile()` 成功打开<br>2. 每份文件提取实体数 > 0<br>3. 2 个子方法全部 PASS: `test_real_world_dxf_parse`, `test_real_world_entity_count` |

---

#### S1-EDGE01 — 边界条件用例

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-EDGE01 |
| **名称** | 空 DXF 文件边界条件验证 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证解析器处理空文件（0 实体）时不崩溃 |
| **测试类型** | 异常 |
| **前置关联** | 无 |
| **前置条件** | tier1 DXF 文件存在（测试空图层场景） |
| **测试数据** | `tier1_wing_leading_edge_workshop.dxf`（过滤特定空图层） |
| **通过条件设定** | 1. 返回 entities=0 的有效结果，不崩溃<br>2. `test_empty_layer_handling` PASS |

---

### 1.2 新增测试用例（基于真实工业数据）

#### S1-RT01-01 — 木工车间 DXF 基础解析

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT01-01 |
| **名称** | 木工车间工业 DXF 基础解析 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证对真实中等复杂度工业产线底图的实体、图层解析正确性 |
| **测试类型** | 功能 |
| **前置关联** | S1-TC01 |
| **前置条件** | `woodworking_plant.dxf` 已下载至 `spike_01_dwg_parse/test_data/real_world/` |
| **测试数据** | `woodworking_plant.dxf` — 3.2 MB, 11 图层, 1,563 实体 (含 equipment/rail/wall 语义层, INSERT 202 块) |
| **通过条件设定** | 1. 提取实体数量与参考值 1,563 偏差 ≤ 1%<br>2. 提取图层数 = 11<br>3. 确认包含 equipment、rail、wall 图层 |

---

#### S1-RT01-02 — 木工工厂 DXF 基础解析

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT01-02 |
| **名称** | 木工工厂工业 DXF 基础解析 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证对含弧线密集实体的工业底图解析能力 |
| **测试类型** | 功能 |
| **前置关联** | S1-TC01 |
| **前置条件** | `woodworking_factory_1.dxf` 已下载 |
| **测试数据** | `woodworking_factory_1.dxf` — 3.9 MB, 9 图层, 11,424 实体 (含 floor/walls/furn_eq, ARC 3,210) |
| **通过条件设定** | 1. 提取实体数量与参考值 11,424 偏差 ≤ 1%<br>2. 提取图层数 = 9<br>3. 含 floor、walls、furn_eq 图层 |

---

#### S1-RT01-03 — 冷轧钢生产线 DXF 基础解析

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT01-03 |
| **名称** | 冷轧钢生产线大规模 DXF 基础解析 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证对大规模（近 10 万实体）工业底图的解析正确性 |
| **测试类型** | 功能 |
| **前置关联** | S1-TC01 |
| **前置条件** | `cold_rolled_steel_production.dxf` 已下载 |
| **测试数据** | `cold_rolled_steel_production.dxf` — 42.7 MB, 5 图层, 95,856 实体 (LINE 78,954, DIMENSION 45) |
| **通过条件设定** | 1. 提取实体数量与参考值 95,856 偏差 ≤ 1%<br>2. 提取图层数 = 5<br>3. LINE 实体占比 > 80% |

---

#### S1-RT01-04 — 鱼加工厂 DXF 基础解析

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT01-04 |
| **名称** | 鱼加工厂超大规模 DXF 基础解析 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证对最大文件（118 图层、10 万+实体）的解析正确性 |
| **测试类型** | 功能 |
| **前置关联** | S1-TC01 |
| **前置条件** | `fish_processing_plant.dxf` 已下载 |
| **测试数据** | `fish_processing_plant.dxf` — 82.9 MB, 118 图层, 104,811 实体 (SPLINE 12,901) |
| **通过条件设定** | 1. 提取实体数量与参考值 104,811 偏差 ≤ 1%<br>2. 提取图层数 = 118 |

---

#### S1-RT02-01 — 木工车间图层语义映射

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT02-01 |
| **名称** | 木工车间真实图层语义分类 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证 LayerSemanticMapper 对含 equipment/rail/wall/axis/txt 的真实图层名分类能力 |
| **测试类型** | 功能 |
| **前置关联** | S1-TC02, S1-RT01-01 |
| **前置条件** | LayerSemanticMapper 支持泛化映射 + 同义词表 |
| **测试数据** | `woodworking_plant.dxf` — 11 图层: equipment→设备, rail→设备, wall→结构, axis→辅助, txt→辅助 |
| **通过条件设定** | 图层分类准确率 ≥ `Thresholds.S1_LAYER_CLASSIFY_RATE` (85%) |

---

#### S1-RT02-02 — 鱼加工厂 118 层语义映射

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT02-02 |
| **名称** | 鱼加工厂 118 层大规模语义分类 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证对真实大量非标图层名（axis/wall exist/columns/techno 等）的语义映射压力 |
| **测试类型** | 功能 |
| **前置关联** | S1-TC02, S1-RT01-04 |
| **前置条件** | LayerSemanticMapper 支持 118 层批量分类 |
| **测试数据** | `fish_processing_plant.dxf` — 118 层含 axis→辅助, wall1/wall exist→结构, columns→结构, techno 1/2/3→设备 |
| **通过条件设定** | 图层分类准确率 ≥ `Thresholds.S1_LAYER_CLASSIFY_RATE` (85%) |

---

#### S1-RT02-03 — 冷轧钢生产线图层分类

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT02-03 |
| **名称** | 冷轧钢生产线非标图层分类 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证对非标层名（0/dwgmodels.com/Defpoints/hatch/Системный слой）的容错归类 |
| **测试类型** | 功能 |
| **前置关联** | S1-TC02, S1-RT01-03 |
| **前置条件** | LayerSemanticMapper 支持 unclassified 兜底 |
| **测试数据** | `cold_rolled_steel_production.dxf` — 5 图层 (含俄语层名、网站水印层名) |
| **通过条件设定** | 图层分类准确率 ≥ 85%（含 unclassified 归类合理） |

---

#### S1-RT02-04 — 非标层名 unclassified 比率

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT02-04 |
| **名称** | 工业文件非标层名 unclassified 比率统计 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 统计全部 4 份工业文件中无法归类的图层比率，确保不超标 |
| **测试类型** | 功能 |
| **前置关联** | S1-RT02-01 ~ S1-RT02-03 |
| **前置条件** | 4 份工业 DXF 均已解析并完成图层映射 |
| **测试数据** | 全部 4 份工业 DXF: woodworking_plant, woodworking_factory_1, cold_rolled_steel_production, fish_processing_plant |
| **通过条件设定** | unclassified 图层占比 ≤ 30% |

---

#### S1-RT03-01 — 鱼加工厂内存压测

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT03-01 |
| **名称** | 鱼加工厂 83MB 文件内存压测 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证解析 83MB 真实工业 DXF 时峰值内存不超标 |
| **测试类型** | 性能 |
| **前置关联** | S1-TC03 |
| **前置条件** | tracemalloc 可用；fish_processing_plant.dxf 已下载 |
| **测试数据** | `fish_processing_plant.dxf` — 82.9 MB, 104,811 实体 |
| **通过条件设定** | 峰值内存 ≤ `Thresholds.S1_LARGE_FILE_MEMORY_MB` (2,048 MB) |

---

#### S1-RT03-02 — 鱼加工厂耗时压测

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT03-02 |
| **名称** | 鱼加工厂 83MB 文件耗时压测 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证解析 83MB 真实工业 DXF 的耗时不超标 |
| **测试类型** | 性能 |
| **前置关联** | S1-TC03 |
| **前置条件** | time.perf_counter 可用 |
| **测试数据** | `fish_processing_plant.dxf` — 82.9 MB |
| **通过条件设定** | 解析耗时 ≤ `Thresholds.S1_LARGE_FILE_TIME_S` (30s) |

---

#### S1-RT03-03 — 冷轧钢生产线内存压测

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT03-03 |
| **名称** | 冷轧钢 43MB 文件内存压测 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证解析 43MB 工业 DXF 时峰值内存 |
| **测试类型** | 性能 |
| **前置关联** | S1-TC03 |
| **前置条件** | tracemalloc 可用 |
| **测试数据** | `cold_rolled_steel_production.dxf` — 42.7 MB, 95,856 实体 |
| **通过条件设定** | 峰值内存 ≤ `Thresholds.S1_LARGE_FILE_MEMORY_MB` (2,048 MB) |

---

#### S1-RT03-04 — 冷轧钢生产线耗时压测

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT03-04 |
| **名称** | 冷轧钢 43MB 文件耗时压测 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证解析 43MB 工业 DXF 的耗时 |
| **测试类型** | 性能 |
| **前置关联** | S1-TC03 |
| **前置条件** | time.perf_counter 可用 |
| **测试数据** | `cold_rolled_steel_production.dxf` — 42.7 MB |
| **通过条件设定** | 解析耗时 ≤ `Thresholds.S1_LARGE_FILE_TIME_S` (30s) |

---

#### S1-RT04-01 — 实体类型覆盖度

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT04-01 |
| **名称** | 14 种 DXF 实体类型覆盖度验证 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证 4 份工业文件合并后可覆盖 ≥10 种实体类型 |
| **测试类型** | 功能 |
| **前置关联** | S1-RT01-01 ~ S1-RT01-04 |
| **前置条件** | 4 份工业 DXF 均可解析 |
| **测试数据** | 全部 4 份工业 DXF，期望覆盖: LINE, ARC, LWPOLYLINE, CIRCLE, INSERT, MTEXT, HATCH, ELLIPSE, SPLINE, DIMENSION, POLYLINE, TEXT, POINT, REGION |
| **通过条件设定** | 合并实体类型集合 ≥ 10 种 |

---

#### S1-RT04-02 — DIMENSION 实体解析

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT04-02 |
| **名称** | DIMENSION 标注实体数值提取 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证 DIMENSION 实体可提取标注值（用于工站间距计算） |
| **测试类型** | 功能 |
| **前置关联** | S1-RT01-03 |
| **前置条件** | cold_rolled_steel_production.dxf 含 45 个 DIMENSION |
| **测试数据** | `cold_rolled_steel_production.dxf` — 45 个 DIMENSION 实体 |
| **通过条件设定** | 45 个 DIMENSION 实体全部可提取标注值，无丢失 |

---

#### S1-RT04-03 — INSERT 块引用解析

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT04-03 |
| **名称** | INSERT 块引用解引用验证 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证 INSERT 实体可解引用到对应块定义（用于设备识别） |
| **测试类型** | 功能 |
| **前置关联** | S1-RT01-01 |
| **前置条件** | woodworking_plant.dxf 含 202 个 INSERT |
| **测试数据** | `woodworking_plant.dxf` — 202 个 INSERT 实体 |
| **通过条件设定** | 202 个 INSERT 全部可解引用到块定义 |

---

#### S1-RT04-04 — HATCH 填充实体解析

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT04-04 |
| **名称** | HATCH 填充实体边界与图案提取 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证 HATCH 实体的边界路径和图案名称可提取 |
| **测试类型** | 功能 |
| **前置关联** | S1-RT01-01 |
| **前置条件** | woodworking_plant.dxf 含 74 个 HATCH |
| **测试数据** | `woodworking_plant.dxf` — 74 个 HATCH 实体 |
| **通过条件设定** | 74 个 HATCH 实体边界 + 图案名全部可读取 |

---

#### S1-RT04-05 — SPLINE 曲线实体解析

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT04-05 |
| **名称** | SPLINE 曲线控制点提取 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证 SPLINE 实体的控制点可提取（用于异形区域边界） |
| **测试类型** | 功能 |
| **前置关联** | S1-RT01-04 |
| **前置条件** | fish_processing_plant.dxf 含 12,901 个 SPLINE |
| **测试数据** | `fish_processing_plant.dxf` — 12,901 个 SPLINE 实体 |
| **通过条件设定** | SPLINE 实体不丢失，控制点序列可提取 |

---

#### S1-RT05-01 — DWG→DXF 转换链路

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT05-01 |
| **名称** | ODA DWG→DXF 转换链路验证 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证 4 份工业 DWG 经 ODA File Converter 转换后 DXF 可被 ezdxf 正常读取 |
| **测试类型** | 兼容性 |
| **前置关联** | 无 |
| **前置条件** | ODA File Converter 27.1 已安装；4 份工业 DWG 已下载 |
| **测试数据** | `cold_rolled_steel_production.dwg`, `fish_processing_plant.dwg`, `woodworking_plant.dwg`, `woodworking_factory_1.dwg` |
| **通过条件设定** | 4/4 转换后 DXF 可被 `ezdxf.readfile()` 正常读取 |

---

#### S1-RT05-02 — DWG 版本 AC1021 识别

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT05-02 |
| **名称** | DWG 文件 AC1021 版本头识别 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证 4 份工业 DWG 文件头版本为 AC1021 (AutoCAD 2007) |
| **测试类型** | 兼容性 |
| **前置关联** | 无 |
| **前置条件** | DWG 文件可读取前 6 字节 |
| **测试数据** | 4 份工业 DWG 文件（文件头前 6 字节 = "AC1021"） |
| **通过条件设定** | 4/4 文件版本头正确识别为 AC1021 |

---

#### S1-RT05-03 — DWG 多版本兼容

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT05-03 |
| **名称** | DWG R2000/R2007/R2018 多版本识别 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证对不同 AutoCAD 版本 DWG 文件格式的版本识别能力 |
| **测试类型** | 兼容性 |
| **前置关联** | 无 |
| **前置条件** | example_2000.dwg / example_2007.dwg / example_2018.dwg 存在 |
| **测试数据** | `example_2000.dwg` (AC1015), `example_2007.dwg` (AC1021), `example_2018.dwg` (AC1032) |
| **通过条件设定** | 3/3 文件版本正确识别 |

---

#### S1-RT06-01 — BoundingBox 有效性

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT06-01 |
| **名称** | 工业 DXF BoundingBox 非零验证 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证 4 份工业 DXF 的 extents (BoundingBox) 均为有效非零值 |
| **测试类型** | 功能 |
| **前置关联** | S1-RT01-01 ~ S1-RT01-04 |
| **前置条件** | 4 份工业 DXF 均可解析 |
| **测试数据** | 全部 4 份工业 DXF |
| **通过条件设定** | extents 不为零；max > min（x、y 方向均满足） |

---

#### S1-RT06-02 — 坐标范围合理性

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT06-02 |
| **名称** | 木工车间坐标范围合理性验证 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证工厂底图坐标范围在合理尺寸内，无异常偏移 |
| **测试类型** | 功能 |
| **前置关联** | S1-RT06-01 |
| **前置条件** | 无 |
| **测试数据** | `woodworking_plant.dxf` |
| **通过条件设定** | 坐标范围在 ±100,000mm 内（合理工厂尺寸） |

---

#### S1-RT06-03 — 实体空间分布验证

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT06-03 |
| **名称** | 鱼加工厂实体空间分布离群点检测 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证实体空间分布在 BoundingBox 范围内，无离群点 |
| **测试类型** | 功能 |
| **前置关联** | S1-RT06-01 |
| **前置条件** | 无 |
| **测试数据** | `fish_processing_plant.dxf` |
| **通过条件设定** | ≥ 95% 实体在 BoundingBox 范围内 |

---

#### S1-RT07-01 — SiteModel 输出 Schema 完整性

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT07-01 |
| **名称** | SiteModel JSON Schema 完整性验证 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证 `to_site_model()` 输出包含 PRD-1 要求的所有字段 |
| **测试类型** | 功能 |
| **前置关联** | S1-RT01-01 |
| **前置条件** | SiteModel schema 已定义 |
| **测试数据** | `woodworking_plant.dxf` |
| **通过条件设定** | 输出包含 site_guid / layers / entities / bounding_box 四个必填字段 |

---

#### S1-RT07-02 — SiteModel JSON 往返保真

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT07-02 |
| **名称** | SiteModel JSON 序列化/反序列化保真验证 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证 SiteModel 对象经 JSON dumps → loads 后无信息丢失 |
| **测试类型** | 功能 |
| **前置关联** | S1-RT07-01 |
| **前置条件** | json 模块可用 |
| **测试数据** | `woodworking_plant.dxf` → SiteModel 对象 |
| **通过条件设定** | dumps → loads → 与原对象完全一致，100% 保真 |

---

#### S1-RT07-03 — SiteModel MCP 上下文追溯

| 字段 | 内容 |
|------|------|
| **用例编号** | S1-RT07-03 |
| **名称** | SiteModel 输出 MCP Context 追溯链验证 |
| **所属功能模块** | Spike-1 DWG/DXF 底图解析 |
| **版本** | v1.0 |
| **测试目的** | 验证 SiteModel 输出携带 mcp_context_id，可被下游 Agent 追溯 |
| **测试类型** | 集成 |
| **前置关联** | S1-RT07-01, S2-TC06 |
| **前置条件** | MCP Context 传播机制已实现 |
| **测试数据** | `woodworking_plant.dxf` |
| **通过条件设定** | 输出包含 `mcp_context_id` 字段且非空 |

---

## 二、Spike-2：MCP 协议端到端通信

> **模块**：Spike-2 MCP 通信  
> **优先级**：P0（架构脊柱）  
> **Go/No-Go 阈值**：stdio 成功率 100%、SSE 成功率 ≥99%、SSE P99 ≤500ms、Context 传播链 100%  

### 2.1 已有测试用例

#### S2-TC06 — MCP Context 传播链验证

| 字段 | 内容 |
|------|------|
| **用例编号** | S2-TC06 |
| **名称** | MCP Context 传播链完整性验证 |
| **所属功能模块** | Spike-2 MCP 通信 |
| **版本** | v1.0 |
| **测试目的** | 验证 Agent_A 产出的 context_id 能被 Agent_B 正确读取并链接为 parent_context |
| **测试类型** | 集成 |
| **前置关联** | 无 |
| **前置条件** | MCP SDK 已安装；mock_agent_tools.json 存在 |
| **测试数据** | `mock_agent_tools.json`（模拟 parse-agent / layout-agent 工具定义） |
| **通过条件设定** | 1. context_id 生成唯一<br>2. context 版本号自动递增<br>3. 完整 Pipeline 链路: parse → layout → sim → report，parent_contexts 链接正确<br>4. 3 个子方法全部 PASS: `test_tc06_context_chain`, `test_tc06_context_version_increment`, `test_tc06_full_pipeline_context_chain` |

---

## 三、Spike-3：空间碰撞检测与实时自愈

> **模块**：Spike-3 碰撞检测  
> **优先级**：P0（用户体验核心）  
> **Go/No-Go 阈值**：100 Assets ≤100ms、增量 ≤20ms、自愈 ≤100ms、WS E2E ≤500ms  

### 3.1 已有测试用例

#### S3-TC01~TC03 — 全局碰撞检测性能

| 字段 | 内容 |
|------|------|
| **用例编号** | S3-TC01 / S3-TC02 / S3-TC03 |
| **名称** | R-Tree + Shapely 全局碰撞检测性能 (50/100/200 Assets) |
| **所属功能模块** | Spike-3 碰撞检测 |
| **版本** | v1.0 |
| **测试目的** | 验证不同规模 (50/100/200) Asset 布局下全局碰撞检测延迟 |
| **测试类型** | 性能 |
| **前置关联** | 无 |
| **前置条件** | Shapely、R-Tree 已安装；collision_test_data fixture 可用 |
| **测试数据** | `tier2_layout_assets.json`（碰撞场景数据）+ 随机生成 50/100/200 Assets |
| **通过条件设定** | 1. 50 Assets ≤ `Thresholds.S3_GLOBAL_50_MS` (50ms)<br>2. 100 Assets ≤ `Thresholds.S3_GLOBAL_100_MS` (100ms)<br>3. 200 Assets ≤ `Thresholds.S3_GLOBAL_200_MS` (200ms)<br>4. 碰撞结果结构完整 (含 asset_a/b/overlap)<br>5. 无自碰撞、无重复碰撞对<br>6. 性能取 5 次中位数（排除 1 次预热）<br>7. 子方法: `test_global_collision_latency` (参数化), `test_collision_result_structure`, `test_no_self_collision`, `test_no_duplicate_pairs` |

---

#### S3-TC04 — 增量碰撞检测

| 字段 | 内容 |
|------|------|
| **用例编号** | S3-TC04 |
| **名称** | 增量碰撞检测（单设备移动）性能验证 |
| **所属功能模块** | Spike-3 碰撞检测 |
| **版本** | v1.0 |
| **测试目的** | 验证单设备拖拽后的增量碰撞检测延迟，而非全局重算 |
| **测试类型** | 性能 |
| **前置关联** | S3-TC01 |
| **前置条件** | R-Tree 空间索引已构建 |
| **测试数据** | 100 Assets 布局 + 模拟移动 1 个 Asset |
| **通过条件设定** | 1. 延迟 ≤ `Thresholds.S3_INCREMENTAL_MS` (20ms)<br>2. 增量结果与全局结果一致（正确性）<br>3. 子方法: `test_tc04_incremental_latency`, `test_tc04_incremental_correctness` |

---

#### S3-TC05 — 自愈算法

| 字段 | 内容 |
|------|------|
| **用例编号** | S3-TC05 |
| **名称** | 碰撞自愈算法（推开碰撞设备）验证 |
| **所属功能模块** | Spike-3 碰撞检测 |
| **版本** | v1.0 |
| **测试目的** | 验证自愈算法在 ≤5 碰撞对时，能自动推开碰撞设备且计算耗时达标 |
| **测试类型** | 功能 + 性能 |
| **前置关联** | S3-TC01 |
| **前置条件** | 自愈算法模块可导入 |
| **测试数据** | 模拟 3~5 个碰撞对的布局 |
| **通过条件设定** | 1. 自愈耗时 ≤ `Thresholds.S3_HEAL_MS` (100ms)<br>2. 自愈后无残留碰撞<br>3. 位移量合理（≤ 设备最大尺寸的 2 倍）<br>4. 子方法: `test_tc05_heal_latency`, `test_tc05_heal_no_remaining_collision`, `test_tc05_heal_reasonable_displacement` |

---

#### S3-TC06 — 禁区/安全区侵入检测

| 字段 | 内容 |
|------|------|
| **用例编号** | S3-TC06 |
| **名称** | 禁区/安全区侵入检测性能验证 |
| **所属功能模块** | Spike-3 碰撞检测 |
| **版本** | v1.0 |
| **测试目的** | 验证 100 Assets + 10 禁区场景下侵入检测延迟和检出率 |
| **测试类型** | 性能 |
| **前置关联** | S3-TC01 |
| **前置条件** | 禁区 Polygon 数据可用 |
| **测试数据** | 100 Assets + 10 禁区 Polygon + tier2 禁区数据 |
| **通过条件设定** | 1. 检测延迟 ≤ `Thresholds.S3_EXCLUSION_MS` (50ms)<br>2. 检出所有侵入（无遗漏）<br>3. 支持 tier2 真实禁区数据<br>4. 子方法: `test_tc06_exclusion_latency`, `test_tc06_detect_all_intrusions`, `test_tc06_tier2_exclusion_zones` |

---

#### S3-TC07/TC08 — WebSocket 全链路

| 字段 | 内容 |
|------|------|
| **用例编号** | S3-TC07 / S3-TC08 |
| **名称** | WebSocket 全链路拖拽延迟验证 |
| **所属功能模块** | Spike-3 碰撞检测 |
| **版本** | v1.0 |
| **测试目的** | 验证前端拖拽 → BFF → Agent → 碰撞检测 → 自愈 → 返回的端到端延迟 |
| **测试类型** | 集成 + 性能 |
| **前置关联** | S3-TC04, S3-TC05 |
| **前置条件** | WebSocket Server 已启动 |
| **测试数据** | 100 Assets 场景 + 模拟连续拖拽 |
| **通过条件设定** | 1. TC07: 单次 drag→heal roundtrip ≤ `Thresholds.S3_WS_E2E_MS` (500ms)<br>2. TC08: 连续 100 次拖拽/10s 无消息丢失、无崩溃 (@slow)<br>3. 子方法: `test_tc07_drag_heal_roundtrip`, `test_tc08_continuous_drag_no_drop` |

---

#### S3-SPATIAL — 空间索引基础操作

| 字段 | 内容 |
|------|------|
| **用例编号** | S3-SPATIAL |
| **名称** | R-Tree / STR-Tree 空间索引基础操作验证 |
| **所属功能模块** | Spike-3 碰撞检测 |
| **版本** | v1.0 |
| **测试目的** | 验证空间索引的构建、查询邻居、动态更新基础功能 |
| **测试类型** | 功能 |
| **前置关联** | 无 |
| **前置条件** | Shapely STRtree 可用 |
| **测试数据** | 程序生成的几何对象集合 |
| **通过条件设定** | 1. 索引构建成功<br>2. 邻居查询结果正确<br>3. 索引更新后查询一致<br>4. 子方法: `test_build_index`, `test_query_neighbors`, `test_index_update` |

---

#### S3-L4 — Golden Baseline 精确碰撞验证

| 字段 | 内容 |
|------|------|
| **用例编号** | S3-L4 |
| **名称** | 已知几何 → 碰撞结果精确基线 |
| **所属功能模块** | Spike-3 碰撞检测 |
| **版本** | v1.0 |
| **测试目的** | 使用已知几何体验证碰撞检测结果的精确性（消除随机性） |
| **测试类型** | 精度 |
| **前置关联** | 无 |
| **前置条件** | 无 |
| **测试数据** | 程序化构造: 2 个重叠矩形、2 个不重叠矩形、边缘接触、安全区创建碰撞、3 个互相碰撞 |
| **通过条件设定** | 1. 重叠面积精确匹配<br>2. 不重叠检测结果为零<br>3. 边缘接触不算碰撞<br>4. 安全区扩展后正确创建碰撞<br>5. 三体互碰检出 3 对<br>6. 子方法: `test_two_overlapping_exact_area`, `test_non_overlapping_zero`, `test_touching_edges_no_collision`, `test_safety_zone_creates_collision`, `test_three_mutual_collisions` |

---

#### S3-PERF-STAT — 统计性能基线

| 字段 | 内容 |
|------|------|
| **用例编号** | S3-PERF-STAT |
| **名称** | 碰撞检测统计性能基线（中位数） |
| **所属功能模块** | Spike-3 碰撞检测 |
| **版本** | v1.0 |
| **测试目的** | 用 5 次运行中位数（排除 1 次预热）作为性能基线，降低波动影响 |
| **测试类型** | 性能 |
| **前置关联** | S3-TC01 |
| **前置条件** | `benchmark_median()` 工具函数可用（conftest.py） |
| **测试数据** | 100/200 Assets 参数化 + 增量检测 |
| **通过条件设定** | 1. 100 Assets 中位数 ≤ 100ms<br>2. 200 Assets 中位数 ≤ 200ms<br>3. 增量中位数 ≤ 20ms<br>4. 子方法: `test_global_collision_median` (参数化), `test_incremental_median` |

---

#### S3-AERO — 真实布局碰撞验证

| 字段 | 内容 |
|------|------|
| **用例编号** | S3-AERO |
| **名称** | Tier-2 真实航空布局数据碰撞检测 |
| **所属功能模块** | Spike-3 碰撞检测 |
| **版本** | v1.0 |
| **测试目的** | 使用 tier2 真实布局数据验证碰撞检测功能正确性 |
| **测试类型** | 功能 |
| **前置关联** | S3-TC01 |
| **前置条件** | `tier2_layout_assets.json` 存在 |
| **测试数据** | `tier2_layout_assets.json` — 含预定义碰撞场景 |
| **通过条件设定** | 1. tier2 数据碰撞检测成功<br>2. 预定义碰撞场景全部检出<br>3. 子方法: `test_detect_with_tier2_data`, `test_predefined_scenarios` |

---

## 四、Spike-4：SimPy DES 仿真精度与性能

> **模块**：Spike-4 DES 仿真  
> **优先级**：P1  
> **Go/No-Go 阈值**：确定性 JPH 误差 ≤1%、随机 JPH 误差 ≤5%、20 工站 ≤60s  

### 4.1 已有测试用例

#### S4-TC01 — 5 工站确定性仿真

| 字段 | 内容 |
|------|------|
| **用例编号** | S4-TC01 |
| **名称** | 5 工站串行确定性仿真 JPH 精度验证 |
| **所属功能模块** | Spike-4 DES 仿真 |
| **版本** | v1.0 |
| **测试目的** | 验证 OEE=1.0 下确定性仿真 JPH = 3600/max(cycle_time) 的精度 |
| **测试类型** | 精度 |
| **前置关联** | 无 |
| **前置条件** | SimPy 已安装 |
| **测试数据** | 5 工站配置: WS-1(30s), WS-2(25s), WS-3(35s 瓶颈), WS-4(28s), WS-5(20s)。理论 JPH = 3600/35 ≈ 102.86 |
| **通过条件设定** | 1. JPH 误差 ≤ `Thresholds.S4_DETERMINISTIC_ERROR_PCT` (1%)<br>2. 瓶颈正确识别为 WS-3<br>3. 稼动率一致性验证<br>4. 子方法: `test_tc01_5station_jph`, `test_tc01_bottleneck_is_ws3`, `test_tc01_utilization_consistency` |

---

#### S4-TC02 — 5 工站随机故障仿真

| 字段 | 内容 |
|------|------|
| **用例编号** | S4-TC02 |
| **名称** | 5 工站随机故障 JPH 精度验证（10 次均值） |
| **所属功能模块** | Spike-4 DES 仿真 |
| **版本** | v1.0 |
| **测试目的** | 验证加入 OEE=0.85 随机故障后 10 次运行均值 JPH 精度 |
| **测试类型** | 精度 |
| **前置关联** | S4-TC01 |
| **前置条件** | SimPy 已安装 |
| **测试数据** | 5 工站 + OEE=0.85, MTBF=100min, MTTR=10min；运行 10 次取均值 |
| **通过条件设定** | JPH 均值误差 ≤ `Thresholds.S4_STOCHASTIC_ERROR_PCT` (5%) |

---

#### S4-TC03~TC05 — 规模扩展性能

| 字段 | 内容 |
|------|------|
| **用例编号** | S4-TC03 / S4-TC04 / S4-TC05 |
| **名称** | 10/20/50 工站仿真耗时验证 |
| **所属功能模块** | Spike-4 DES 仿真 |
| **版本** | v1.0 |
| **测试目的** | 验证不同规模仿真的 wall-time 不超标 |
| **测试类型** | 性能 |
| **前置关联** | S4-TC01 |
| **前置条件** | SimPy 已安装 |
| **测试数据** | 10 工站 / 20 工站 / 50 工站配置 |
| **通过条件设定** | 1. 10 工站 ≤ `Thresholds.S4_10STATION_TIME_S` (30s)<br>2. 20 工站 ≤ `Thresholds.S4_20STATION_TIME_S` (60s)<br>3. 50 工站 ≤ `Thresholds.S4_50STATION_TIME_S` (180s) (@slow)<br>4. 子方法: `test_scale_time` (参数化 10/20), `test_50_station_scale` (@slow) |

---

#### S4-TC06 — 结果可复现性

| 字段 | 内容 |
|------|------|
| **用例编号** | S4-TC06 |
| **名称** | 固定 seed 仿真结果完全一致验证 |
| **所属功能模块** | Spike-4 DES 仿真 |
| **版本** | v1.0 |
| **测试目的** | 验证固定 random_seed 下多次运行结果完全一致 |
| **测试类型** | 功能 |
| **前置关联** | S4-TC01 |
| **前置条件** | 无 |
| **测试数据** | 任意工站配置 + seed=42，运行 3 次 |
| **通过条件设定** | 3 次 JPH 值完全一致 (identical) |

---

#### S4-TC07 — 瓶颈识别正确性

| 字段 | 内容 |
|------|------|
| **用例编号** | S4-TC07 |
| **名称** | 瓶颈工站识别正确性验证 |
| **所属功能模块** | Spike-4 DES 仿真 |
| **版本** | v1.0 |
| **测试目的** | 验证故意设置一个慢工站后系统能正确识别为瓶颈 |
| **测试类型** | 功能 |
| **前置关联** | S4-TC01 |
| **前置条件** | 瓶颈识别算法可用 |
| **测试数据** | 故意慢工站配置（cycle_time 远大于其他工站） |
| **通过条件设定** | 1. 最大 utilization 工站 = 故意设置的慢工站<br>2. 多指标（utilization + WIP + wait_time）均指向同一瓶颈<br>3. 子方法: `test_tc07_obvious_bottleneck`, `test_tc07_multiple_metrics` |

---

#### S4-AERO — 航空场景验证

| 字段 | 内容 |
|------|------|
| **用例编号** | S4-AERO |
| **名称** | simulation_scenarios.json 航空产线场景验证 |
| **所属功能模块** | Spike-4 DES 仿真 |
| **版本** | v1.0 |
| **测试目的** | 使用航空制造场景数据验证 6 工站确定性仿真 |
| **测试类型** | 功能 |
| **前置关联** | S4-TC01 |
| **前置条件** | `simulation_scenarios.json` 存在 |
| **测试数据** | `simulation_scenarios.json` — SIM-01 确定性 6 工站场景 |
| **通过条件设定** | 仿真完成，JPH 在理论范围内 |

---

#### S4-L4 — Golden Baseline 理论精确验证

| 字段 | 内容 |
|------|------|
| **用例编号** | S4-L4 |
| **名称** | 可解析计算的理论值精确验证 |
| **所属功能模块** | Spike-4 DES 仿真 |
| **版本** | v1.0 |
| **测试目的** | 用可手算的简单场景精确验证仿真引擎正确性 |
| **测试类型** | 精度 |
| **前置关联** | 无 |
| **前置条件** | 无 |
| **测试数据** | 1 工站 (cycle_time=36s → JPH=100) / 2 等速工站 / utilization sum |
| **通过条件设定** | 1. 单工站 JPH 精确 = 3600/cycle_time<br>2. 两等速工站 JPH = 3600/cycle_time<br>3. utilization 总和一致<br>4. 子方法: `test_single_station_exact_jph`, `test_two_equal_stations_jph`, `test_utilization_sum_consistent` |

---

## 五、Spike-5：LLM 工艺约束提取

> **模块**：Spike-5 LLM 提取  
> **优先级**：P1  
> **Go/No-Go 阈值**：Precision ≥0.80、Recall ≥0.70、source_ref ≥90%、幻觉率 ≤10%  

### 5.1 已有测试用例

#### S5-TC01 — SOP-A 约束提取

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-TC01 |
| **名称** | SOP-A 机翼蒙皮铣削约束提取 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证 ConstraintExtractor 对 12 条 Gold Standard 约束的提取准确率 |
| **测试类型** | 精度 |
| **前置关联** | 无 |
| **前置条件** | ConstraintExtractor + ExtractionEvaluator 模块可导入；LLM API 可用 |
| **测试数据** | `SOP_A_wing_skin_milling.md` — 12 条标注约束 (WLE-C01~C12), 0 矛盾 |
| **通过条件设定** | 1. Precision ≥ `Thresholds.S5_PRECISION` (0.80)<br>2. Recall ≥ `Thresholds.S5_RECALL` (0.70)<br>3. JSON 输出 100% 可解析<br>4. 子方法: `test_tc01_precision_recall`, `test_tc01_json_schema`, `test_tc01_constraint_ids` |

---

#### S5-TC02 — SOP-B 约束提取

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-TC02 |
| **名称** | SOP-B 机身壁板钻铆约束提取 + 矛盾检测 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证 18 条约束提取准确率 + 2 对矛盾检出能力 |
| **测试类型** | 精度 |
| **前置关联** | S5-TC01 |
| **前置条件** | ContradictionDetector 模块可导入 |
| **测试数据** | `SOP_B_fuselage_panel_riveting.md` — 18 条标注约束 (FSP-C01~C18), 2 矛盾 |
| **通过条件设定** | 1. Precision ≥ 0.80, Recall ≥ 0.70<br>2. 矛盾检出 ≥ 1 对<br>3. 子方法: `test_tc02_precision_recall`, `test_tc02_contradiction_detection` |

---

#### S5-TC03 — SOP-C 约束提取

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-TC03 |
| **名称** | SOP-C 总装翼身对接约束提取 + 3 矛盾检测 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证最大复杂度 SOP（25 条 + 3 矛盾）的提取能力 |
| **测试类型** | 精度 |
| **前置关联** | S5-TC01 |
| **前置条件** | 同上 |
| **测试数据** | `SOP_C_wing_body_join.md` — 25 条标注约束 (WBJ-C01~C25), 3 矛盾 |
| **通过条件设定** | 1. Precision ≥ 0.80, Recall ≥ 0.70<br>2. 矛盾检出 ≥ 2 对<br>3. 提取约束含 hard/soft 类型<br>4. 子方法: `test_tc03_precision_recall`, `test_tc03_contradiction_detection`, `test_tc03_constraint_types` |

---

#### S5-TC04 — source_ref 回溯

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-TC04 |
| **名称** | 约束 source_ref 原文回溯准确率 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证每条提取约束的 source_ref 可在原文中定位到对应段落 |
| **测试类型** | 精度 |
| **前置关联** | S5-TC01 ~ S5-TC03 |
| **前置条件** | 无 |
| **测试数据** | SOP_A/B/C.md — 参数化测试 |
| **通过条件设定** | 回溯准确率 ≥ `Thresholds.S5_SOURCE_REF_ACCURACY` (90%) |

---

#### S5-TC05 — Prompt 策略对比

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-TC05 |
| **名称** | 零样本 / 少样本 / CoT Prompt 策略对比 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 对比 3 种 Prompt 策略的 Precision/Recall，确定最优策略 |
| **测试类型** | 功能 |
| **前置关联** | S5-TC01 |
| **前置条件** | LLM API 可用 |
| **测试数据** | `SOP_A_wing_skin_milling.md` + 3 种 Prompt |
| **通过条件设定** | 1. 3 种策略均可产出结果<br>2. 最优策略 Precision ≥ 0.80<br>3. 子方法: `test_tc05_all_strategies_produce_output`, `test_tc05_best_strategy_above_threshold` |

---

#### S5-TC06 — 幻觉检测

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-TC06 |
| **名称** | LLM 提取幻觉率控制验证 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 统计 LLM 输出中非文档内容（幻觉）的比率 |
| **测试类型** | 精度 |
| **前置关联** | S5-TC01 |
| **前置条件** | 无 |
| **测试数据** | `SOP_A_wing_skin_milling.md` |
| **通过条件设定** | 幻觉率 ≤ `Thresholds.S5_HALLUCINATION_RATE` (10%) |

---

#### S5-TC07 — JSON 结构化输出

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-TC07 |
| **名称** | LLM 输出 ConstraintSet JSON 格式验证 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证 LLM 直接输出的 JSON 格式可被解析且 Schema 正确 |
| **测试类型** | 功能 |
| **前置关联** | 无 |
| **前置条件** | 无 |
| **测试数据** | SOP_A/B/C.md — 参数化 |
| **通过条件设定** | 1. JSON 100% 可解析<br>2. 每条约束含 id / type / rule / source_ref<br>3. 子方法: `test_tc07_json_parseable`, `test_tc07_constraint_schema` |

---

#### S5-L4 — Mock 确定性提取基线

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-L4 |
| **名称** | Mock LLM 确定性提取精确验证 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 用 Mock LLM 响应替代真实 API，验证评估管道本身的正确性 |
| **测试类型** | 功能 |
| **前置关联** | 无 |
| **前置条件** | 无（Mock 不依赖外部服务） |
| **测试数据** | MOCK_LLM_RESPONSE 字典（硬编码 12 条约束、0 矛盾） |
| **通过条件设定** | 1. Precision = 1.0, Recall = 1.0<br>2. 幻觉率 = 0<br>3. source_ref 全部有效<br>4. 子方法: `test_mock_perfect_precision_recall`, `test_mock_zero_hallucination`, `test_mock_source_ref_valid` |

---

### 5.2 新增测试用例（基于真实 FAA PDF）

#### S5-RT01-01 — FAA AC43-214 PDF 文本提取

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT01-01 |
| **名称** | FAA AC43-214 复合材料修复 PDF 文本提取 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证 PyMuPDF 对 21 页 FAA Advisory Circular 的文本提取能力 |
| **测试类型** | 功能 |
| **前置关联** | 无 |
| **前置条件** | PyMuPDF (fitz) 已安装；PDF 文件已下载 |
| **测试数据** | `FAA_AC43-214_Composite_Repair.pdf` — 21 页, 170 KB |
| **通过条件设定** | 1. 提取文本长度 > 5,000 字符<br>2. 文本含 "composite", "cure", "bond" 关键词 |

---

#### S5-RT01-02 — FAA AC21-26A PDF 文本提取

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT01-02 |
| **名称** | FAA AC21-26A 质量系统 PDF 文本提取 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证对含固化曲线/温度监控内容的 PDF 文本提取 |
| **测试类型** | 功能 |
| **前置关联** | 无 |
| **前置条件** | PyMuPDF 已安装 |
| **测试数据** | `FAA_AC21-26A_Quality_System.pdf` — 15 页, 2.4 MB |
| **通过条件设定** | 文本含 "temperature", "pressure", "process" 关键词 |

---

#### S5-RT01-03 — FAA AC43.13-1B 大文档文本提取

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT01-03 |
| **名称** | FAA AC43.13-1B 646 页大文档文本提取性能 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证对 646 页大文档的全文提取性能和完整性 |
| **测试类型** | 性能 |
| **前置关联** | 无 |
| **前置条件** | PyMuPDF 已安装 |
| **测试数据** | `FAA_AC43.13-1B_Inspection_Repair.pdf` — 646 页, 20.1 MB |
| **通过条件设定** | 1. 全文提取耗时 ≤ 60s<br>2. 文本总长度 > 500,000 字符 |

---

#### S5-RT01-04 — FAA AC145-10 PDF 文本提取

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT01-04 |
| **名称** | FAA AC145-10 维修站 PDF 文本提取 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证对含 repair/inspect/procedure 维修流程的文本提取 |
| **测试类型** | 功能 |
| **前置关联** | 无 |
| **前置条件** | PyMuPDF 已安装 |
| **测试数据** | `FAA_AC145-10_Repair_Station.pdf` — 41 页, 496 KB |
| **通过条件设定** | 文本含 "repair", "inspect", "procedure" 关键词 |

---

#### S5-RT01-05 — FAA AC21.303 PDF 文本提取

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT01-05 |
| **名称** | FAA AC21.303 零部件制造 PDF 文本提取 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证对含 manufacturing/approval/compliance 内容的文本提取 |
| **测试类型** | 功能 |
| **前置关联** | 无 |
| **前置条件** | PyMuPDF 已安装 |
| **测试数据** | `FAA_AC21.303_Parts_Manufacturing.pdf` — 32 页, 316 KB |
| **通过条件设定** | 文本含 "manufacturing", "approval", "compliance" 关键词 |

---

#### S5-RT02-01 — 真实 PDF 复合材料约束提取

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT02-01 |
| **名称** | FAA AC43-214 复合材料修复约束提取 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证 LLM 从真实 FAA 文档中提取铺层/固化/粘接约束的能力 |
| **测试类型** | 精度 |
| **前置关联** | S5-RT01-01, S5-TC01 |
| **前置条件** | ConstraintExtractor + LLM API 可用 |
| **测试数据** | `FAA_AC43-214_Composite_Repair.pdf` (21pp) |
| **通过条件设定** | 1. 输出 ConstraintSet，约束数 ≥ 5<br>2. 每条含 id/type/rule/source_ref<br>3. Precision ≥ `Thresholds.S5_PRECISION` (0.80) |

---

#### S5-RT02-02 — 真实 PDF 质量系统约束提取

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT02-02 |
| **名称** | FAA AC21-26A 质量系统参数约束提取 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证提取温度/压力/时间参数约束，含数值范围 |
| **测试类型** | 精度 |
| **前置关联** | S5-RT01-02 |
| **前置条件** | ConstraintExtractor + LLM API 可用 |
| **测试数据** | `FAA_AC21-26A_Quality_System.pdf` (15pp) |
| **通过条件设定** | 1. Recall ≥ `Thresholds.S5_RECALL` (0.70)<br>2. 约束含数值参数（温度/压力/时间） |

---

#### S5-RT02-03 — 真实 PDF 维修流程约束提取

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT02-03 |
| **名称** | FAA AC145-10 维修流程依赖关系提取 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证提取流程依赖 (ProcessGraph) 含步骤序列 |
| **测试类型** | 功能 |
| **前置关联** | S5-RT01-04 |
| **前置条件** | ConstraintExtractor + LLM API 可用 |
| **测试数据** | `FAA_AC145-10_Repair_Station.pdf` (41pp) |
| **通过条件设定** | 输出可解析 JSON，含流程依赖步骤 |

---

#### S5-RT02-04 — 大文档分块约束提取

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT02-04 |
| **名称** | FAA AC43.13-1B 646 页分块提取与合并 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证大文档分块提取策略：每块 ≤4000 token，去重合并 |
| **测试类型** | 功能 + 性能 |
| **前置关联** | S5-RT01-03 |
| **前置条件** | 分块 + LLM API 可用 |
| **测试数据** | `FAA_AC43.13-1B_Inspection_Repair.pdf` (646pp) |
| **通过条件设定** | 1. 合并后约束 ≥ 20 条<br>2. 每块 ≤ 4000 token |

---

#### S5-RT02-05 — 真实 PDF 制造审批约束提取

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT02-05 |
| **名称** | FAA AC21.303 多步骤审批流程提取 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证多步骤审批流程约束的结构化提取 |
| **测试类型** | 功能 |
| **前置关联** | S5-RT01-05 |
| **前置条件** | ConstraintExtractor + LLM API 可用 |
| **测试数据** | `FAA_AC21.303_Parts_Manufacturing.pdf` (32pp) |
| **通过条件设定** | 输出可解析 JSON |

---

#### S5-RT03-01 — 约束数值参数验证

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT03-01 |
| **名称** | 提取约束含数值参数(温度/压力/时间)验证 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证从 FAA 文档中提取的约束含量化工艺参数 |
| **测试类型** | 精度 |
| **前置关联** | S5-RT02-01 |
| **前置条件** | 无 |
| **测试数据** | S5-RT02-01 提取结果（基于 FAA_AC43-214） |
| **通过条件设定** | 至少 3 条约束含数值参数（温度°F/°C, 压力 psi, 时间 min/hr） |

---

#### S5-RT03-02 — 约束类型分布

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT03-02 |
| **名称** | hard/soft 约束类型分布合理性验证 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证提取结果中 hard/soft 约束分布合理（非全 hard 或全 soft） |
| **测试类型** | 功能 |
| **前置关联** | S5-RT02-02 |
| **前置条件** | 无 |
| **测试数据** | S5-RT02-02 提取结果（基于 FAA_AC21-26A） |
| **通过条件设定** | hard ≥ 30% 且 soft ≥ 20% |

---

#### S5-RT03-03 — source_ref 真实文本定位

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT03-03 |
| **名称** | 真实 PDF 约束 source_ref 原文段落定位 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证每条 source_ref 可在 PDF 原文中定位到对应段落 |
| **测试类型** | 精度 |
| **前置关联** | S5-RT02-01 |
| **前置条件** | 无 |
| **测试数据** | S5-RT02-01 提取结果 + FAA_AC43-214 原文 |
| **通过条件设定** | ≥ `Thresholds.S5_SOURCE_REF_ACCURACY` (90%) 可定位 |

---

#### S5-RT03-04 — 约束去重验证

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT03-04 |
| **名称** | 提取约束全局唯一性与逻辑去重 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证约束 ID 全局唯一，且无逻辑重复（规则文本相似度 < 0.9） |
| **测试类型** | 功能 |
| **前置关联** | S5-RT02-03 |
| **前置条件** | 无 |
| **测试数据** | S5-RT02-03 提取结果（基于 FAA_AC145-10） |
| **通过条件设定** | 0 条重复（ID 唯一 + 规则 similarity < 0.9） |

---

#### S5-RT04-01 — 铆接 ProcessGraph 提取

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT04-01 |
| **名称** | 铆接章节 ProcessGraph DAG 提取 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 从 FAA 铆接工艺章节提取 step 序列 DAG |
| **测试类型** | 功能 |
| **前置关联** | S5-RT02-04 |
| **前置条件** | ProcessGraph 数据结构已定义 |
| **测试数据** | `FAA_AC43.13-1B` Ch.3 铆接章节 |
| **通过条件设定** | 1. 步骤数 ≥ 3（钻孔→去毛刺→铆接→检验）<br>2. DAG 无环 |

---

#### S5-RT04-02 — 复合材料 ProcessGraph 提取

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT04-02 |
| **名称** | 复合材料修复 ProcessGraph DAG 提取 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 提取铺层→真空袋→固化→检验流程 + 温度/时间约束关联 |
| **测试类型** | 功能 |
| **前置关联** | S5-RT02-01 |
| **前置条件** | ProcessGraph 结构已定义 |
| **测试数据** | `FAA_AC43-214_Composite_Repair.pdf` |
| **通过条件设定** | 1. DAG 无环<br>2. 含温度/时间约束关联 |

---

#### S5-RT04-03 — ProcessGraph DAG 验证

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT04-03 |
| **名称** | ProcessGraph 拓扑排序与 DAG 合法性 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证提取的 ProcessGraph 可拓扑排序，无死锁/悬空节点 |
| **测试类型** | 功能 |
| **前置关联** | S5-RT04-01 或 S5-RT04-02 |
| **前置条件** | 无 |
| **测试数据** | 任意已提取的 ProcessGraph |
| **通过条件设定** | 拓扑排序可执行，无环无死锁 |

---

#### S5-RT04-04 — ProcessGraph 约束引用一致性

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT04-04 |
| **名称** | ProcessGraph 节点与 ConstraintSet 引用一致性 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证 ProcessGraph 节点引用的 constraint_id 在 ConstraintSet 中存在 |
| **测试类型** | 集成 |
| **前置关联** | S5-RT04-02, S5-RT02-01 |
| **前置条件** | 无 |
| **测试数据** | FAA_AC43-214 提取的 ProcessGraph + ConstraintSet |
| **通过条件设定** | 引用 constraint_id 100% 在 ConstraintSet 中 |

---

#### S5-RT05-01 — 646 页大文档分块

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT05-01 |
| **名称** | 646 页文档分块数量与 token 限制验证 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证大文档分块策略：块数 ≥10，每块 ≤4000 token |
| **测试类型** | 功能 |
| **前置关联** | S5-RT01-03 |
| **前置条件** | Chunking pipeline 已实现 |
| **测试数据** | `FAA_AC43.13-1B_Inspection_Repair.pdf` (646pp) |
| **通过条件设定** | 1. 分块数 ≥ 10<br>2. 每块 ≤ 4000 token<br>3. 无句中切断 |

---

#### S5-RT05-02 — 重叠区域去重

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT05-02 |
| **名称** | 分块重叠区域约束去重合并 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证滑动窗口重叠区域的约束不重复计数 |
| **测试类型** | 功能 |
| **前置关联** | S5-RT05-01 |
| **前置条件** | merge 去重逻辑已实现 |
| **测试数据** | `FAA_AC43.13-1B` 分块结果 |
| **通过条件设定** | merge 后约束 ID 全局唯一，0 重复 |

---

#### S5-RT05-03 — 单块提取耗时

| 字段 | 内容 |
|------|------|
| **用例编号** | S5-RT05-03 |
| **名称** | 单块 LLM 提取耗时验证 |
| **所属功能模块** | Spike-5 LLM 提取 |
| **版本** | v1.0 |
| **测试目的** | 验证单块提取时间（含 LLM API 网络延迟）不超标 |
| **测试类型** | 性能 |
| **前置关联** | S5-RT05-01 |
| **前置条件** | LLM API 可用 |
| **测试数据** | `FAA_AC43-214` 分块 |
| **通过条件设定** | 单块提取 ≤ 30s |

---

## 六、Spike-6：Temporal 工作流编排

> **模块**：Spike-6 Temporal 编排  
> **优先级**：P1  
> **Go/No-Go 阈值**：全链路成功 100%、重试 3 次内恢复、Worker 重启无数据丢失  

### 6.1 测试用例

> 注：Spike-6 测试文件当前仅含导入，测试类尚未实现。以下为基于 PRD 的设计。

#### S6-TC01 — 简单 3-step Workflow

| 字段 | 内容 |
|------|------|
| **用例编号** | S6-TC01 |
| **名称** | 简单 3-step 顺序 Workflow 执行 |
| **所属功能模块** | Spike-6 Temporal 编排 |
| **版本** | v1.0 |
| **测试目的** | 验证 parse → layout → report 三步 Workflow 顺序执行完成 |
| **测试类型** | 功能 |
| **前置关联** | 无 |
| **前置条件** | Temporal Server 已启动；Worker 已部署；Activity 已注册 |
| **测试数据** | 模拟 ParseDWGActivity / GenerateLayoutActivity / GenerateReportActivity |
| **通过条件设定** | Workflow 执行成功，返回包含 site_guid / layout_id / report_id 的结果 |

---

#### S6-TC02 — Activity 超时自动重试

| 字段 | 内容 |
|------|------|
| **用例编号** | S6-TC02 |
| **名称** | Activity 超时自动重试验证 |
| **所属功能模块** | Spike-6 Temporal 编排 |
| **版本** | v1.0 |
| **测试目的** | 验证 Activity 超时后 RetryPolicy 自动重试并最终成功 |
| **测试类型** | 异常 |
| **前置关联** | S6-TC01 |
| **前置条件** | RetryPolicy 配置 maximum_attempts=3 |
| **测试数据** | 模拟第 2 步超时的 Activity |
| **通过条件设定** | `Thresholds.S6_RETRY_MAX_ATTEMPTS` (3) 次内成功 |

---

#### S6-TC03 — Activity 永久失败

| 字段 | 内容 |
|------|------|
| **用例编号** | S6-TC03 |
| **名称** | Activity 永久失败 Workflow 可见错误 |
| **所属功能模块** | Spike-6 Temporal 编排 |
| **版本** | v1.0 |
| **测试目的** | 验证 Activity 永久异常时 Workflow 标记失败且错误可调试 |
| **测试类型** | 异常 |
| **前置关联** | S6-TC01 |
| **前置条件** | Temporal Server 可用 |
| **测试数据** | 模拟第 2 步持续异常的 Activity |
| **通过条件设定** | 1. Workflow 状态 = FAILED<br>2. 错误信息含异常描述<br>3. Temporal UI 可查看失败详情 |

---

#### S6-TC04 — 条件分支（瓶颈回写）

| 字段 | 内容 |
|------|------|
| **用例编号** | S6-TC04 |
| **名称** | 仿真瓶颈严重触发条件分支验证 |
| **所属功能模块** | Spike-6 Temporal 编排 |
| **版本** | v1.0 |
| **测试目的** | 验证仿真结果 bottleneck_severity=high 时触发约束回写 + 重新布局 |
| **测试类型** | 功能 |
| **前置关联** | S6-TC01, S4-TC07 |
| **前置条件** | FullPipelineWorkflow 含条件分支逻辑 |
| **测试数据** | 仿真返回 bottleneck_severity="high" |
| **通过条件设定** | 1. 条件分支正确触发<br>2. 重新布局 Activity 被调用<br>3. 最终报告包含更新后的 layout_id |

---

#### S6-TC05 — 并行 Activity

| 字段 | 内容 |
|------|------|
| **用例编号** | S6-TC05 |
| **名称** | 并行 Activity 执行验证 |
| **所属功能模块** | Spike-6 Temporal 编排 |
| **版本** | v1.0 |
| **测试目的** | 验证同时调 2 个独立 Agent Activity 时可并行执行 |
| **测试类型** | 性能 |
| **前置关联** | S6-TC01 |
| **前置条件** | Temporal Worker 配置 concurrent_activity_count > 1 |
| **测试数据** | 2 个独立 Activity（各耗时 3s） |
| **通过条件设定** | 总耗时 ≈ 较慢的那个 Activity（≤ 1.5 × max(单个)），非串行 |

---

#### S6-TC06 — Workflow 版本控制

| 字段 | 内容 |
|------|------|
| **用例编号** | S6-TC06 |
| **名称** | Workflow 新旧版本共存验证 |
| **所属功能模块** | Spike-6 Temporal 编排 |
| **版本** | v1.0 |
| **测试目的** | 验证部署新版 Workflow 后旧版正在运行的实例不受影响 |
| **测试类型** | 兼容性 |
| **前置关联** | S6-TC01 |
| **前置条件** | Temporal 版本化部署支持 |
| **测试数据** | V1 Workflow (运行中) + V2 Workflow (新部署) |
| **通过条件设定** | 1. V1 继续运行完成<br>2. 新启动的实例使用 V2 |

---

#### S6-TC07 — Worker 重启恢复

| 字段 | 内容 |
|------|------|
| **用例编号** | S6-TC07 |
| **名称** | Worker 进程重启 Workflow 恢复执行验证 |
| **所属功能模块** | Spike-6 Temporal 编排 |
| **版本** | v1.0 |
| **测试目的** | 验证杀 Worker 进程再重启后挂起的 Workflow 恢复执行 |
| **测试类型** | 异常 |
| **前置关联** | S6-TC01 |
| **前置条件** | Temporal Server 持久化存储可用 |
| **测试数据** | 运行中的 Workflow + Worker kill 信号 |
| **通过条件设定** | 1. Worker 重启后 Workflow 继续执行<br>2. 无数据丢失<br>3. 已完成的 Activity 不重复执行 |

---

#### S6-TC08 — Heartbeat 进度上报

| 字段 | 内容 |
|------|------|
| **用例编号** | S6-TC08 |
| **名称** | 长时 Activity Heartbeat 进度上报 |
| **所属功能模块** | Spike-6 Temporal 编排 |
| **版本** | v1.0 |
| **测试目的** | 验证长时仿真 Activity 的 heartbeat 进度百分比前端可查询 |
| **测试类型** | 功能 |
| **前置关联** | S6-TC01 |
| **前置条件** | heartbeat_timeout 已配置 |
| **测试数据** | 模拟 RunDESActivity 上报 10%~100% |
| **通过条件设定** | 进度百分比可通过 Temporal API 查询 |

---

## 七、Spike-7：3D 渲染与实时交互

> **模块**：Spike-7 3D 渲染  
> **优先级**：P1  
> **Go/No-Go 阈值**：200 Assets FPS ≥30、首屏 ≤3s  

### 7.1 已有测试用例

#### S7-TC01 — 50 Assets 场景数据生成

| 字段 | 内容 |
|------|------|
| **用例编号** | S7-TC01 |
| **名称** | 50 Assets 场景 JSON 数据生成 |
| **所属功能模块** | Spike-7 3D 渲染 |
| **版本** | v1.0 |
| **测试目的** | 验证后端生成 50 Assets 场景 JSON 供前端 Three.js 渲染 |
| **测试类型** | 功能 |
| **前置关联** | 无 |
| **前置条件** | SceneDataGenerator 模块可导入 |
| **测试数据** | 程序生成 50 Assets 布局 |
| **通过条件设定** | 1. 场景 JSON 含 50 个 asset 对象<br>2. 每个 asset 含 position/rotation/scale/geometry_type<br>3. JSON 可序列化 |

---

#### S7-TC02 — 200 Assets 场景数据生成

| 字段 | 内容 |
|------|------|
| **用例编号** | S7-TC02 |
| **名称** | 200 Assets 场景 JSON 数据生成（InstancedMesh 优化） |
| **所属功能模块** | Spike-7 3D 渲染 |
| **版本** | v1.0 |
| **测试目的** | 验证大规模场景数据生成能力 |
| **测试类型** | 功能 + 性能 |
| **前置关联** | S7-TC01 |
| **前置条件** | 同上 |
| **测试数据** | 程序生成 200 Assets 布局 |
| **通过条件设定** | 1. 场景 JSON 含 200 个 asset 对象<br>2. JSON 可序列化<br>3. 预期前端 FPS ≥ `Thresholds.S7_FPS_200_ASSETS` (30) |

---

#### S7-TC04 — 碰撞高亮数据

| 字段 | 内容 |
|------|------|
| **用例编号** | S7-TC04 |
| **名称** | 碰撞高亮 payload 数据生成 |
| **所属功能模块** | Spike-7 3D 渲染 |
| **版本** | v1.0 |
| **测试目的** | 验证碰撞检测结果生成红色高亮 payload 数据 |
| **测试类型** | 功能 |
| **前置关联** | S3-TC01 |
| **前置条件** | CollisionHighlightGenerator 可导入 |
| **测试数据** | 碰撞对 GUID 列表 |
| **通过条件设定** | 1. highlight payload 含碰撞 asset GUIDs<br>2. 含 color/opacity 渲染属性 |

---

#### S7-TC05 — 障碍物/禁区覆盖数据

| 字段 | 内容 |
|------|------|
| **用例编号** | S7-TC05 |
| **名称** | 禁区半透明覆盖 overlay 数据生成 |
| **所属功能模块** | Spike-7 3D 渲染 |
| **版本** | v1.0 |
| **测试目的** | 验证禁区 Polygon 生成半透明覆盖 overlay 数据 |
| **测试类型** | 功能 |
| **前置关联** | S3-TC06 |
| **前置条件** | ExclusionZoneOverlayGenerator 可导入 |
| **测试数据** | 禁区 Polygon 列表 |
| **通过条件设定** | overlay 含 polygon 坐标 + opacity < 1.0 |

---

#### S7-TC06 — 2D/3D 切换相机配置

| 字段 | 内容 |
|------|------|
| **用例编号** | S7-TC06 |
| **名称** | 正交/透视相机配置切换 |
| **所属功能模块** | Spike-7 3D 渲染 |
| **版本** | v1.0 |
| **测试目的** | 验证 2D(正交) / 3D(透视) 视角切换的相机参数正确性 |
| **测试类型** | 功能 |
| **前置关联** | 无 |
| **前置条件** | CameraConfigGenerator 可导入 |
| **测试数据** | 无 |
| **通过条件设定** | 1. 正交模式: projection = "orthographic"<br>2. 透视模式: projection = "perspective", fov > 0<br>3. 子方法: `test_tc06_orthographic_config`, `test_tc06_perspective_config` |

---

#### S7-L4 — Golden Baseline 精确 JSON 结构

| 字段 | 内容 |
|------|------|
| **用例编号** | S7-L4 |
| **名称** | 已知资产 → 精确 JSON 结构基线 |
| **所属功能模块** | Spike-7 3D 渲染 |
| **版本** | v1.0 |
| **测试目的** | 用已知资产验证生成 JSON 结构的精确性 |
| **测试类型** | 精度 |
| **前置关联** | 无 |
| **前置条件** | 无 |
| **测试数据** | 2 个已知 asset、已知碰撞 GUID、已知禁区 |
| **通过条件设定** | 1. 2 assets → 精确 JSON 结构匹配<br>2. highlight GUIDs 精确匹配<br>3. overlay geometry_type 匹配<br>4. 子方法: `test_two_assets_exact_structure`, `test_highlight_exact_guids`, `test_overlay_geometry_type_matches_zone` |

---

## 八、Spike-8：PINN 代理模型加速

> **模块**：Spike-8 PINN  
> **优先级**：P2（V1.0 阶段，PoC 不阻塞）  
> **Go/No-Go 阈值**：推理误差 ≤10% MAE、推理延迟 ≤100ms  

### 8.1 已有测试用例

#### S8-TC01 — 训练数据生成

| 字段 | 内容 |
|------|------|
| **用例编号** | S8-TC01 |
| **名称** | SimPy 训练数据集生成 |
| **所属功能模块** | Spike-8 PINN |
| **版本** | v1.0 |
| **测试目的** | 验证 SimPy 可批量运行 100/500 次生成 (input, output) 训练数据集 |
| **测试类型** | 功能 |
| **前置关联** | S4-TC01 |
| **前置条件** | SimPy 已安装 |
| **测试数据** | 参数化 100/500 samples 配置 |
| **通过条件设定** | 数据集生成成功，含 input_features / output_labels |

---

#### S8-TC02 — PINN 模型训练

| 字段 | 内容 |
|------|------|
| **用例编号** | S8-TC02 |
| **名称** | PyTorch PINN 模型训练收敛验证 |
| **所属功能模块** | Spike-8 PINN |
| **版本** | v1.0 |
| **测试目的** | 验证 5 工站 PINN 模型训练可收敛 |
| **测试类型** | 功能 |
| **前置关联** | S8-TC01 |
| **前置条件** | PyTorch 已安装；GPU 可用 (@gpu @slow) |
| **测试数据** | S8-TC01 生成的训练数据集 |
| **通过条件设定** | 训练 loss 收敛（最终 loss < 初始 loss × 0.1） |

---

#### S8-TC03 — PINN 推理精度

| 字段 | 内容 |
|------|------|
| **用例编号** | S8-TC03 |
| **名称** | PINN 推理精度 vs SimPy 真值 |
| **所属功能模块** | Spike-8 PINN |
| **版本** | v1.0 |
| **测试目的** | 验证 PINN 推理 JPH 与 SimPy 仿真真值的误差 |
| **测试类型** | 精度 |
| **前置关联** | S8-TC02 |
| **前置条件** | 训练好的 PINN 模型 |
| **测试数据** | 分布内测试集 |
| **通过条件设定** | 推理误差 ≤ `Thresholds.S8_INFERENCE_ERROR_PCT` (10%) MAE |

---

#### S8-TC04 — PINN 推理速度

| 字段 | 内容 |
|------|------|
| **用例编号** | S8-TC04 |
| **名称** | 单次 PINN 推理延迟验证 |
| **所属功能模块** | Spike-8 PINN |
| **版本** | v1.0 |
| **测试目的** | 验证 PINN 推理延迟远低于 SimPy 运行时间 |
| **测试类型** | 性能 |
| **前置关联** | S8-TC02 |
| **前置条件** | 训练好的 PINN 模型 |
| **测试数据** | 单次推理输入 |
| **通过条件设定** | 推理延迟 ≤ `Thresholds.S8_INFERENCE_LATENCY_MS` (100ms) |

---

#### S8-TC05 — 分布外泛化

| 字段 | 内容 |
|------|------|
| **用例编号** | S8-TC05 |
| **名称** | PINN 分布外 (OOD) 输入泛化验证 |
| **所属功能模块** | Spike-8 PINN |
| **版本** | v1.0 |
| **测试目的** | 验证输入偏离训练分布 20% 时推理误差可控 |
| **测试类型** | 精度 |
| **前置关联** | S8-TC02 |
| **前置条件** | 训练好的 PINN 模型 |
| **测试数据** | 训练分布 ±20% 的测试集 |
| **通过条件设定** | OOD 误差 ≤ `Thresholds.S8_OOD_ERROR_PCT` (20%) |

---

#### S8-L4 — 解析函数精确拟合

| 字段 | 内容 |
|------|------|
| **用例编号** | S8-L4 |
| **名称** | 已知线性/常数函数精确拟合基线 |
| **所属功能模块** | Spike-8 PINN |
| **版本** | v1.0 |
| **测试目的** | 用可解析的简单函数验证 PINN 训练管道本身的正确性 |
| **测试类型** | 精度 |
| **前置关联** | 无 |
| **前置条件** | PyTorch 可用 |
| **测试数据** | y = 2x + 1（线性）/ y = 5（常数） |
| **通过条件设定** | 1. 线性函数拟合误差 < 1%<br>2. 常数函数拟合误差 < 1%<br>3. 子方法: `test_linear_function_exact_fit`, `test_constant_function` |

---

## 九、Spike-9：RAG 知识检索

> **模块**：Spike-9 RAG 检索  
> **优先级**：P2  
> **Go/No-Go 阈值**：Recall@5 ≥0.80、检索延迟 ≤500ms  

### 9.1 已有测试用例

#### S9-TC01 — 文档向量化入库

| 字段 | 内容 |
|------|------|
| **用例编号** | S9-TC01 |
| **名称** | 行业规范文档向量化入库 |
| **所属功能模块** | Spike-9 RAG 检索 |
| **版本** | v1.0 |
| **测试目的** | 验证文档分块 + Embedding + 写入向量数据库的完整流程 |
| **测试类型** | 功能 |
| **前置关联** | 无 |
| **前置条件** | Milvus/Chroma 可用；Embedding 模型已加载 |
| **测试数据** | `spike_09_rag/test_data/*.md` — 行业规范文档 |
| **通过条件设定** | 1. 所有文档成功入库<br>2. 每个 chunk 含 metadata（doc_id/section/page）<br>3. 子方法: `test_tc01_ingest_all_documents`, `test_tc01_chunk_metadata` |

---

#### S9-TC02 — 精确查询

| 字段 | 内容 |
|------|------|
| **用例编号** | S9-TC02 |
| **名称** | 精确查询 Top-5 命中验证 |
| **所属功能模块** | Spike-9 RAG 检索 |
| **版本** | v1.0 |
| **测试目的** | 验证精确关键词查询能在 Top-5 中命中正确文档 |
| **测试类型** | 精度 |
| **前置关联** | S9-TC01 |
| **前置条件** | 文档已入库 |
| **测试数据** | 查询: "焊接车间最小安全距离" |
| **通过条件设定** | Top-5 结果含正确条款 |

---

#### S9-TC03 — 模糊查询

| 字段 | 内容 |
|------|------|
| **用例编号** | S9-TC03 |
| **名称** | 模糊查询 Top-5 相关性验证 |
| **所属功能模块** | Spike-9 RAG 检索 |
| **版本** | v1.0 |
| **测试目的** | 验证模糊/近义词查询能找到语义相关的文档 |
| **测试类型** | 精度 |
| **前置关联** | S9-TC01 |
| **前置条件** | 文档已入库 |
| **测试数据** | 查询: "喷涂区域通风要求" |
| **通过条件设定** | Top-5 结果含相关条款 |

---

#### S9-TC04 — 混合检索性能

| 字段 | 内容 |
|------|------|
| **用例编号** | S9-TC04 |
| **名称** | 向量 + BM25 混合检索延迟验证 |
| **所属功能模块** | Spike-9 RAG 检索 |
| **版本** | v1.0 |
| **测试目的** | 验证混合检索策略的延迟不超标 |
| **测试类型** | 性能 |
| **前置关联** | S9-TC01 |
| **前置条件** | 混合检索引擎已配置 |
| **测试数据** | 任意查询 |
| **通过条件设定** | 检索延迟 ≤ `Thresholds.S9_LATENCY_MS` (500ms) |

---

#### S9-TC05 — 中文分块质量

| 字段 | 内容 |
|------|------|
| **用例编号** | S9-TC05 |
| **名称** | RecursiveCharacterTextSplitter 中文分块质量 |
| **所属功能模块** | Spike-9 RAG 检索 |
| **版本** | v1.0 |
| **测试目的** | 验证中文文档分块无句中截断 |
| **测试类型** | 功能 |
| **前置关联** | 无 |
| **前置条件** | LangChain TextSplitter 可用 |
| **测试数据** | 中文行业规范文档 |
| **通过条件设定** | 无句中截断（每个 chunk 末尾为完整句号/问号/叹号） |

---

#### S9-TC06 — Recall@5 评估

| 字段 | 内容 |
|------|------|
| **用例编号** | S9-TC06 |
| **名称** | 20 个预标注 Query Recall@5 评估 |
| **所属功能模块** | Spike-9 RAG 检索 |
| **版本** | v1.0 |
| **测试目的** | 用人工标注的 20 个 Query→正确文档映射评估 Recall@5 |
| **测试类型** | 精度 |
| **前置关联** | S9-TC01 |
| **前置条件** | ANNOTATED_QUERIES 标注数据已准备 |
| **测试数据** | 20 个预标注查询 (query → relevant_docs → sections) |
| **通过条件设定** | Recall@5 ≥ `Thresholds.S9_RECALL_AT_5` (0.80) |

---

#### S9-L4 — Mock Embedding 精确排序

| 字段 | 内容 |
|------|------|
| **用例编号** | S9-L4 |
| **名称** | Mock Embedding 确定性排序验证 |
| **所属功能模块** | Spike-9 RAG 检索 |
| **版本** | v1.0 |
| **测试目的** | 用 Mock Embedding 替代真实模型，验证检索管道排序逻辑正确性 |
| **测试类型** | 功能 |
| **前置关联** | 无 |
| **前置条件** | 无（Mock 不依赖外部服务） |
| **测试数据** | 硬编码 embedding 向量 |
| **通过条件设定** | 1. 排序结果与预期精确匹配<br>2. score 排序正确<br>3. 子方法: `test_exact_ranking_with_mock`, `test_mock_score_ordering` |

---

#### S9-PERF-STAT — 检索延迟统计

| 字段 | 内容 |
|------|------|
| **用例编号** | S9-PERF-STAT |
| **名称** | 检索延迟统计中位数基线 |
| **所属功能模块** | Spike-9 RAG 检索 |
| **版本** | v1.0 |
| **测试目的** | 取 5 次运行中位数作为性能基线 |
| **测试类型** | 性能 |
| **前置关联** | S9-TC04 |
| **前置条件** | `benchmark_median()` 可用 |
| **测试数据** | 标准查询 |
| **通过条件设定** | 中位数延迟 ≤ `Thresholds.S9_LATENCY_MS` (500ms) |

---

## 十、Spike-10：PDF/Word 报告生成

> **模块**：Spike-10 报告生成  
> **优先级**：P2  
> **Go/No-Go 阈值**：PDF 含表格+中文 100%、中文无乱码、50 页 ≤30s  

### 10.1 已有测试用例

#### S10-TC01 — 简单 PDF 生成

| 字段 | 内容 |
|------|------|
| **用例编号** | S10-TC01 |
| **名称** | Jinja2 + WeasyPrint 简单 PDF 生成 |
| **所属功能模块** | Spike-10 报告生成 |
| **版本** | v1.0 |
| **测试目的** | 验证基础 PDF 生成能力：模板渲染 + 输出文件 |
| **测试类型** | 功能 |
| **前置关联** | 无 |
| **前置条件** | WeasyPrint + Jinja2 已安装；`layout_review_report.md` 模板存在 |
| **测试数据** | `report_template` fixture + `sample_report_data` fixture |
| **通过条件设定** | 1. PDF 文件生成成功（大小 > 0）<br>2. 模板渲染无未替换变量<br>3. 子方法: `test_tc01_generate_pdf`, `test_tc01_template_rendering` |

---

#### S10-TC02 — 含表格 PDF

| 字段 | 内容 |
|------|------|
| **用例编号** | S10-TC02 |
| **名称** | 含 ROI 表 / 方案对比表的 PDF 生成 |
| **所属功能模块** | Spike-10 报告生成 |
| **版本** | v1.0 |
| **测试目的** | 验证 PDF 中表格排版正确，行列对齐 |
| **测试类型** | 功能 |
| **前置关联** | S10-TC01 |
| **前置条件** | 无 |
| **测试数据** | 含表格数据的 sample_report_data |
| **通过条件设定** | 表格排版正确，可提取行/列数据 |

---

#### S10-TC03 — 含图表 PDF

| 字段 | 内容 |
|------|------|
| **用例编号** | S10-TC03 |
| **名称** | ECharts 图表截图嵌入 PDF |
| **所属功能模块** | Spike-10 报告生成 |
| **版本** | v1.0 |
| **测试目的** | 验证图表图片可嵌入 PDF 且清晰可读 |
| **测试类型** | 功能 |
| **前置关联** | S10-TC01 |
| **前置条件** | 图表生成模块可用 |
| **测试数据** | 图表 PNG/SVG |
| **通过条件设定** | 图片成功嵌入 PDF，分辨率清晰 |

---

#### S10-TC04 — 中文排版

| 字段 | 内容 |
|------|------|
| **用例编号** | S10-TC04 |
| **名称** | 中文字体排版与换行验证 |
| **所属功能模块** | Spike-10 报告生成 |
| **版本** | v1.0 |
| **测试目的** | 验证 PDF 中文渲染无乱码，长文本换行正确 |
| **测试类型** | 功能 |
| **前置关联** | S10-TC01 |
| **前置条件** | 中文字体 (Noto Sans CJK / 思源黑体) 已安装 |
| **测试数据** | 含中文标题、段落、表格的 report data |
| **通过条件设定** | 1. 无乱码（提取文本可读）<br>2. 长文本换行正确（无溢出）<br>3. 子方法: `test_tc04_no_garbled_text`, `test_tc04_long_text_wrapping` |

---

#### S10-TC05 — Word 文档输出

| 字段 | 内容 |
|------|------|
| **用例编号** | S10-TC05 |
| **名称** | python-docx Word 文档生成与章节验证 |
| **所属功能模块** | Spike-10 报告生成 |
| **版本** | v1.0 |
| **测试目的** | 验证 Word 格式输出与章节结构 |
| **测试类型** | 功能 |
| **前置关联** | S10-TC01 |
| **前置条件** | python-docx 已安装 |
| **测试数据** | sample_report_data |
| **通过条件设定** | 1. .docx 文件生成成功<br>2. 包含预期章节 (Heading1/Heading2)<br>3. 子方法: `test_tc05_generate_word`, `test_tc05_word_contains_sections` |

---

#### S10-TC06 — Excel 输出

| 字段 | 内容 |
|------|------|
| **用例编号** | S10-TC06 |
| **名称** | openpyxl Excel ROI 表与公式验证 |
| **所属功能模块** | Spike-10 报告生成 |
| **版本** | v1.0 |
| **测试目的** | 验证 Excel 输出含正确数据 + 可计算公式 |
| **测试类型** | 功能 |
| **前置关联** | 无 |
| **前置条件** | openpyxl 已安装 |
| **测试数据** | ROI 计算数据 |
| **通过条件设定** | 1. .xlsx 文件生成成功<br>2. 含公式单元格（如 SUM）<br>3. 子方法: `test_tc06_generate_excel`, `test_tc06_formulas_present` |

---

#### S10-TC07 — 50 页大报告性能

| 字段 | 内容 |
|------|------|
| **用例编号** | S10-TC07 |
| **名称** | 50 页大报告 PDF 生成耗时验证 |
| **所属功能模块** | Spike-10 报告生成 |
| **版本** | v1.0 |
| **测试目的** | 验证大报告生成耗时不超标 |
| **测试类型** | 性能 |
| **前置关联** | S10-TC01 |
| **前置条件** | 无 |
| **测试数据** | 含 50 页内容的 report data |
| **通过条件设定** | 1. 生成耗时 ≤ `Thresholds.S10_LARGE_REPORT_TIME_S` (30s)<br>2. PDF 页数 = 50 (@slow) |

---

#### S10-L4 — Golden Baseline 精确内容验证

| 字段 | 内容 |
|------|------|
| **用例编号** | S10-L4 |
| **名称** | PDF/Word 内容精确验证基线 |
| **所属功能模块** | Spike-10 报告生成 |
| **版本** | v1.0 |
| **测试目的** | 用已知输入验证输出文档内容的精确性 |
| **测试类型** | 精度 |
| **前置关联** | 无 |
| **前置条件** | PyMuPDF (PDF 文本提取) 可用 |
| **测试数据** | 硬编码输入数据 |
| **通过条件设定** | 1. PDF 含预期精确文本<br>2. 表格行数精确匹配<br>3. Word 段落精确匹配<br>4. 子方法: `test_pdf_contains_exact_text`, `test_table_row_count`, `test_word_paragraph_exact` |

---

## 十一、跨 Spike 集成测试

> **模块**：跨 Spike 集成  
> **优先级**：P1（Sprint 3）  

### 11.1 集成测试用例

#### INT-01 — S1→S3: 底图解析→碰撞检测

| 字段 | 内容 |
|------|------|
| **用例编号** | INT-01 |
| **名称** | 木工车间底图→碰撞检测端到端 |
| **所属功能模块** | 集成：Spike-1 + Spike-3 |
| **版本** | v1.0 |
| **测试目的** | 验证从 DXF 解析→SiteModel→Asset footprint→碰撞检测的完整链路 |
| **测试类型** | 集成 |
| **前置关联** | S1-RT01-01, S3-TC01 |
| **前置条件** | DWGParser + CollisionEngine 模块均可导入 |
| **测试数据** | `woodworking_plant.dxf` → equipment 层 202 个 INSERT 块 |
| **通过条件设定** | 1. 从 equipment 层提取 asset footprint 成功<br>2. 输入碰撞引擎无崩溃 |

---

#### INT-02 — S1→S3: 真实布局碰撞性能

| 字段 | 内容 |
|------|------|
| **用例编号** | INT-02 |
| **名称** | 真实布局 INSERT 块→碰撞对检测 |
| **所属功能模块** | 集成：Spike-1 + Spike-3 |
| **版本** | v1.0 |
| **测试目的** | 验证真实工业 INSERT 块引用→asset bounding box→碰撞检测性能 |
| **测试类型** | 集成 + 性能 |
| **前置关联** | INT-01 |
| **前置条件** | 同上 |
| **测试数据** | `woodworking_plant.dxf` — 202 INSERT 块 |
| **通过条件设定** | 碰撞检测延迟 ≤ 100ms |

---

#### INT-03 — S1→S4: 底图解析→DES 仿真

| 字段 | 内容 |
|------|------|
| **用例编号** | INT-03 |
| **名称** | 冷轧钢 DIMENSION 标注→仿真拓扑构建 |
| **所属功能模块** | 集成：Spike-1 + Spike-4 |
| **版本** | v1.0 |
| **测试目的** | 验证从 DIMENSION 标注提取工站间距并构建仿真拓扑 |
| **测试类型** | 集成 |
| **前置关联** | S1-RT04-02, S4-TC01 |
| **前置条件** | DWGParser + SimPy 模块均可导入 |
| **测试数据** | `cold_rolled_steel_production.dxf` — 45 个 DIMENSION |
| **通过条件设定** | 站间距 > 0，仿真拓扑可构建 |

---

#### INT-04 — S1→S4: 图层→工站数量

| 字段 | 内容 |
|------|------|
| **用例编号** | INT-04 |
| **名称** | 鱼加工厂 techno 层→工站数量提取 |
| **所属功能模块** | 集成：Spike-1 + Spike-4 |
| **版本** | v1.0 |
| **测试目的** | 验证从 techno 1/2/3 图层实体推导工站数量 |
| **测试类型** | 集成 |
| **前置关联** | S1-RT01-04, S4-TC01 |
| **前置条件** | 同上 |
| **测试数据** | `fish_processing_plant.dxf` — techno 1/2/3 层 |
| **通过条件设定** | 提取工站数 ≥ 2 |

---

#### INT-05 — S5→S3: 约束提取→禁区几何

| 字段 | 内容 |
|------|------|
| **用例编号** | INT-05 |
| **名称** | FAA 约束→排斥区 Polygon 生成 |
| **所属功能模块** | 集成：Spike-5 + Spike-3 |
| **版本** | v1.0 |
| **测试目的** | 验证 hard 约束 "minimum clearance" 转换为 exclusion zone polygon |
| **测试类型** | 集成 |
| **前置关联** | S5-RT02-01, S3-TC06 |
| **前置条件** | ConstraintExtractor + ExclusionZoneGenerator 可导入 |
| **测试数据** | FAA PDF → ConstraintSet → 禁区 polygon |
| **通过条件设定** | exclusion zone 面积 > 0 |

---

#### INT-06 — S1+S5→S10: 底图+约束→报告

| 字段 | 内容 |
|------|------|
| **用例编号** | INT-06 |
| **名称** | 底图+约束→布局评审 PDF 报告 |
| **所属功能模块** | 集成：Spike-1 + Spike-5 + Spike-10 |
| **版本** | v1.0 |
| **测试目的** | 验证 SiteModel + ConstraintSet 数据可生成包含图层统计表 + 约束列表的 PDF 报告 |
| **测试类型** | 集成 |
| **前置关联** | S1-RT07-01, S5-TC01, S10-TC02 |
| **前置条件** | 三个模块均可导入 |
| **测试数据** | woodworking SiteModel + SOP_A ConstraintSet |
| **通过条件设定** | 1. PDF 报告生成成功<br>2. 含图层统计表（≥1 行）<br>3. 含约束列表（≥1 条）<br>4. 表格可读 |

---

## 附录 A：测试用例汇总统计

| Spike | 模块 | 已有用例 | 新增用例 | 合计 |
|-------|------|---------|---------|------|
| Spike-1 | DWG/DXF 底图解析 | 7 (S1-TC01~TC06, RW01, EDGE01) | 26 (RT01~RT07) | 33 |
| Spike-2 | MCP 通信 | 1 (S2-TC06) | 0 | 1 |
| Spike-3 | 碰撞检测 | 9 (TC01~TC08, SPATIAL, L4, PERF-STAT, AERO) | 0 | 9 |
| Spike-4 | DES 仿真 | 7 (TC01~TC07, AERO, L4) | 0 | 7 |
| Spike-5 | LLM 提取 | 8 (TC01~TC07, L4) | 21 (RT01~RT05) | 29 |
| Spike-6 | Temporal 编排 | 0 | 8 (TC01~TC08) | 8 |
| Spike-7 | 3D 渲染 | 5 (TC01~TC06, L4) | 0 | 5 |
| Spike-8 | PINN | 6 (TC01~TC05, L4) | 0 | 6 |
| Spike-9 | RAG 检索 | 8 (TC01~TC06, L4, PERF-STAT) | 0 | 8 |
| Spike-10 | 报告生成 | 8 (TC01~TC07, L4) | 0 | 8 |
| 集成 | 跨 Spike | 0 | 6 (INT-01~INT-06) | 6 |
| **总计** | | **59** | **61** | **120** |

> 注：部分测试用例包含多个子方法（如 S3-TC01~TC03 含 6 个 test method），实际 test method 总数约 **184**。

---

## 附录 B：Go/No-Go 阈值速查表

| Spike | 阈值名 | 值 | 类型 |
|-------|--------|-----|------|
| S1 | S1_ENTITY_DIFF_PCT | ≤ 1% | 必须 |
| S1 | S1_LAYER_CLASSIFY_RATE | ≥ 85% | 必须 |
| S1 | S1_COORD_ERROR_MM | ≤ 10mm | 必须 |
| S1 | S1_LARGE_FILE_MEMORY_MB | ≤ 2048 MB | 必须 |
| S1 | S1_LARGE_FILE_TIME_S | ≤ 30s | 期望 |
| S1 | S1_ERROR_CODE_CORRUPT | 5001 | 必须 |
| S2 | S2_STDIO_SUCCESS_RATE | 100% | 必须 |
| S2 | S2_SSE_SUCCESS_RATE | ≥ 99% | 必须 |
| S2 | S2_SSE_P99_LATENCY_MS | ≤ 500ms | 必须 |
| S3 | S3_GLOBAL_50/100/200_MS | ≤ 50/100/200ms | 必须 |
| S3 | S3_INCREMENTAL_MS | ≤ 20ms | 必须 |
| S3 | S3_HEAL_MS | ≤ 100ms | 必须 |
| S3 | S3_EXCLUSION_MS | ≤ 50ms | 必须 |
| S3 | S3_WS_E2E_MS | ≤ 500ms | 必须 |
| S4 | S4_DETERMINISTIC_ERROR_PCT | ≤ 1% | 必须 |
| S4 | S4_STOCHASTIC_ERROR_PCT | ≤ 5% | 必须 |
| S4 | S4_10/20/50STATION_TIME_S | ≤ 30/60/180s | 必须/期望 |
| S5 | S5_PRECISION | ≥ 0.80 | 必须 |
| S5 | S5_RECALL | ≥ 0.70 | 必须 |
| S5 | S5_SOURCE_REF_ACCURACY | ≥ 90% | 必须 |
| S5 | S5_HALLUCINATION_RATE | ≤ 10% | 必须 |
| S6 | S6_RETRY_MAX_ATTEMPTS | 3 | 必须 |
| S7 | S7_FPS_200_ASSETS | ≥ 30 | 必须 |
| S7 | S7_FIRST_PAINT_S | ≤ 3s | 必须 |
| S8 | S8_INFERENCE_ERROR_PCT | ≤ 10% MAE | 期望 |
| S8 | S8_INFERENCE_LATENCY_MS | ≤ 100ms | 期望 |
| S8 | S8_OOD_ERROR_PCT | ≤ 20% | 期望 |
| S9 | S9_RECALL_AT_5 | ≥ 0.80 | 必须 |
| S9 | S9_LATENCY_MS | ≤ 500ms | 期望 |
| S10 | S10_LARGE_REPORT_TIME_S | ≤ 30s | 期望 |

---

## 附录 C：测试类型分布

| 测试类型 | 用例数 | 占比 |
|----------|--------|------|
| 功能 | 52 | 43.3% |
| 性能 | 24 | 20.0% |
| 精度 | 22 | 18.3% |
| 异常 | 6 | 5.0% |
| 兼容性 | 5 | 4.2% |
| 集成 | 11 | 9.2% |
| **合计** | **120** | **100%** |

---

## 附录 D：优先级执行计划

| 阶段 | Sprint | 覆盖 Spike | 用例数 | 准入条件 |
|------|--------|-----------|--------|----------|
| Phase-1 P0 必过 | Sprint 1 | S1 (基础+大文件+兼容性), S5 (PDF 预处理) | 23 | ezdxf + PyMuPDF 安装 |
| Phase-2 P1 核心 | Sprint 2 | S1 (图层+实体+坐标), S2 (MCP), S3 (全部), S4 (全部), S5 (约束提取+质量) | 62 | DWGParser + LLM API + SimPy |
| Phase-3 P1 集成 | Sprint 3 | S1 (SiteModel), S5 (ProcessGraph+分块), S6 (Temporal), S7, INT-01~06 | 27 | 全模块集成 |
| Phase-4 P2 扩展 | Sprint 4 | S8 (PINN), S9 (RAG), S10 (报告) | 22 | GPU + Milvus + WeasyPrint |
