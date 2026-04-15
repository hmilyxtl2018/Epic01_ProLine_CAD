"""
Spike-4 测试用例：SimPy DES 仿真精度与性能
==========================================
Test Case IDs: S4-TC01 ~ S4-TC07 (关键技术验证计划 §5.3)

Go/No-Go 必须标准:
  - 5工站确定性 JPH 误差 ≤ 1%
  - 5工站随机故障 JPH 误差 ≤ 5% (10次均值)
  - 20工站仿真耗时 ≤ 60s
  - 瓶颈识别正确性 = 100%
  - 固定 seed 结果完全一致
"""
import json
import time
import pytest
from conftest import SPIKE4_DATA, Thresholds

# ════════════════════════════════════════════════════════════════
# 待实现模块导入 — TDD RED phase
# ════════════════════════════════════════════════════════════════
from spike_04_des_sim.src.des_engine import DESEngine, StationConfig, SimResult


@pytest.mark.p1
@pytest.mark.spike4
class TestDeterministicSimulation:
    """S4-TC01: 5工站串行确定性仿真 — JPH 误差 ≤ 1%"""

    def test_tc01_5station_jph(self):
        """OEE=1.0, 理论 JPH = 3600 / max(cycle_time)"""
        stations = [
            StationConfig(name="WS-1", cycle_time_s=30),
            StationConfig(name="WS-2", cycle_time_s=25),
            StationConfig(name="WS-3", cycle_time_s=35),   # 瓶颈
            StationConfig(name="WS-4", cycle_time_s=28),
            StationConfig(name="WS-5", cycle_time_s=20),
        ]

        engine = DESEngine(seed=42)
        result = engine.run(
            stations=stations,
            sim_duration_h=8,
            warm_up_h=1,
        )

        expected_jph = 3600 / 35  # = 102.86
        error_pct = abs(result.jph - expected_jph) / expected_jph * 100

        assert error_pct <= Thresholds.S4_DETERMINISTIC_ERROR_PCT, (
            f"JPH 误差 {error_pct:.2f}% > {Thresholds.S4_DETERMINISTIC_ERROR_PCT}%"
            f" (实际={result.jph:.2f}, 理论={expected_jph:.2f})"
        )

    def test_tc01_bottleneck_is_ws3(self):
        """瓶颈应是 cycle_time 最大的 WS-3"""
        stations = [
            StationConfig(name="WS-1", cycle_time_s=30),
            StationConfig(name="WS-2", cycle_time_s=25),
            StationConfig(name="WS-3", cycle_time_s=35),
            StationConfig(name="WS-4", cycle_time_s=28),
            StationConfig(name="WS-5", cycle_time_s=20),
        ]

        engine = DESEngine(seed=42)
        result = engine.run(stations=stations, sim_duration_h=8, warm_up_h=1)

        assert result.bottleneck == "WS-3"

    def test_tc01_utilization_consistency(self):
        """瓶颈工站利用率应最高，接近 1.0"""
        stations = [
            StationConfig(name="WS-1", cycle_time_s=30),
            StationConfig(name="WS-2", cycle_time_s=25),
            StationConfig(name="WS-3", cycle_time_s=35),
            StationConfig(name="WS-4", cycle_time_s=28),
            StationConfig(name="WS-5", cycle_time_s=20),
        ]

        engine = DESEngine(seed=42)
        result = engine.run(stations=stations, sim_duration_h=8, warm_up_h=1)

        bottleneck_util = result.get_utilization("WS-3")
        assert bottleneck_util > 0.95, f"瓶颈利用率 {bottleneck_util:.2%} 偏低"

        # 非瓶颈工站利用率应低于瓶颈
        for name in ["WS-1", "WS-2", "WS-4", "WS-5"]:
            assert result.get_utilization(name) < bottleneck_util


