"""SimPy DES 仿真引擎 — Stub"""
from dataclasses import dataclass, field


@dataclass
class StationConfig:
    name: str = ""
    cycle_time_s: float = 0
    oee: float = 1.0
    mtbf_min: float = float("inf")
    mttr_min: float = 0
    buffer_capacity: int = 5


@dataclass
class SimResult:
    jph: float = 0.0
    total_completed: int = 0
    bottleneck: str | None = None
    utilizations: list = field(default_factory=list)
    sim_wall_time_s: float = 0.0

    def get_utilization(self, station_name: str) -> float:
        raise NotImplementedError


class DESEngine:
    def __init__(self, seed: int = 42):
        self.seed = seed

    def run(self, stations: list[StationConfig],
            sim_duration_h: float = 8, warm_up_h: float = 1) -> SimResult:
        raise NotImplementedError("DESEngine.run 尚未实现")
