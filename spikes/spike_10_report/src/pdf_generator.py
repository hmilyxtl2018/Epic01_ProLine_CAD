"""PDF 报告生成器 — Stub"""


class PDFReportGenerator:
    def generate(self, html: str, output_path: str):
        raise NotImplementedError

    def generate_with_charts(self, chart_data: dict, output_path: str):
        raise NotImplementedError

    def extract_text(self, pdf_path: str) -> str:
        """从 PDF 提取纯文本 (用于 L4 黄金基准验证)"""
        raise NotImplementedError

    def extract_tables(self, pdf_path: str) -> list[list]:
        """从 PDF 提取表格数据 (用于 L4 黄金基准验证)"""
        raise NotImplementedError