@pytest.mark.p1
@pytest.mark.spike4
class TestStochasticSimulation:
    """S4-TC02: 5工站随机故障 — 10次均值 JPH 误差 ≤ 5%"""

    def test_tc02_stochastic_jph_average(self):
        """MTBF/MTTR 随机故障, 10次仿真均值有效"""
        stations = [
            StationConfig(name="WS-1", cycle_time_s=30, oee=0.85, mtbf_min=100, mttr_min=10),
            StationConfig(name="WS-2", cycle_time_s=25, oee=0.85, mtbf_min=120, mttr_min=8),
            StationConfig(name="WS-3", cycle_time_s=35, oee=0.85, mtbf_min=80, mttr_min=15),
            StationConfig(name="WS-4", cycle_time_s=28, oee=0.85, mtbf_min=110, mttr_min=12),
            StationConfig(name="WS-5", cycle_time_s=20, oee=0.85, mtbf_min=150, mttr_min=5),
        ]

        jph_values = []
        for seed in range(10):
            engine = DESEngine(seed=seed)
            result = engine.run(stations=stations, sim_duration_h=8, warm_up_h=1)
            jph_values.append(result.jph)

        avg_jph = sum(jph_values) / len(jph_values)
        # OEE=0.85 时理论 JPH ≈ 102.86 * 0.85 = 87.4
        expected_jph = (3600 / 35) * 0.85
        error_pct = abs(avg_jph - expected_jph) / expected_jph * 100

        assert error_pct <= Thresholds.S4_STOCHASTIC_ERROR_PCT, (
            f"10次均值 JPH 误差 {error_pct:.2f}% > {Thresholds.S4_STOCHASTIC_ERROR_PCT}%"
            f" (均值={avg_jph:.2f}, 理论={expected_jph:.2f})"
        )


@pytest.mark.p1
@pytest.mark.spike4
@pytest.mark.slow
class TestScalePerformance:
    """S4-TC03~TC05: 不同规模仿真耗时"""

    @pytest.mark.parametrize("count,threshold_s", [
        (10, Thresholds.S4_10STATION_TIME_S),
        (20, Thresholds.S4_20STATION_TIME_S),
    ], ids=["10-stations", "20-stations"])
    def test_scale_time(self, count, threshold_s):
        stations = [
            StationConfig(name=f"WS-{i+1}", cycle_time_s=25 + i * 2)
            for i in range(count)
        ]
        engine = DESEngine(seed=42)

        start = time.perf_counter()
        result = engine.run(stations=stations, sim_duration_h=8, warm_up_h=1)
        elapsed = time.perf_counter() - start

        assert elapsed <= threshold_s, (
            f"{count}工站仿真耗时 {elapsed:.1f}s > {threshold_s}s"
        )
        assert result.jph > 0

    @pytest.mark.slow
    def test_50_station_scale(self):
        """50 工站大规模仿真 ≤ 180s"""
        stations = [
            StationConfig(name=f"WS-{i+1}", cycle_time_s=20 + i)
            for i in range(50)
        ]
        engine = DESEngine(seed=42)

        start = time.perf_counter()
        result = engine.run(stations=stations, sim_duration_h=8, warm_up_h=1)
        elapsed = time.perf_counter() - start

        assert elapsed <= Thresholds.S4_50STATION_TIME_S
        assert result.jph > 0


@pytest.mark.p1
@pytest.mark.spike4
class TestReproducibility:
    """S4-TC06: 固定 seed 结果完全一致"""

    def test_tc06_identical_results(self):
        """同一 seed 运行 3 次, JPH 完全一致"""
        stations = [
            StationConfig(name="WS-1", cycle_time_s=30, mtbf_min=100, mttr_min=10),
            StationConfig(name="WS-2", cycle_time_s=25, mtbf_min=120, mttr_min=8),
            StationConfig(name="WS-3", cycle_time_s=35, mtbf_min=80, mttr_min=15),
        ]

        jph_values = []
        for _ in range(3):
            engine = DESEngine(seed=42)
            result = engine.run(stations=stations, sim_duration_h=8, warm_up_h=1)
            jph_values.append(result.jph)

        assert len(set(jph_values)) == 1, (
            f"3次 JPH 不一致: {jph_values}"
        )


