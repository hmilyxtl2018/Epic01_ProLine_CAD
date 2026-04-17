# ParseAgent 解析质量改进计划

> 基于 Claude Opus LLM 质量评估矩阵制定，持续迭代

## 0. 当前状态摘要

### Phase 1 基线 (改进前, overall = 0.15)

| DWG 文件 | Assets | Links | Rule Verdict | LLM Overall | 主要瓶颈 |
|---|---|---|---|---|---|
| 机加车间 | 704 | 1,327 | SUCCESS | **0.32** | STEP_1误分类; 49% Other |
| woodworking_plant | 1,563 | 37,631 | SUCCESS_WITH_WARNINGS | **0.28** | wall/door/window 层未识别 |
| example_2018 | 68 | 0 | SUCCESS_WITH_WARNINGS | **0.13** | 意大利层名无覆盖; (0,0,0) |
| example_2007 | 68 | 0 | SUCCESS_WITH_WARNINGS | **0.12** | 同上 |
| example_2000 | 68 | 0 | SUCCESS_WITH_WARNINGS | **0.12** | 同上 |
| woodworking_factory_1 | 11,424 | 0 | DEGRADED | **0.09** | 英文层名(walls/furn_eq)未匹配 |
| fish_processing | 104,811 | 43,427 | DEGRADED | **0.08** | 波兰语层名; 10万 Other |
| cold_rolled | 95,856 | 0 | DEGRADED | **0.06** | 俄语单层; 零分类 |

### Phase 1 结果 (IMP-01~05 完成后, overall = 0.27, +80%)

| DWG 文件 | v1 Overall | v2 Overall | 变化 | 状态 |
|---|---|---|---|---|
| 机加车间 | 0.32 | **0.28** | -0.04 | IMP-03 过滤导致轻微回退 |
| woodworking_plant | 0.28 | **0.44** | +0.16 | ✅ 显著提升 |
| example_2018 | 0.13 | **0.35** | +0.22 | ✅ 意大利语层名生效 |
| example_2007 | 0.12 | **0.26** | +0.14 | ✅ |
| example_2000 | 0.12 | **0.26** | +0.14 | ✅ |
| woodworking_factory_1 | 0.09 | **0.36** | +0.27 | ✅ 最大进步 |
| fish_processing | 0.08 | **0.14** | +0.06 | 波兰语仍待深化 |
| cold_rolled | 0.06 | **0.03** | -0.03 | ⚠️ 仍极低 |
| **平均** | **0.15** | **0.27** | **+0.12** | |

### Phase 2 目标

**改进目标**: 将 8 份平均 overall 从 **0.27 → 0.45+**（Phase 2）→ **0.60+**（Phase 3）

---

## 1. 改进路线总览

### Phase 1 改进项 (✅ 已完成)

| 改进编号 | 改进项 | 状态 | 实际提升 |
|---|---|---|---|
| IMP-01 | 扩展 AssetType 5→13 | ✅ 完成 | coverage +0.15 |
| IMP-02 | 多语言图层名字典 (意/俄/波兰) | ✅ 完成 | classification_accuracy +0.12 |
| IMP-03 | 坐标异常过滤 (origin + IQR) | ✅ 完成 | confidence_calibration +0.08 |
| IMP-04 | 英文图层名扩展映射 (~50条) | ✅ 完成 | coverage +0.10 |
| IMP-05 | Zone 分类精细化 (图层覆盖几何 + 原点降级) | ✅ 完成 | classification_accuracy +0.05 |

> Phase 1 共新增 42 条测试 + 49 条回归 = 91 条全部 PASS

### Phase 2 改进项 (🔧 进行中)

基于**概念-关系-事实**三层本体分析，Phase 1 核心不足:
- **事实层**: 仅 5 种信号，TEXT 内容、面积、属性全部丢弃
- **概念层**: 扁平 13 枚举，无 is-a 层次，未知→OTHER 而非上位类
- **关系层**: 关系是分类的**产出**而非**输入**，每个实体独立分类

