"""
Spike-1 测试用例：DWG/RVT 底图解析可行性
==========================================
Test Case IDs: S1-TC01 ~ S1-TC06 (关键技术验证计划 §2.3)

Go/No-Go 必须标准:
  - DWG 解析成功率 = 100%
  - 图层识别率 ≥ 85% (有映射表)
  - 坐标对齐误差 ≤ 10mm
  - 大文件内存 ≤ 2GB, 耗时 ≤ 30s
"""
import json
import time
import tracemalloc
import pytest
from pathlib import Path
from conftest import SPIKE1_DATA, SPIKE1_REAL, Thresholds

# ════════════════════════════════════════════════════════════════
# 待实现模块导入 — TDD RED phase: 这些模块尚未实现
# 开发者需要创建这些模块使测试通过
# ════════════════════════════════════════════════════════════════
from spike_01_dwg_parse.src.dwg_parser import DWGParser
from spike_01_dwg_parse.src.layer_mapper import LayerSemanticMapper
from spike_01_dwg_parse.src.coordinate_aligner import CoordinateAligner


# ──────────────────── 图层语义映射表 ────────────────────
# 航空制造产线标准图层 → 语义分类
LAYER_SEMANTIC_MAP = {
    # 结构层
    "WALL": "structure",
    "COLUMN": "structure",
    "GRID": "structure",
    "BOUNDARY": "structure",
    # 设备层
    "EQUIPMENT": "equipment",
    "WORKSTATION": "equipment",
    "CRANE": "equipment",
    "AGV_TRACK": "equipment",
    # 安全/禁区层
    "SAFETY_ZONE": "exclusion",
    "EXCLUSION": "exclusion",
    "FOD_ZONE": "exclusion",
    "RADIATION_ZONE": "exclusion",
    "CLEAN_ZONE": "exclusion",
    "CHEMICAL_ZONE": "exclusion",
    # 辅助层
    "FLOW_LINE": "auxiliary",
    "ANNOTATION": "auxiliary",
    "DIMENSION": "auxiliary",
    "HATCH": "auxiliary",
    "REFERENCE_POINT": "auxiliary",
    "TEXT": "auxiliary",
}


@pytest.mark.p0
@pytest.mark.spike1
class TestDWGParse:
    """S1-TC01: 标准产线 DXF 解析 — 实体数量与图层一致性"""

    def test_tc01_tier1_parse_entities(self, tier1_dxf_path):
        """解析 Tier-1 (60×30m 车间), 验证实体数量与图层提取"""
        parser = DWGParser()
        result = parser.parse(str(tier1_dxf_path))

        assert result is not None, "解析结果不应为 None"
        assert result.total_entities > 0, "实体数量应 > 0"
        assert result.layer_count > 0, "图层数量应 > 0"
        assert isinstance(result.layers, dict), "图层字典格式"

        # Tier-1 已知约 99 个实体 (来自 preview 统计)
        expected_entities = 99
        diff_pct = abs(result.total_entities - expected_entities) / expected_entities * 100
        assert diff_pct <= Thresholds.S1_ENTITY_DIFF_PCT, (
            f"实体数量差异 {diff_pct:.1f}% 超过阈值 {Thresholds.S1_ENTITY_DIFF_PCT}%"
        )

    def test_tc01_tier2_parse_entities(self, tier2_dxf_path):
        """解析 Tier-2 (150×80m 设施), 验证实体数量"""
        parser = DWGParser()
        result = parser.parse(str(tier2_dxf_path))

        assert result.total_entities > 0
        expected_entities = 286
        diff_pct = abs(result.total_entities - expected_entities) / expected_entities * 100
        assert diff_pct <= Thresholds.S1_ENTITY_DIFF_PCT

    def test_tc01_tier3_parse_entities(self, tier3_dxf_path):
        """解析 Tier-3 (300×120m FAL), 验证实体数量"""
        parser = DWGParser()
        result = parser.parse(str(tier3_dxf_path))

        assert result.total_entities > 0
        expected_entities = 358
        diff_pct = abs(result.total_entities - expected_entities) / expected_entities * 100
        assert diff_pct <= Thresholds.S1_ENTITY_DIFF_PCT

    def test_tc01_layer_extraction(self, tier2_dxf_path):
        """验证图层名称完整提取"""
        parser = DWGParser()
        result = parser.parse(str(tier2_dxf_path))

        expected_layers = {
            "WALL", "COLUMN", "EQUIPMENT", "SAFETY_ZONE",
            "CRANE", "EXCLUSION", "FLOW_LINE",
        }
        actual_layers = set(result.layers.keys())
        # 至少包含核心图层
        missing = expected_layers - actual_layers
        assert len(missing) == 0, f"缺失核心图层: {missing}"

    def test_tc01_output_json_format(self, tier1_dxf_path):
        """验证解析结果可序列化为 JSON (SiteModel 格式)"""
        parser = DWGParser()
        result = parser.parse(str(tier1_dxf_path))

        site_model = result.to_site_model()
        json_str = json.dumps(site_model, ensure_ascii=False)
        parsed_back = json.loads(json_str)

        assert "site_guid" in parsed_back
        assert "layers" in parsed_back
        assert "entities" in parsed_back
        assert "bounding_box" in parsed_back


