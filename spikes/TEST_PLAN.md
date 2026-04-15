# ProLine CAD Spike 测试计划 —— 基于真实数据
> 版本 1.0 | 2026-04-10 | 关联 PRD v1.2

---

## 一、数据资产清单

### 1.1 Spike-1 DWG/DXF 底图（`spike_01_dwg_parse/test_data/`）

| 分类 | 文件 | 大小 | 图层 | 实体数 | 用途 |
|------|------|------|------|--------|------|
| **工业产线 DXF** | `cold_rolled_steel_production.dxf` | 42.7 MB | 5 | 95,856 | 大规模钢铁产线；LINE 78K + DIMENSION 45；性能 & 实体覆盖 |
| **工业产线 DXF** | `fish_processing_plant.dxf` | 82.9 MB | 118 | 104,811 | 最大文件；118 层（axis/wall/techno/columns）；图层分类压力 |
| **工业产线 DXF** | `woodworking_plant.dxf` | 3.2 MB | 11 | 1,563 | 中等复杂度；含 equipment/rail/wall 语义层；INSERT 202 块 |
| **工业产线 DXF** | `woodworking_factory_1.dxf` | 3.9 MB | 9 | 11,424 | 含 floor/walls/furn_eq；ARC 3210 弧线密集 |
| **工业产线 DWG** | `cold_rolled_steel_production.dwg` | 5.5 MB | — | — | ODA 转换源文件 (AC1021) |
| **工业产线 DWG** | `fish_processing_plant.dwg` | 13.5 MB | — | — | ODA 转换源文件 (AC1021) |
| **工业产线 DWG** | `woodworking_plant.dwg` | 394 KB | — | — | ODA 转换源文件 (AC1021) |
| **工业产线 DWG** | `woodworking_factory_1.dwg` | 691 KB | — | — | ODA 转换源文件 (AC1021) |
| 格式参考 DWG | `example_2000/2007/2018.dwg` | 146~569 KB | — | — | DWG R2000/R2007/R2018 版本兼容性 |
| 格式参考 DWG | `807_complex.dwg` | 495 KB | — | — | 复杂实体格式验证 |
| 特性参考 DXF | `hatch_complex/patterns.dxf` | 72~164 KB | 2 | 12~98 | HATCH 填充实体解析 |
| 特性参考 DXF | `custom_blocks.dxf` | 160 KB | 2 | 5 | INSERT 块引用解析 |
| 特性参考 DXF | `viewport_layers.dxf` | 72 KB | 5 | 4 | 视口图层控制 |
| 特性参考 DXF | `entities_all.dxf` | 190 KB | 4 | 116 | LINE/MTEXT/INSERT/LWPOLYLINE 混合 |
| 合成测试 DXF | `tier1/2/3_*.dxf` | 合成 | 合成 | 99/286/358 | TDD 合成数据（尺寸梯度） |
| 异常测试 | `corrupted_file.dxf` | — | — | — | 优雅失败 + 错误码 5001 |

### 1.2 Spike-5 SOP 文档（`spike_05_llm_extract/test_data/`）

| 文件 | 页数 | 大小 | 关键内容 | 测试价值 |
|------|------|------|----------|----------|
| `FAA_AC43.13-1B_Inspection_Repair.pdf` | 646 | 20.1 MB | 铆接/钣金/复合材料/焊接全工艺步骤 | 最全面 SOP；大文档 LLM 分块提取 |
| `FAA_AC43-214_Composite_Repair.pdf` | 21 | 170 KB | 铺层/固化/粘接 + 温度/压力参数 | 最贴近 PRD 场景；参数化约束 |
| `FAA_AC21-26A_Quality_System.pdf` | 15 | 2.4 MB | 固化曲线/温度监控/检验方法 | 质量控制流程 + 工艺参数约束 |
| `FAA_AC145-10_Repair_Station.pdf` | 41 | 496 KB | 维修流程/人员资质/工具校准 | 流程依赖关系提取 |
| `FAA_AC21.303_Parts_Manufacturing.pdf` | 32 | 316 KB | 制造审批/检验流程/合规要求 | 多步骤审批 + 合规约束 |
| `SOP_A_wing_skin_milling.md` | — | 合成 | 机翼蒙皮铣削 12 条约束 | Gold Standard A |
| `SOP_B_fuselage_panel_riveting.md` | — | 合成 | 机身壁板钻铆 18 条 + 2 矛盾 | Gold Standard B |
| `SOP_C_wing_body_join.md` | — | 合成 | 总装翼身对接 25 条 + 3 矛盾 | Gold Standard C |