| 改进编号 | 改进项 | 影响文件数 | 预期提升维度 | 依赖 |
|---|---|---|---|---|
| IMP-06 | TEXT/MTEXT 内容提取 + 空间标签关联 | 6/8 | semantic_richness, actionability | 无 |
| IMP-07 | 概念层次树 (is-a 降级匹配) | 8/8 | classification_accuracy, coverage | 无 |
| IMP-08 | KNN 空间上下文传播 | 8/8 | classification_accuracy, confidence | IMP-06 |
| IMP-09 | 闭环推理迭代 (classify↔link 收敛) | 8/8 | semantic_richness, coverage | IMP-08 |
| IMP-10 | 冷轧领域词典 + 平面图模式 | 1/8 (cold_rolled) | classification_accuracy | 无 |

---

## 2. Phase 1 — 已完成 (IMP-01~05)

> Phase 1 详细设计见 git 历史。42 条新增测试 + 49 条回归全部 PASS。
> 8 份 DWG 平均 overall 从 0.15 → 0.27 (+80%)。

---

## 3. Phase 2 — 本体推理增强 (IMP-06~10)

### IMP-06: TEXT/MTEXT 内容提取 + 空间标签关联

**问题**: DWG 中 MTEXT/TEXT 实体包含设备名称、区域标签等中文/多语言信息。当前 `entity_extract()` 不提取 TEXT 内容，这些实体被分类为 Other 后丢弃，未用于丰富邻近设备的语义标签。`semantic_richness` 维度平均仅 0.18，是最弱维度。

**改动范围**:
- `shared/models.py` — Asset 增加 `label: str = ""`, `block_name: str = ""`
- `shared/models.py` — LinkType 增加 `LABELED_BY`
- `agents/parse_agent/service.py` — `entity_extract()` 提取 TEXT/MTEXT 的 `text_content`
- `agents/parse_agent/service.py` — 新增 `associate_text_labels()` 空间关联方法
- `execute()`/`execute_full()` 管线插入新步骤

**设计要点**:
1. `entity_extract()` 中对 TEXT/MTEXT 提取 `rec["text_content"] = e.dxf.text` 或 `e.plain_text()`
2. `associate_text_labels()`:
   - 构建 2D KD-tree (scipy.spatial.cKDTree) 或暴力搜索 fallback
   - 对每个 TEXT 实体，找最近的非 TEXT 资产 (距离 < 2000mm)
   - 将文本内容赋值给目标资产的 `label` 字段
   - 生成 LABELED_BY 关系边
3. 管线位置: `filter_anomalous_coords` 之后、`build_ontology_graph` 之前

**TDD 用例** (~12 条):
```
test_text_entity_extracts_text_content
test_mtext_entity_extracts_plain_text
test_asset_model_has_label_field
test_asset_model_has_block_name_field
test_link_type_has_labeled_by
test_associate_text_nearest_equipment
test_associate_text_radius_limit_2000mm
test_associate_text_ignores_far_text
test_associate_text_empty_text_skipped
test_associate_text_generates_labeled_by_link
test_associate_text_multiple_texts_nearest_wins
test_pipeline_includes_text_association_step
```

**验收口径**:
- TEXT/MTEXT 内容被提取为 `text_content` 字段
- 近邻设备获得有意义的 `label`
- `semantic_richness` 维度整体提升 0.1+

---

### IMP-07: 概念层次树 (is-a 降级匹配)

**问题**: 当前 13 种 AssetType 是扁平枚举。当无法精确匹配为某个子类型时，直接降为 OTHER。这在"概念-关系-事实"本体中缺少**上位概念**层，导致大量"几乎正确"的分类被浪费。

**改动范围**:
- `agents/parse_agent/service.py` — 新增 `_CONCEPT_HIERARCHY` 字典
- `agents/parse_agent/service.py` — `classify_entity()` 中增加层次降级逻辑

**概念层次设计**:
```python
_CONCEPT_HIERARCHY: dict[AssetType, AssetType] = {
    # 子类型 → 父类型
    AssetType.CNC_MACHINE: AssetType.EQUIPMENT,
    AssetType.ELECTRICAL_PANEL: AssetType.EQUIPMENT,
    AssetType.STORAGE_RACK: AssetType.EQUIPMENT,
    AssetType.LIFTING_POINT: AssetType.EQUIPMENT,
    AssetType.CONVEYOR: AssetType.EQUIPMENT,
    AssetType.DOOR: AssetType.WALL,
    AssetType.WINDOW: AssetType.WALL,
    AssetType.PIPE: AssetType.EQUIPMENT,
}
```