@pytest.mark.p0
@pytest.mark.spike1
class TestLayerSemanticMapping:
    """S1-TC02: 非标准图层命名 — 语义分类准确率 ≥ 85%"""

    def test_tc02_mapping_accuracy(self, tier2_dxf_path):
        """使用映射表分类实体, 识别率 ≥ 85%"""
        parser = DWGParser()
        result = parser.parse(str(tier2_dxf_path))

        mapper = LayerSemanticMapper(LAYER_SEMANTIC_MAP)
        classification = mapper.classify(result.layers)

        assert classification.accuracy >= Thresholds.S1_LAYER_CLASSIFY_RATE, (
            f"语义分类准确率 {classification.accuracy:.2%} "
            f"低于阈值 {Thresholds.S1_LAYER_CLASSIFY_RATE:.0%}"
        )

    def test_tc02_all_categories_present(self, tier2_dxf_path):
        """验证四大语义分类均有实体"""
        parser = DWGParser()
        result = parser.parse(str(tier2_dxf_path))

        mapper = LayerSemanticMapper(LAYER_SEMANTIC_MAP)
        classification = mapper.classify(result.layers)

        for category in ["structure", "equipment", "exclusion", "auxiliary"]:
            assert classification.category_count(category) > 0, (
                f"语义分类 '{category}' 无实体"
            )

    def test_tc02_unknown_layer_handling(self):
        """非映射表中的图层应归入 'unclassified'"""
        mapper = LayerSemanticMapper(LAYER_SEMANTIC_MAP)
        layers = {"RANDOM_LAYER_XYZ": 10, "EQUIPMENT": 20}
        classification = mapper.classify(layers)

        assert classification.unclassified_count > 0
        assert classification.classified_count >= 20


@pytest.mark.p0
@pytest.mark.spike1
class TestCoordinateAlignment:
    """S1-TC04: 坐标对齐精度 — 仿射变换后误差 ≤ 10mm"""

    def test_tc04_alignment_error_within_threshold(
        self, reference_points_dxf_path, reference_points_mapping
    ):
        """3 个参考点仿射变换, 验证误差 ≤ 10mm"""
        aligner = CoordinateAligner()

        ref_points = reference_points_mapping["reference_points"]
        result = aligner.align(ref_points)

        assert result.max_error_mm <= Thresholds.S1_COORD_ERROR_MM, (
            f"最大对齐误差 {result.max_error_mm:.2f}mm "
            f"超过阈值 {Thresholds.S1_COORD_ERROR_MM}mm"
        )

    def test_tc04_mean_error(self, reference_points_mapping):
        """平均误差应远小于最大误差阈值"""
        aligner = CoordinateAligner()
        ref_points = reference_points_mapping["reference_points"]
        result = aligner.align(ref_points)

        assert result.mean_error_mm <= Thresholds.S1_COORD_ERROR_MM / 2, (
            f"平均误差 {result.mean_error_mm:.2f}mm 偏高"
        )

    def test_tc04_transform_matrix_valid(self, reference_points_mapping):
        """变换矩阵参数应有效（非NaN/Inf）"""
        import math

        aligner = CoordinateAligner()
        ref_points = reference_points_mapping["reference_points"]
        result = aligner.align(ref_points)

        for param in result.transform_params:
            assert math.isfinite(param), f"变换参数含非法值: {param}"

    def test_tc04_inverse_transform(self, reference_points_mapping):
        """正向→逆向变换后应恢复原始坐标"""
        aligner = CoordinateAligner()
        ref_points = reference_points_mapping["reference_points"]
        result = aligner.align(ref_points)

        for rp in ref_points:
            dwg_pt = rp["dwg"]
            real_pt = rp["real"]
            transformed = result.forward(dwg_pt)
            # 变换后应接近 real 坐标
            dist = ((transformed[0] - real_pt[0]) ** 2 + (transformed[1] - real_pt[1]) ** 2) ** 0.5
            assert dist <= Thresholds.S1_COORD_ERROR_MM