---

## 二、Spike-1 测试计划：DWG/DXF 底图解析

### 2.1 已有测试（133 条，TDD RED phase）

| 测试类 | TC-ID | 当前数据 | 状态 |
|--------|-------|----------|------|
| TestDWGParse | S1-TC01 | tier1/2/3 合成 DXF | ✅ 保留 |
| TestLayerSemanticMapping | S1-TC02 | tier2 合成 DXF | ✅ 保留 |
| TestCoordinateAlignment | S1-TC04 | reference_points_offset.dxf | ✅ 保留 |
| TestLargeFilePerformance | S1-TC03 | tier3 合成 DXF | ✅ 保留 |
| TestCorruptedFile | S1-TC06 | corrupted_file.dxf | ✅ 保留 |
| TestRealWorldDWG | — | ezdxf/ 子目录 DXF | ✅ 保留 |
| TestEdgeCases | — | tier1 DXF | ✅ 保留 |

### 2.2 新增测试（基于真实工业 DXF）

#### S1-RT01: 工业产线 DXF 基础解析

| # | 测试方法 | 输入文件 | 验证点 | Go/No-Go |
|---|----------|----------|--------|----------|
| 1 | `test_industrial_parse_woodworking_plant` | `woodworking_plant.dxf` | entities=1563, layers=11, 确认提取 equipment/rail/wall 层 | 实体偏差 ≤1% |
| 2 | `test_industrial_parse_woodworking_factory` | `woodworking_factory_1.dxf` | entities=11424, layers=9, 含 floor/walls/furn_eq | 实体偏差 ≤1% |
| 3 | `test_industrial_parse_steel_production` | `cold_rolled_steel_production.dxf` | entities=95856, layers=5, LINE 占比 >80% | 实体偏差 ≤1% |
| 4 | `test_industrial_parse_fish_plant` | `fish_processing_plant.dxf` | entities=104811, layers=118 | 实体偏差 ≤1% |

#### S1-RT02: 工业图层语义映射

| # | 测试方法 | 输入文件 | 验证点 | Go/No-Go |
|---|----------|----------|--------|----------|
| 5 | `test_woodworking_layer_classify` | `woodworking_plant.dxf` | equipment→设备, rail→设备, wall→结构, axis→辅助, txt→辅助 | 准确率 ≥85% |
| 6 | `test_fish_plant_layer_classify` | `fish_processing_plant.dxf` | 118 层中: axis→辅助, wall1/wall exist→结构, columns→结构, techno 1/2/3→设备 | 准确率 ≥85% |
| 7 | `test_steel_layer_classify` | `cold_rolled_steel_production.dxf` | 5 层 (0/dwgmodels.com/Defpoints/hatch/Системный слой) 归类 | 准确率 ≥85% |
| 8 | `test_unknown_layer_ratio` | 全部 4 文件 | 非标层名(dwgmodels.com/Defpoints)归入 unclassified, 比率统计 | unclassified ≤30% |

#### S1-RT03: 大文件性能压测

| # | 测试方法 | 输入文件 | 验证点 | Go/No-Go |
|---|----------|----------|--------|----------|
| 9 | `test_fish_plant_memory` | `fish_processing_plant.dxf` (83 MB) | 峰值内存 | ≤2GB |
| 10 | `test_fish_plant_time` | `fish_processing_plant.dxf` (83 MB) | 解析耗时 | ≤30s |
| 11 | `test_steel_production_memory` | `cold_rolled_steel_production.dxf` (43 MB) | 峰值内存 | ≤2GB |
| 12 | `test_steel_production_time` | `cold_rolled_steel_production.dxf` (43 MB) | 解析耗时 | ≤30s |