**降级逻辑**: 在 `classify_entity()` 最终类型决策后:
- 若 `asset_type == OTHER` 且 confidence > 0.15:
    - 检查 block_type/geom_type/layer_type 是否在 _CONCEPT_HIERARCHY 中有父类
    - 如有，降级为父类型，confidence = max(confidence, 0.3)

**TDD 用例** (~8 条):
```
test_concept_hierarchy_exists
test_cnc_machine_parent_is_equipment
test_door_parent_is_wall
test_low_conf_other_with_block_hint_promotes_to_parent
test_high_conf_specific_type_not_affected
test_truly_unknown_stays_other
test_hierarchy_does_not_affect_zone
test_hierarchy_reduces_other_ratio
```

**验收口径**:
- OTHER 比例在所有文件中下降 10%+
- 不引入新的误分类

---

### IMP-08: KNN 空间上下文传播

**问题**: 每个实体独立分类，不考虑空间邻域信息。在工厂布局中，同类设备往往空间聚集。邻域共识可作为分类信号的增强/降级因子。

**前置**: IMP-06 (TEXT 提取提供空间坐标)

**改动范围**:
- `agents/parse_agent/service.py` — 新增 `propagate_spatial_context()` 方法

**算法设计**:
1. 构建 2D KD-tree，k=5 最近邻，r=3000mm 半径限制
2. 对每个资产，统计 k 邻域中的类型分布:
   - 如 ≥3/5 邻居同类型，且自身为 OTHER → 提升为该类型，conf = 0.35
   - 如自身有明确类型且邻居一致 → confidence × 1.2 (上限 0.95)
   - 如自身有明确类型但邻居冲突 → confidence × 0.9
3. 跳过 Zone 和 OTHER (不参与传播)

**TDD 用例** (~10 条):
```
test_propagate_majority_promotes_other_to_equipment
test_propagate_consistent_neighbors_boost_confidence
test_propagate_conflicting_neighbors_reduce_confidence
test_propagate_zone_not_affected
test_propagate_isolated_entity_unchanged
test_propagate_respects_radius_limit
test_propagate_empty_assets
test_propagate_preserves_label
test_propagate_confidence_cap_095
test_propagate_does_not_flip_strong_type
```

**验收口径**:
- OTHER 比例在有坐标文件中下降 5%+
- 高密度区域的 confidence 上升
- cold_rolled 等无坐标差异的文件不受影响

---

### IMP-09: 闭环推理迭代 (classify ↔ link 收敛)

**问题**: 当前管线单向: classify → link。关系是分类的**产出**，但从不**反馈**到分类。在本体推理中，关系应该是**双向证据**。

**前置**: IMP-08

**改动范围**:
- `agents/parse_agent/service.py` — 修改 `execute()`/`execute_full()` 增加迭代循环
- `shared/models.py` — LinkType 增加 `CONTAINS`

**迭代设计**:
```python
for round_idx in range(max_rounds):  # max_rounds = 3
    assets = classify_entity(entities, ontology_ver)
    assets = filter_anomalous_coords(assets)
    assets = associate_text_labels(assets, text_entities)
    assets = propagate_spatial_context(assets)
    links = build_ontology_graph(assets)
    
    # 收敛检测: 若本轮资产类型分布与上轮一致 → break
    type_dist = Counter(a.type for a in assets)
    if type_dist == prev_type_dist:
        break
    prev_type_dist = type_dist
```

**TDD 用例** (~8 条):
```
test_iteration_converges_within_3_rounds
test_iteration_single_round_if_stable
test_iteration_improves_classification
test_link_type_has_contains
test_iteration_does_not_degrade_existing
test_iteration_max_rounds_respected
test_iteration_empty_entities
test_iteration_type_distribution_changes
```

**验收口径**:
- 管线平均迭代 1.5 轮即收敛
- 总体 overall 提升 0.05+
- 不显著增加延迟 (< 2x)

---

### IMP-10: 冷轧钢铁领域词典 + 平面图模式

**问题**: cold_rolled 是俄语工业图纸，95K 实体几乎全在单个图层，overall = 0.03。需要领域特化处理。

**改动范围**:
- `agents/parse_agent/service.py` — 新增俄语钢铁行业 block 模式
- `agents/parse_agent/service.py` — 新增"平面图模式"检测 (>90% 实体在单一图层时触发)

