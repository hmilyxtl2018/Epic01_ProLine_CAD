"""
DWG/DXF 底图解析器 — Stub (待实现)
===================================
使用 ODA File Converter + ezdxf 解析产线底图。

实现时参考:
  - 关键技术验证计划 §2.4 验证脚本框架
  - S1-TC01~TC06 测试用例
"""
from dataclasses import dataclass, field


@dataclass
class ParseResult:
    success: bool = False
    total_entities: int = 0
    layer_count: int = 0
    layers: dict = field(default_factory=dict)
    entity_types: set = field(default_factory=set)
    error_code: int | None = None
    error_message: str | None = None

    def to_site_model(self) -> dict:
        raise NotImplementedError("DWGParser.to_site_model 尚未实现")


class DWGParser:
    def parse(self, file_path: str) -> ParseResult:
        raise NotImplementedError("DWGParser.parse 尚未实现")

    def parse_ifc(self, file_path: str) -> ParseResult:
        raise NotImplementedError("DWGParser.parse_ifc 尚未实现")