@pytest.mark.p0
@pytest.mark.spike1
@pytest.mark.slow
class TestLargeFilePerformance:
    """S1-TC03: 大文件 DWG 处理 — 内存 ≤ 2GB, 耗时 ≤ 30s"""

    def test_tc03_tier3_memory(self, tier3_dxf_path):
        """Tier-3 (300×120m FAL) 解析内存 ≤ 2GB"""
        parser = DWGParser()

        tracemalloc.start()
        _ = parser.parse(str(tier3_dxf_path))
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / 1024 / 1024
        assert peak_mb <= Thresholds.S1_LARGE_FILE_MEMORY_MB, (
            f"峰值内存 {peak_mb:.0f}MB 超过阈值 {Thresholds.S1_LARGE_FILE_MEMORY_MB}MB"
        )

    def test_tc03_tier3_time(self, tier3_dxf_path):
        """Tier-3 解析耗时 ≤ 30s"""
        parser = DWGParser()

        start = time.perf_counter()
        _ = parser.parse(str(tier3_dxf_path))
        elapsed = time.perf_counter() - start

        assert elapsed <= Thresholds.S1_LARGE_FILE_TIME_S, (
            f"解析耗时 {elapsed:.1f}s 超过阈值 {Thresholds.S1_LARGE_FILE_TIME_S}s"
        )


@pytest.mark.p0
@pytest.mark.spike1
class TestCorruptedFile:
    """S1-TC06: 损坏 DWG 文件 — 优雅失败 + 错误码 5001"""

    def test_tc06_graceful_failure(self, corrupted_dxf_path):
        """损坏文件不应导致崩溃"""
        parser = DWGParser()
        result = parser.parse(str(corrupted_dxf_path))

        assert result.success is False, "损坏文件应解析失败"
        assert result.error_code == Thresholds.S1_ERROR_CODE_CORRUPT, (
            f"错误码应为 {Thresholds.S1_ERROR_CODE_CORRUPT}, 实际: {result.error_code}"
        )

    def test_tc06_error_message(self, corrupted_dxf_path):
        """失败结果应包含有意义的错误信息"""
        parser = DWGParser()
        result = parser.parse(str(corrupted_dxf_path))

        assert result.error_message is not None
        assert len(result.error_message) > 0

    def test_tc06_nonexistent_file(self):
        """不存在的文件路径应优雅失败"""
        parser = DWGParser()
        result = parser.parse("/nonexistent/path/file.dwg")

        assert result.success is False
        assert result.error_code is not None


@pytest.mark.p0
@pytest.mark.spike1
class TestRealWorldDWG:
    """S1-TC01 扩展: 真实 DWG 文件兼容性验证"""

    def test_real_dxf_all_parseable(self, real_dxf_paths):
        """所有 ezdxf 示例 DXF 均可成功解析"""
        parser = DWGParser()
        failed = []
        for dxf_path in real_dxf_paths:
            result = parser.parse(str(dxf_path))
            if not result.success:
                failed.append(dxf_path.name)

        assert len(failed) == 0, f"解析失败的文件: {failed}"

    def test_real_dxf_entity_types(self, real_dxf_paths):
        """真实 DXF 应包含多种实体类型"""
        parser = DWGParser()
        all_entity_types = set()
        for dxf_path in real_dxf_paths:
            result = parser.parse(str(dxf_path))
            if result.success:
                all_entity_types.update(result.entity_types)

        # 至少应包含 LINE, ARC, TEXT 等基础类型
        assert len(all_entity_types) >= 3, (
            f"实体类型过少: {all_entity_types}"
        )


@pytest.mark.p0
@pytest.mark.spike1
@pytest.mark.integration
class TestRVTConversion:
    """S1-TC05: RVT → IFC 转换可行性 (需要外部工具)"""

    @pytest.mark.skip(reason="需要 Revit/IFC OpenShell 环境, PoC 阶段可选")
    def test_tc05_rvt_to_ifc(self):
        """RVT 转 IFC 后可解析房间/构件/空间信息"""
        parser = DWGParser()
        result = parser.parse_ifc("test_data/sample.ifc")
        assert result.success
        assert result.rooms_count > 0



# ════════════════════════════════════════════════════════════════
# 边界条件与错误路径
# ════════════════════════════════════════════════════════════════

@pytest.mark.p0
@pytest.mark.spike1
class TestEdgeCases:
    """边界条件 — 仅保留 DWG 领域有意义的检查"""

    def test_parse_idempotent(self, tier1_dxf_path):
        """同一文件解析两次结果应完全一致"""
        parser = DWGParser()
        r1 = parser.parse(str(tier1_dxf_path))
        r2 = parser.parse(str(tier1_dxf_path))
        assert r1.total_entities == r2.total_entities
        assert r1.layers == r2.layers
        assert r1.entity_types == r2.entity_types