**领域词典**:
```python
# 俄语钢铁行业 block patterns
_RUSSIAN_STEEL_PATTERNS: dict[AssetType, list[str]] = {
    AssetType.EQUIPMENT: ["станок", "пресс", "печь", "прокат", "стан"],
    AssetType.CONVEYOR: ["рольганг", "конвейер", "транспорт"],
    AssetType.PIPE: ["труба", "воздуховод", "газопровод"],
    AssetType.ZONE: ["участок", "цех", "пролёт"],
}

# 平面图模式: 当 >90% 实体同一图层时
# 切换到纯几何+block 分类，忽略图层信号
```

**TDD 用例** (~6 条):
```
test_russian_steel_block_stanok_is_equipment
test_russian_steel_block_rolgeng_is_conveyor
test_flat_drawing_mode_detected
test_flat_drawing_mode_ignores_layer
test_flat_drawing_mode_uses_geometry
test_cold_rolled_improves_classification
```

**验收口径**:
- cold_rolled 的 classified_ratio 从 1.5% → 10%+
- cold_rolled overall 从 0.03 → 0.10+

---

## 4. 实施节奏与回归策略

### 依赖关系

```
IMP-06 (TEXT提取) ──→ IMP-08 (KNN传播) ──→ IMP-09 (闭环迭代)
IMP-07 (概念层次) ──→ IMP-08
IMP-10 (冷轧领域) ── 并行，无依赖
```

### 实施顺序

```
Step 1:  IMP-06 (TEXT提取+空间关联) → RED → GREEN → 回归
         IMP-07 (概念层次树)         → RED → GREEN → 回归
         IMP-10 (冷轧领域词典)       → RED → GREEN → 回归 (并行)
Step 2:  IMP-08 (KNN空间传播)       → RED → GREEN → 回归
Step 3:  IMP-09 (闭环迭代)          → RED → GREEN → 回归
         全量 LLM 重评估 → 对比 overall 提升
```

### 回归策略

每个 IMP 完成后:
1. **单元测试**: 新增用例全部 GREEN
2. **存量回归**: 91 条 P0 测试全部 PASS (49 原始 + 42 Phase 1)
3. **质量回归**: 重跑 `scripts/quality_matrix_llm.py` 验证 overall 分数提升
4. **无退化**: 任何文件的 overall 不得低于改进前的分数

### 预期效果

| 阶段 | 预期平均 overall | 提升幅度 |
|---|---|---|
| Phase 1 完成 (IMP-01~05) | 0.27 ✅ | +0.12 (实际) |
| Phase 2: IMP-06+07+10 | 0.35~0.40 | +0.08~0.13 |
| Phase 2: IMP-08 | 0.40~0.45 | +0.05 |
| Phase 2: IMP-09 | 0.45~0.50 | +0.05 |

---

## 5. 风险与约束

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| AssetType 扩展导致下游 Agent 不兼容 | 高 | 新增类型向下兼容 OTHER; 下游按需 fallback |
| 多语言字典维护成本 | 中 | 仅加入已验证的 LLM 推荐条目; 后续按需扩展 |
| 坐标过滤误杀正常实体 | 中 | 仅标记 (is_suspect) 不删除; 低阈值保守启动 |
| Block 坐标修复需深度 ezdxf 改动 | 高 | 延后到 Phase 3; 先用过滤策略缓解 |
| LLM 评估成本 (每次 ~30s ×8 ≈ 4min) | 低 | 仅阶段里程碑时执行; 日常用规则矩阵 |

---

## 6. 度量与验收总表

| 改进编号 | 关键度量 | 改进前 | 目标值 | 验证方式 |
|---|---|---|---|---|
| IMP-01~05 | 8 份平均 LLM overall | 0.15 | 0.27 ✅ | LLM 评估 |
| IMP-06 | semantic_richness 平均 | 0.18 | 0.30+ | LLM 评估 |
| IMP-07 | OTHER 比例下降 | ~60% | ~45% | dump 统计 |
| IMP-08 | 高密度区域 confidence | ~0.35 | ~0.50 | dump 统计 |
| IMP-09 | 管线平均迭代轮数 | 1 | ≤2 | 日志 |
| IMP-10 | cold_rolled overall | 0.03 | 0.10+ | LLM 评估 |
| 全局 | 8 份平均 LLM overall | 0.27 | **0.45+** | LLM 重评估 |
| 全局 | 存量回归 | 91/91 | 91+/91+ | pytest |