@pytest.mark.p1
@pytest.mark.spike4
class TestBottleneckIdentification:
    """S4-TC07: 瓶颈识别正确性"""

    def test_tc07_obvious_bottleneck(self):
        """故意设 1 个慢工站, 应正确识别"""
        stations = [
            StationConfig(name="WS-1", cycle_time_s=20),
            StationConfig(name="WS-2", cycle_time_s=20),
            StationConfig(name="SLOW-WS", cycle_time_s=100),  # 明显瓶颈
            StationConfig(name="WS-4", cycle_time_s=20),
            StationConfig(name="WS-5", cycle_time_s=20),
        ]

        engine = DESEngine(seed=42)
        result = engine.run(stations=stations, sim_duration_h=8, warm_up_h=1)

        assert result.bottleneck == "SLOW-WS"

    def test_tc07_multiple_metrics(self):
        """输出应包含完整指标: JPH, 稼动率, 缓冲区水位"""
        stations = [
            StationConfig(name="WS-1", cycle_time_s=30),
            StationConfig(name="WS-2", cycle_time_s=35),
        ]
        engine = DESEngine(seed=42)
        result = engine.run(stations=stations, sim_duration_h=8, warm_up_h=1)

        assert result.jph > 0
        assert result.bottleneck is not None
        assert len(result.utilizations) == 2
        assert result.total_completed > 0


@pytest.mark.p1
@pytest.mark.spike4
class TestAerospaceScenarios:
    """使用 simulation_scenarios.json 航空场景验证"""

    def test_sim01_deterministic_6station(self, simulation_scenarios):
        """SIM-01: 6站脉动线确定性仿真"""
        scenario = next(
            s for s in simulation_scenarios["scenarios"]
            if s["scenario_id"] == "SIM-01-DETERMINISTIC"
        )

        stations = []
        for st in scenario["stations"]:
            stations.append(StationConfig(
                name=st["name"],
                cycle_time_s=st["cycle_time_hours"] * 3600,
            ))

        engine = DESEngine(seed=scenario["random_seed"])
        result = engine.run(
            stations=stations,
            sim_duration_h=scenario["sim_duration_hours"],
            warm_up_h=scenario["warm_up_hours"],
        )

        assert result.jph > 0
        assert result.total_completed > 0


# ════════════════════════════════════════════════════════════════
# L4: 黄金基准 — 单工站理论精确值
# ════════════════════════════════════════════════════════════════

@pytest.mark.p1
@pytest.mark.spike4
class TestGoldenBaseline:
    """L4: 可解析计算的理论值精确验证"""

    def test_single_station_exact_jph(self):
        """单工站, OEE=1.0 → JPH = 3600 / cycle_time = 120.0"""
        engine = DESEngine(seed=42)
        result = engine.run(
            stations=[StationConfig(name="WS-1", cycle_time_s=30)],
            sim_duration_h=8, warm_up_h=1,
        )
        expected = 3600 / 30
        error_pct = abs(result.jph - expected) / expected * 100
        assert error_pct <= Thresholds.S4_DETERMINISTIC_ERROR_PCT, (
            f"单工站 JPH={result.jph:.2f}, 理论={expected:.2f}"
        )

    def test_two_equal_stations_jph(self):
        """2 个相同工站串行 → JPH 仍 = 3600 / cycle_time"""
        engine = DESEngine(seed=42)
        result = engine.run(
            stations=[
                StationConfig(name="WS-1", cycle_time_s=30),
                StationConfig(name="WS-2", cycle_time_s=30),
            ],
            sim_duration_h=8, warm_up_h=1,
        )
        expected = 3600 / 30
        error_pct = abs(result.jph - expected) / expected * 100
        assert error_pct <= Thresholds.S4_DETERMINISTIC_ERROR_PCT

    def test_utilization_sum_consistent(self):
        """所有工站利用率应在 [0, 1] 范围内"""
        stations = [
            StationConfig(name=f"WS-{i+1}", cycle_time_s=20 + i * 5)
            for i in range(5)
        ]
        engine = DESEngine(seed=42)
        result = engine.run(stations=stations, sim_duration_h=8, warm_up_h=1)

        for st in stations:
            util = result.get_utilization(st.name)
            assert 0 <= util <= 1.0, (
                f"{st.name} 利用率 {util:.2f} 超出 [0,1] 范围"
            )