#### S1-RT04: 实体类型覆盖度

| # | 测试方法 | 输入文件 | 验证点 | Go/No-Go |
|---|----------|----------|--------|----------|
| 13 | `test_entity_type_coverage` | 全部 4 文件 | 合并应覆盖: LINE, ARC, LWPOLYLINE, CIRCLE, INSERT, MTEXT, HATCH, SPLINE, ELLIPSE, DIMENSION, POLYLINE, POINT, TEXT, REGION | ≥10 种 |
| 14 | `test_dimension_entity_parse` | `cold_rolled_steel_production.dxf` | 45 个 DIMENSION 实体可提取标注值 | DIMENSION 不丢失 |
| 15 | `test_insert_block_resolve` | `woodworking_plant.dxf` | 202 个 INSERT 可解引用到块定义 | INSERT 全部可解析 |
| 16 | `test_hatch_pattern_parse` | `woodworking_plant.dxf` | 74 个 HATCH 实体边界 + 图案名可提取 | HATCH 全部可读 |
| 17 | `test_spline_entity_parse` | `fish_processing_plant.dxf` | 12901 个 SPLINE 控制点可提取 | SPLINE 不丢失 |

#### S1-RT05: DWG 格式兼容性（ODA 转换链路）

| # | 测试方法 | 输入文件 | 验证点 | Go/No-Go |
|---|----------|----------|--------|----------|
| 18 | `test_dwg_to_dxf_roundtrip` | 4 个工业 DWG → ODA → DXF | DXF 可被 ezdxf.readfile() 正常读取 | 4/4 成功 |
| 19 | `test_dwg_version_ac1021` | 4 个工业 DWG | 文件头 = AC1021 (AutoCAD 2007) | 版本识别正确 |
| 20 | `test_dwg_multi_version` | example_2000/2007/2018.dwg | R2000(AC1015), R2007(AC1021), R2018(AC1032) 均可识别 | 3/3 正确版本 |

#### S1-RT06: 坐标系 & BoundingBox

| # | 测试方法 | 输入文件 | 验证点 | Go/No-Go |
|---|----------|----------|--------|----------|
| 21 | `test_bounding_box_nonzero` | 全部 4 工业 DXF | extents 不为零; max > min | extents 有效 |
| 22 | `test_coordinate_range_sane` | `woodworking_plant.dxf` | 坐标范围在 ±100,000mm 内（合理工厂尺寸） | 无异常偏移值 |
| 23 | `test_entity_spatial_distribution` | `fish_processing_plant.dxf` | 实体空间分布在 bounding box 范围内, 无离群点 | ≥95% 实体在 bbox 内 |

#### S1-RT07: SiteModel 输出完整性

| # | 测试方法 | 输入文件 | 验证点 | Go/No-Go |
|---|----------|----------|--------|----------|
| 24 | `test_site_model_schema` | `woodworking_plant.dxf` | to_site_model() 包含 site_guid/layers/entities/bounding_box | schema 完整 |
| 25 | `test_site_model_json_roundtrip` | `woodworking_plant.dxf` | dumps → loads → 无信息丢失 | 100% 保真 |
| 26 | `test_site_model_mcp_context` | `woodworking_plant.dxf` | SiteModel 输出携带 mcp_context_id | MCP 追溯链 |

---

## 三、Spike-5 测试计划：LLM 工艺约束提取

### 3.1 已有测试（TDD RED phase）

| 测试类 | TC-ID | 当前数据 | 状态 |
|--------|-------|----------|------|
| TestConstraintExtractionSOP_A | S5-TC01 | SOP_A.md (合成) | ✅ 保留 |
| TestConstraintExtractionSOP_B | S5-TC02 | SOP_B.md (合成) | ✅ 保留 |
| TestConstraintExtractionSOP_C | S5-TC03 | SOP_C.md (合成) | ✅ 保留 |
| TestSourceRefTraceability | S5-TC04 | SOP_A/B/C.md | ✅ 保留 |
| TestPromptStrategies | S5-TC05 | SOP_A.md | ✅ 保留 |
| TestHallucinationDetection | S5-TC06 | SOP_A.md | ✅ 保留 |
| TestJSONOutput | S5-TC07 | SOP_A/B/C.md | ✅ 保留 |
| TestMockDeterministicExtraction | L4 | Mock LLM | ✅ 保留 |

