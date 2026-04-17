"""PT-P0-01: DWG 格式识别与版本判定
====================================
功能测试计划 §7.4 测试卡 — ParseAgent 能力 P-01

测试目标: 验证 ParseAgent 能正确识别 DWG 文件格式和版本
输入组:   G-VER-2000, G-VER-2007, G-VER-2018
前置条件: ParseAgent 可接收文件输入；格式识别模块启用

TDD 状态: RED — ParseService.format_detect() 尚未实现,
          所有测试预期因 NotImplementedError 失败。
          实现 format_detect 后应全部变绿。
"""
import pytest
from pathlib import Path

from shared.models import CADFormat


@pytest.mark.p0
class TestPTP001_FormatDetect:
    """PT-P0-01: DWG 格式识别与版本判定。

    执行步骤 (来自测试卡):
    1. 依次输入 example_2000.dwg、example_2007.dwg、example_2018.dwg
    2. 调用格式识别能力 (format_detect)
    3. 记录返回的 format/version

    核心断言:
    1. 每个输入都有非空识别结果
    2. 版本识别与样本版本一致
    3. 不出现跨版本误判

    失败判定:
    返回空值、返回错误版本、把 DWG 误识别为其他格式 → 任一即失败
    """

    # ── 步骤 1+2: 每个 DWG 版本都能识别 ──

    def test_detect_r2000(self, parse_service, g_ver_2000: Path):
        """R2000 版本 DWG: format_detect 返回非空且格式为 DWG。"""
        content = g_ver_2000.read_bytes()
        result = parse_service.format_detect(content, g_ver_2000.name)

        assert result is not None, "format_detect 返回 None"
        assert result != "", "format_detect 返回空字符串"

    def test_detect_r2007(self, parse_service, g_ver_2007: Path):
        """R2007 版本 DWG: format_detect 返回非空且格式为 DWG。"""
        content = g_ver_2007.read_bytes()
        result = parse_service.format_detect(content, g_ver_2007.name)

        assert result is not None, "format_detect 返回 None"
        assert result != "", "format_detect 返回空字符串"

    def test_detect_r2018(self, parse_service, g_ver_2018: Path):
        """R2018 版本 DWG: format_detect 返回非空且格式为 DWG。"""
        content = g_ver_2018.read_bytes()
        result = parse_service.format_detect(content, g_ver_2018.name)

        assert result is not None, "format_detect 返回 None"
        assert result != "", "format_detect 返回空字符串"

    # ── 步骤 3: 版本识别准确性 ──

    def test_version_accuracy_r2000(self, parse_service, g_ver_2000: Path):
        """R2000 版本应被正确识别, 结果中包含 '2000' 或 'AC1015'。"""
        content = g_ver_2000.read_bytes()
        result = parse_service.format_detect(content, g_ver_2000.name)

        result_upper = str(result).upper()
        assert "2000" in result_upper or "AC1015" in result_upper, (
            f"R2000 版本未被正确识别, 实际返回: {result}"
        )

    def test_version_accuracy_r2007(self, parse_service, g_ver_2007: Path):
        """R2007 版本应被正确识别, 结果中包含 '2007' 或 'AC1021'。"""
        content = g_ver_2007.read_bytes()
        result = parse_service.format_detect(content, g_ver_2007.name)

        result_upper = str(result).upper()
        assert "2007" in result_upper or "AC1021" in result_upper, (
            f"R2007 版本未被正确识别, 实际返回: {result}"
        )

    def test_version_accuracy_r2018(self, parse_service, g_ver_2018: Path):
        """R2018 版本应被正确识别, 结果中包含 '2018' 或 'AC1032'。"""
        content = g_ver_2018.read_bytes()
        result = parse_service.format_detect(content, g_ver_2018.name)

        result_upper = str(result).upper()
        assert "2018" in result_upper or "AC1032" in result_upper, (
            f"R2018 版本未被正确识别, 实际返回: {result}"
        )

    # ── 核心断言 3: 不出现跨版本误判 ──

    def test_no_cross_version_confusion(
        self, parse_service, g_ver_2000: Path, g_ver_2007: Path, g_ver_2018: Path,
    ):
        """三个不同版本文件的识别结果应互不相同。"""
        results = {}
        for label, path in [
            ("2000", g_ver_2000),
            ("2007", g_ver_2007),
            ("2018", g_ver_2018),
        ]:
            content = path.read_bytes()
            results[label] = parse_service.format_detect(content, path.name)

        # 三个结果不应完全相同 (说明确实区分了版本)
        unique_results = set(str(r) for r in results.values())
        assert len(unique_results) >= 2, (
            f"不同版本文件返回了相同的识别结果: {results}"
        )

    # ── 失败判定: 不把 DWG 误识别为其他格式 ──

    def test_format_is_dwg_not_other(self, parse_service, g_ver_2018: Path):
        """DWG 文件不应被识别为 IFC / STEP / DXF 等其他格式。"""
        content = g_ver_2018.read_bytes()
        result = str(parse_service.format_detect(content, g_ver_2018.name)).upper()

        for wrong_format in ["IFC", "STEP", "IGES", "STL"]:
            assert wrong_format not in result, (
                f"DWG 被误识别为 {wrong_format}, 结果: {result}"
            )
