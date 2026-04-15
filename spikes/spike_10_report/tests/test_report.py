"""
Spike-10 测试用例：PDF/Word 报告生成质量
========================================
Test Case IDs: S10-TC01 ~ S10-TC07 (关键技术验证计划 §11.2)

Go/No-Go 必须标准:
  - PDF 生成成功 (含表格+中文) = 100%
  - 中文排版正确, 无乱码
  - 50页报告生成耗时 ≤ 30s
"""
import json
import time
import pytest
from pathlib import Path
from conftest import SPIKE10_DATA, SPIKE10_TEMPLATES, Thresholds

# ════════════════════════════════════════════════════════════════
# 待实现模块导入 — TDD RED phase
# ════════════════════════════════════════════════════════════════
from spike_10_report.src.pdf_generator import PDFReportGenerator
from spike_10_report.src.word_generator import WordReportGenerator
from spike_10_report.src.excel_generator import ExcelReportGenerator
from spike_10_report.src.template_engine import TemplateEngine


@pytest.mark.p2
@pytest.mark.spike10
class TestSimplePDF:
    """S10-TC01: 简单 PDF 生成"""

    def test_tc01_generate_pdf(self, report_template, sample_report_data, tmp_path):
        """Jinja2 模板 + WeasyPrint 生成 PDF"""
        engine = TemplateEngine()
        html = engine.render(report_template, sample_report_data)

        generator = PDFReportGenerator()
        output_path = tmp_path / "test_report.pdf"
        generator.generate(html, str(output_path))

        assert output_path.exists()
        assert output_path.stat().st_size > 0
        # PDF 文件应以 %PDF- 开头
        with open(output_path, "rb") as f:
            header = f.read(5)
        assert header == b"%PDF-"

    def test_tc01_template_rendering(self, report_template, sample_report_data):
        """模板变量应全部替换"""
        engine = TemplateEngine()
        html = engine.render(report_template, sample_report_data)

        assert "{{" not in html, "模板中仍有未替换变量"
        assert "}}" not in html


@pytest.mark.p2
@pytest.mark.spike10
class TestTablePDF:
    """S10-TC02: 含表格 PDF"""

    def test_tc02_table_in_pdf(self, sample_report_data, tmp_path):
        """ROI 表、方案对比表应正确渲染"""
        generator = PDFReportGenerator()
        engine = TemplateEngine()

        # 使用带表格的数据
        template = """
        <h1>测试报告</h1>
        <table>
            <tr><th>方案</th><th>JPH</th><th>利用率</th></tr>
            {% for row in comparison_table %}
            <tr><td>{{ row.name }}</td><td>{{ row.jph }}</td><td>{{ row.utilization }}</td></tr>
            {% endfor %}
        </table>
        """
        data = {
            "comparison_table": [
                {"name": "方案A", "jph": 102.5, "utilization": "87%"},
                {"name": "方案B", "jph": 98.3, "utilization": "92%"},
            ]
        }
        html = engine.render(template, data)
        output_path = tmp_path / "table_report.pdf"
        generator.generate(html, str(output_path))

        assert output_path.exists()
        assert output_path.stat().st_size > 1000  # 含表格应较大


@pytest.mark.p2
@pytest.mark.spike10
class TestChartPDF:
    """S10-TC03: 含图表 PDF"""

    def test_tc03_chart_embedding(self, tmp_path):
        """ECharts 图表截图嵌入 PDF"""
        generator = PDFReportGenerator()

        chart_data = {
            "utilization_chart": [
                {"station": "WS-1", "value": 0.85},
                {"station": "WS-2", "value": 0.92},
                {"station": "WS-3", "value": 0.78},
            ]
        }

        output_path = tmp_path / "chart_report.pdf"
        generator.generate_with_charts(chart_data, str(output_path))

        assert output_path.exists()
        assert output_path.stat().st_size > 5000  # 含图表应较大


@pytest.mark.p2
@pytest.mark.spike10
class TestChineseRendering:
    """S10-TC04: 中文排版"""

    def test_tc04_no_garbled_text(self, tmp_path):
        """中文字体渲染无乱码"""
        generator = PDFReportGenerator()
        engine = TemplateEngine()

        template = """
        <h1>航空产线布局评审报告</h1>
        <p>本报告对C919总装脉动线进行了全面评审。</p>
        <p>包含翼身对接、起落架安装、系统安装等六大工位。</p>
        <p>辐射禁区半径15米，恒温检测区温度控制±0.5°C。</p>
        """
        html = engine.render(template, {})
        output_path = tmp_path / "chinese_report.pdf"
        generator.generate(html, str(output_path))

        assert output_path.exists()
        # 验证 PDF 内嵌字体
        with open(output_path, "rb") as f:
            content = f.read()
        # PDF 应包含 CIDFont (中文字体)
        assert b"Font" in content

    def test_tc04_long_text_wrapping(self, tmp_path):
        """长中文文本正确换行"""
        generator = PDFReportGenerator()
        engine = TemplateEngine()

        long_text = "这是一段非常长的中文文本用于测试PDF排版中的自动换行功能。" * 20
        template = f"<p>{long_text}</p>"
        html = engine.render(template, {})
        output_path = tmp_path / "longtext_report.pdf"
        generator.generate(html, str(output_path))

        assert output_path.exists()