### 3.2 新增测试（基于真实 FAA PDF）

#### S5-RT01: PDF 文档预处理

| # | 测试方法 | 输入文件 | 验证点 | Go/No-Go |
|---|----------|----------|--------|----------|
| 1 | `test_pdf_text_extraction_ac43_214` | `FAA_AC43-214_Composite_Repair.pdf` (21pp) | PyMuPDF 提取文本, 长度 > 5000 字符, 含 "composite", "cure", "bond" | 文本可提取 |
| 2 | `test_pdf_text_extraction_ac21_26a` | `FAA_AC21-26A_Quality_System.pdf` (15pp) | 提取文本含 "temperature", "pressure", "process" | 文本可提取 |
| 3 | `test_pdf_text_extraction_large` | `FAA_AC43.13-1B_Inspection_Repair.pdf` (646pp) | 全文提取 ≤60s, 文本长度 > 500,000 字符 | 性能达标 |
| 4 | `test_pdf_text_extraction_ac145` | `FAA_AC145-10_Repair_Station.pdf` (41pp) | 含 "repair", "inspect", "procedure" | 文本可提取 |
| 5 | `test_pdf_text_extraction_ac21_303` | `FAA_AC21.303_Parts_Manufacturing.pdf` (32pp) | 含 "manufacturing", "approval", "compliance" | 文本可提取 |

#### S5-RT02: 真实 PDF 约束提取

| # | 测试方法 | 输入文件 | 验证点 | Go/No-Go |
|---|----------|----------|--------|----------|
| 6 | `test_real_pdf_extract_composite_repair` | `FAA_AC43-214` (21pp) | 输出 ConstraintSet, constraints 数量 ≥ 5, 每条含 id/type/rule/source_ref | Precision ≥0.80 |
| 7 | `test_real_pdf_extract_quality_system` | `FAA_AC21-26A` (15pp) | 提取温度/压力/时间参数约束, 含数值范围 | Recall ≥0.70 |
| 8 | `test_real_pdf_extract_repair_station` | `FAA_AC145-10` (41pp) | 提取流程依赖 (ProcessGraph), 含步骤序列 | 输出可解析 JSON |
| 9 | `test_real_pdf_extract_large_doc` | `FAA_AC43.13-1B` (646pp) | 分块提取, 每块 ≤4000 token, 去重合并 | 结果 ≥20 条约束 |
| 10 | `test_real_pdf_extract_manufacturing` | `FAA_AC21.303` (32pp) | 多步骤审批流程提取 | 输出可解析 JSON |

#### S5-RT03: 约束质量验证

| # | 测试方法 | 输入文件 | 验证点 | Go/No-Go |
|---|----------|----------|--------|----------|
| 11 | `test_constraint_has_numeric_params` | `FAA_AC43-214` | 至少 3 条约束含数值参数 (温度°F/°C, 压力 psi, 时间 min/hr) | ≥3 条 |
| 12 | `test_constraint_type_distribution` | `FAA_AC21-26A` | hard/soft 分布合理: hard ≥30%, soft ≥20% | 非全 hard/soft |
| 13 | `test_source_ref_points_to_real_text` | `FAA_AC43-214` | 每条 source_ref 可在 PDF 原文中定位到段落 | ≥90% |
| 14 | `test_no_duplicate_constraints` | `FAA_AC145-10` | 约束 ID 全局唯一, 无逻辑重复 (规则文本 similarity <0.9) | 0 重复 |

#### S5-RT04: ProcessGraph 提取 (PRD-2 核心)

