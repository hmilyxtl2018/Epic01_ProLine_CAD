"""坐标对齐器 — Stub"""
from dataclasses import dataclass, field


@dataclass
class AlignmentResult:
    max_error_mm: float = 0.0
    mean_error_mm: float = 0.0
    transform_params: list = field(default_factory=list)
    passed: bool = False

    def forward(self, point: list) -> list:
        raise NotImplementedError


class CoordinateAligner:
    def align(self, ref_points: list) -> AlignmentResult:
        raise NotImplementedError("CoordinateAligner.align 尚未实现")