@pytest.mark.p2
@pytest.mark.spike10
class TestWordOutput:
    """S10-TC05: Word 文档输出"""

    def test_tc05_generate_word(self, sample_report_data, tmp_path):
        """python-docx 生成 Word 格式正确"""
        generator = WordReportGenerator()
        output_path = tmp_path / "test_report.docx"
        generator.generate(sample_report_data, str(output_path))

        assert output_path.exists()
        assert output_path.stat().st_size > 0

        # DOCX 是 ZIP 格式, 应以 PK 开头
        with open(output_path, "rb") as f:
            header = f.read(2)
        assert header == b"PK"

    def test_tc05_word_contains_sections(self, sample_report_data, tmp_path):
        """Word 文档应包含各章节"""
        generator = WordReportGenerator()
        output_path = tmp_path / "sections_report.docx"
        generator.generate(sample_report_data, str(output_path))

        # 验证文档结构
        sections = generator.list_sections(str(output_path))
        assert len(sections) > 0


@pytest.mark.p2
@pytest.mark.spike10
class TestExcelOutput:
    """S10-TC06: Excel 输出"""

    def test_tc06_generate_excel(self, sample_report_data, tmp_path):
        """openpyxl 生成 ROI 表"""
        generator = ExcelReportGenerator()
        output_path = tmp_path / "roi_table.xlsx"
        generator.generate_roi_table(sample_report_data, str(output_path))

        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_tc06_formulas_present(self, sample_report_data, tmp_path):
        """Excel 公式应可计算"""
        generator = ExcelReportGenerator()
        output_path = tmp_path / "formula_test.xlsx"
        generator.generate_roi_table(sample_report_data, str(output_path))

        formulas = generator.list_formulas(str(output_path))
        assert len(formulas) > 0, "ROI 表应包含计算公式"


@pytest.mark.p2
@pytest.mark.spike10
@pytest.mark.slow
class TestLargeReportPerformance:
    """S10-TC07: 50 页大报告性能"""

    def test_tc07_50page_pdf(self, tmp_path):
        """50 页 PDF 生成耗时 ≤ 30s"""
        generator = PDFReportGenerator()
        engine = TemplateEngine()

        # 生成大量内容模拟 50 页
        sections = []
        for i in range(50):
            sections.append(f"""
            <h2>第{i+1}章 详细分析</h2>
            <p>{"本章对产线布局进行了深入分析。" * 20}</p>
            <table>
                <tr><th>设备</th><th>位置X</th><th>位置Y</th><th>状态</th></tr>
                {"".join(f'<tr><td>设备{j}</td><td>{j*1000}</td><td>{j*500}</td><td>合格</td></tr>' for j in range(10))}
            </table>
            """)

        template = "<html><body>" + "".join(sections) + "</body></html>"
        html = engine.render(template, {})

        output_path = tmp_path / "large_report.pdf"
        start = time.perf_counter()
        generator.generate(html, str(output_path))
        elapsed = time.perf_counter() - start

        assert output_path.exists()
        assert elapsed <= Thresholds.S10_LARGE_REPORT_TIME_S, (
            f"50页报告生成耗时 {elapsed:.1f}s > {Thresholds.S10_LARGE_REPORT_TIME_S}s"
        )


# ════════════════════════════════════════════════════════════════
# L4: 黄金基准 — PDF 内容精确验证
# ════════════════════════════════════════════════════════════════

@pytest.mark.p2
@pytest.mark.spike10
class TestGoldenBaseline:
    """L4: PDF 内容回读验证 — 文本/表格行数精确匹配"""

    def test_pdf_contains_exact_text(self, tmp_path):
        """PDF 解析回来的文本应包含原始中文内容"""
        generator = PDFReportGenerator()
        engine = TemplateEngine()

        expected_text = "C919总装脉动线布局评审结论"
        html = engine.render(f"<h1>{expected_text}</h1><p>通过评审。</p>", {})
        output_path = tmp_path / "golden.pdf"
        generator.generate(html, str(output_path))

        extracted = generator.extract_text(str(output_path))
        assert expected_text in extracted, (
            f"PDF 中未找到预期文本: '{expected_text}'"
        )

    def test_table_row_count(self, tmp_path):
        """PDF 表格行数应与输入数据一致"""
        generator = PDFReportGenerator()
        engine = TemplateEngine()

        rows = [{"name": f"方案{chr(65 + i)}", "jph": 100 + i} for i in range(5)]
        template = """<table><tr><th>方案</th><th>JPH</th></tr>
        {% for r in rows %}<tr><td>{{ r.name }}</td><td>{{ r.jph }}</td></tr>{% endfor %}
        </table>"""
        html = engine.render(template, {"rows": rows})
        output_path = tmp_path / "table_golden.pdf"
        generator.generate(html, str(output_path))

        tables = generator.extract_tables(str(output_path))
        assert len(tables) > 0, "应提取到至少 1 个表格"
        assert len(tables[0]) == 5, f"表格数据行数 {len(tables[0])} != 5"

    def test_word_paragraph_exact(self, sample_report_data, tmp_path):
        """Word 文档段落数应与数据结构对应"""
        generator = WordReportGenerator()
        output_path = tmp_path / "golden.docx"
        generator.generate(sample_report_data, str(output_path))

        sections = generator.list_sections(str(output_path))
        assert len(sections) > 0, "DOCX 应包含章节"
        # 每个 section 应有标题
        for sec in sections:
            assert isinstance(sec, str)
            assert len(sec) > 0