| # | 测试方法 | 输入文件 | 验证点 | Go/No-Go |
|---|----------|----------|--------|----------|
| 15 | `test_process_graph_from_repair` | `FAA_AC43.13-1B` Ch.3 铆接章节 | 提取 step 序列: 钻孔→去毛刺→铆接→检验; DAG 无环 | 步骤数 ≥3 |
| 16 | `test_process_graph_from_composite` | `FAA_AC43-214` | 铺层→真空袋→固化→检验; 含温度/时间约束关联 | DAG 无环 |
| 17 | `test_process_graph_dag_valid` | 任意提取结果 | 拓扑排序可执行, 无死锁/悬空节点 | DAG 验证通过 |
| 18 | `test_process_graph_constraint_link` | `FAA_AC43-214` | ProcessGraph 节点引用对应 ConstraintSet 中的 constraint_id | 引用一致 |

#### S5-RT05: 大文档分块与合并

| # | 测试方法 | 输入文件 | 验证点 | Go/No-Go |
|---|----------|----------|--------|----------|
| 19 | `test_chunking_646pp` | `FAA_AC43.13-1B` (646pp) | 分块数 ≥10, 每块 ≤4000 token, 无句中切断 | token 限制 |
| 20 | `test_chunk_overlap_dedup` | `FAA_AC43.13-1B` | 重叠区域约束不重复计数 (merge 后 ID 唯一) | 0 重复 |
| 21 | `test_extraction_time_per_chunk` | `FAA_AC43-214` | 单块提取 ≤30s (LLM 调用含网络延迟) | ≤30s/块 |

---

## 四、跨 Spike 集成测试计划

### 4.1 S1→S3: 底图解析 → 碰撞检测

| # | 测试方法 | 数据来源 | 验证点 | Go/No-Go |
|---|----------|----------|--------|----------|
| 1 | `test_parse_then_collision_woodworking` | `woodworking_plant.dxf` → SiteModel → Asset 列表 | 从 equipment 层提取 asset footprint, 输入碰撞引擎 | 无崩溃 |
| 2 | `test_collision_from_real_layout` | `woodworking_plant.dxf` 202 INSERT 块 | 块引用→asset bounding box→碰撞对数量 | ≤100ms |

### 4.2 S1→S4: 底图解析 → DES 仿真

| # | 测试方法 | 数据来源 | 验证点 | Go/No-Go |
|---|----------|----------|--------|----------|
| 3 | `test_parse_then_sim_steel` | `cold_rolled_steel_production.dxf` → 工站提取 | 从 DIMENSION 标注提取工站间距, 构建仿真拓扑 | 站间距 >0 |
| 4 | `test_station_count_from_layout` | `fish_processing_plant.dxf` techno 层 | techno 1/2/3 层实体 → 工站数量 | 工站数 ≥2 |

### 4.3 S5→S3: 约束提取 → 碰撞检测

| # | 测试方法 | 数据来源 | 验证点 | Go/No-Go |
|---|----------|----------|--------|----------|
| 5 | `test_constraint_to_exclusion_zone` | FAA PDF → ConstraintSet → 禁区 polygon | hard 约束 "minimum clearance" → exclusion zone geometry | zone 面积 >0 |

### 4.4 S1+S5→S10: 底图 + 约束 → 报告

| # | 测试方法 | 数据来源 | 验证点 | Go/No-Go |
|---|----------|----------|--------|----------|
| 6 | `test_report_includes_layout_summary` | woodworking SiteModel + ConstraintSet | PDF 报告含图层统计表 + 约束列表 | 表格可读 |

---

## 五、Fixture 扩展需求

以下 fixture 需加入 `conftest.py`:

```python
# ──────────── Spike-1: 工业产线 DXF Fixtures ────────────
@pytest.fixture(scope="session")
def industrial_dxf_woodworking_plant():
    return SPIKE1_REAL / "woodworking_plant.dxf"

@pytest.fixture(scope="session")
def industrial_dxf_woodworking_factory():
    return SPIKE1_REAL / "woodworking_factory_1.dxf"

@pytest.fixture(scope="session")
def industrial_dxf_steel_production():
    return SPIKE1_REAL / "cold_rolled_steel_production.dxf"

@pytest.fixture(scope="session")
def industrial_dxf_fish_plant():
    return SPIKE1_REAL / "fish_processing_plant.dxf"

@pytest.fixture(scope="session")
def all_industrial_dxf_paths():
    return [
        SPIKE1_REAL / "woodworking_plant.dxf",
        SPIKE1_REAL / "woodworking_factory_1.dxf",
        SPIKE1_REAL / "cold_rolled_steel_production.dxf",
        SPIKE1_REAL / "fish_processing_plant.dxf",
    ]

# ──────────── Spike-5: FAA PDF Fixtures ────────────
@pytest.fixture(scope="session")
def faa_ac43_214_path():
    """FAA AC43-214 Composite Repair (21pp) — 最贴近 PRD 场景"""
    return SPIKE5_DATA / "FAA_AC43-214_Composite_Repair.pdf"

@pytest.fixture(scope="session")
def faa_ac21_26a_path():
    """FAA AC21-26A Quality System (15pp)"""
    return SPIKE5_DATA / "FAA_AC21-26A_Quality_System.pdf"

@pytest.fixture(scope="session")
def faa_ac43_13_path():
    """FAA AC43.13-1B Inspection & Repair (646pp) — 大文档"""
    return SPIKE5_DATA / "FAA_AC43.13-1B_Inspection_Repair.pdf"

@pytest.fixture(scope="session")
def faa_ac145_path():
    """FAA AC145-10 Repair Station (41pp)"""
    return SPIKE5_DATA / "FAA_AC145-10_Repair_Station.pdf"

@pytest.fixture(scope="session")
def faa_ac21_303_path():
    """FAA AC21.303 Parts Manufacturing (32pp)"""
    return SPIKE5_DATA / "FAA_AC21.303_Parts_Manufacturing.pdf"

@pytest.fixture(scope="session")
def all_faa_pdf_paths():
    return sorted(SPIKE5_DATA.glob("FAA_*.pdf"))
```

---

## 六、工业文件→已有测试映射关系

现有测试来自合成数据 (tier1/2/3)。以下映射说明每份工业文件如何替代/补充合成数据：

| 现有测试 | 合成数据 | 替代/补充工业文件 | 映射逻辑 |
|----------|----------|-------------------|----------|
| TestDWGParse.tier1 (99 实体) | tier1_wing_leading_edge_workshop.dxf | `woodworking_plant.dxf` (1563 实体) | 小型车间解析 |
| TestDWGParse.tier2 (286 实体) | tier2_fuselage_join_facility.dxf | `woodworking_factory_1.dxf` (11424 实体) | 中型设施解析 |
| TestDWGParse.tier3 (358 实体) | tier3_pulse_line_fal.dxf | `fish_processing_plant.dxf` (104811 实体) | 大型产线解析 |
| TestLargeFilePerformance | tier3 合成 | `fish_processing_plant.dxf` (83 MB) | 真实大文件性能基线 |
| TestLayerSemanticMapping | tier2 合成层名 | `fish_processing_plant.dxf` (118 真实层名) | 真实非标层分类 |
| TestRealWorldDWG | ezdxf/ 参考集 | 4 个工业 DXF + 8 个参考 DXF | 扩大兼容性覆盖 |

---

## 七、预期实体类型覆盖矩阵

| 实体类型 | steel_prod | fish_plant | wood_plant | wood_factory | 测试覆盖 |
|----------|:---:|:---:|:---:|:---:|:---:|
| LINE | 78,954 | 66,659 | 503 | 6,686 | ✅ |
| ARC | 5,507 | 12,609 | 12 | 3,210 | ✅ |
| LWPOLYLINE | 4,880 | 4,317 | 503 | 1,075 | ✅ |
| CIRCLE | 3,630 | 3,063 | 80 | 156 | ✅ |
| INSERT | 1,085 | 791 | 202 | 89 | ✅ |
| MTEXT | 903 | — | 136 | 112 | ✅ |
| HATCH | 405 | — | 74 | — | ✅ |
| ELLIPSE | 304 | 3,016 | — | 31 | ✅ |
| SPLINE | 128 | 12,901 | — | 23 | ✅ |
| DIMENSION | 45 | — | — | — | ✅ |
| POLYLINE | — | 1,037 | — | — | ✅ |
| TEXT | — | 166 | — | — | ✅ |
| POINT | — | 151 | — | — | ✅ |
| REGION | — | — | 44 | — | ✅ |
| **共计** | **95,856** | **104,811** | **1,563** | **11,424** | **14 种** |

---

## 八、优先级与执行顺序

### Phase-1: P0 必过（Sprint 1）

| 序号 | 测试组 | 新增用例数 | 依赖 |
|------|--------|-----------|------|
| 1 | S1-RT01: 工业 DXF 基础解析 | 4 | ezdxf + DWGParser |
| 2 | S1-RT05: DWG 版本兼容性 | 3 | ODA File Converter |
| 3 | S1-RT03: 大文件性能 | 4 | tracemalloc |
| 4 | S5-RT01: PDF 文本提取 | 5 | PyMuPDF |

### Phase-2: P1 核心（Sprint 2）

| 序号 | 测试组 | 新增用例数 | 依赖 |
|------|--------|-----------|------|
| 5 | S1-RT02: 图层语义映射 | 4 | LayerSemanticMapper |
| 6 | S1-RT04: 实体类型覆盖 | 5 | DWGParser entity model |
| 7 | S1-RT06: 坐标系验证 | 3 | CoordinateAligner |
| 8 | S5-RT02: PDF 约束提取 | 5 | ConstraintExtractor + LLM |
| 9 | S5-RT03: 约束质量 | 4 | ExtractionEvaluator |

### Phase-3: P1 集成（Sprint 3）

| 序号 | 测试组 | 新增用例数 | 依赖 |
|------|--------|-----------|------|
| 10 | S1-RT07: SiteModel 输出 | 3 | SiteModel schema |
| 11 | S5-RT04: ProcessGraph | 4 | ProcessGraph DAG |
| 12 | S5-RT05: 大文档分块 | 3 | Chunking pipeline |
| 13 | 跨 Spike 集成 | 6 | S1+S3+S4+S5+S10 |

---

## 九、测试用例总数汇总

| 类别 | 已有(RED) | 新增(基于真实数据) | 合计 |
|------|----------|-------------------|------|
| Spike-1 DWG/DXF | ~20 | 26 | ~46 |
| Spike-2 MCP | ~5 | 0 | ~5 |
| Spike-3 碰撞 | ~15 | 2 (集成) | ~17 |
| Spike-4 仿真 | ~18 | 2 (集成) | ~20 |
| Spike-5 LLM | ~20 | 21 | ~41 |
| Spike-6 Temporal | 0 (清空) | 0 | 0 |
| Spike-7 3D 渲染 | ~12 | 0 | ~12 |
| Spike-8 PINN | ~12 | 0 | ~12 |
| Spike-9 RAG | ~12 | 0 | ~12 |
| Spike-10 报告 | ~15 | 2 (集成) | ~17 |
| **总计** | **~133** | **51** | **~184** |

---

## 十、风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| fish_processing_plant.dxf (83 MB) 在 CI 中过慢 | CI 超时 | 标记 `@pytest.mark.slow`, CI 分层: fast <10s / slow <120s |
| 工业图层名与航空标准差异大 | 图层分类准确率低 | LayerSemanticMapper 支持泛化映射 + 可配置同义词表 |
| FAA PDF 为英文, PRD 场景为中文航空制造 | LLM 提取质量波动 | prompt 模板含中英双语指令; 英文约束→中文翻译后验收 |
| 646pp 大文档 LLM 分块丢失上下文 | 约束遗漏 | 滑动窗口重叠 200 token; 全局去重合并 |
| DWG 需 ODA 转换, ODA 非 CI 标配 | CI 无法测 DWG | DXF 版本为主测, DWG 测试标记 `@pytest.mark.oda` 仅本地跑 |
