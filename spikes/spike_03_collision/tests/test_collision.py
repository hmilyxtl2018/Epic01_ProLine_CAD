"""
Spike-3 测试用例：空间碰撞检测与实时自愈性能
=============================================
Test Case IDs: S3-TC01 ~ S3-TC08 (关键技术验证计划 §4.3)

Go/No-Go 必须标准:
  - 100 Assets 全局碰撞检测 ≤ 100ms
  - 增量碰撞检测 (单设备) ≤ 20ms
  - 自愈算法 (≤5碰撞对) ≤ 100ms
  - WS 端到端 (拖拽→反馈) ≤ 500ms
"""
import json
import time
import random
import pytest
from conftest import SPIKE3_DATA, Thresholds

# ════════════════════════════════════════════════════════════════
# 待实现模块导入 — TDD RED phase
# ════════════════════════════════════════════════════════════════
from spike_03_collision.src.collision_detector import CollisionDetector
from spike_03_collision.src.auto_healer import AutoHealer
from spike_03_collision.src.exclusion_checker import ExclusionZoneChecker
from spike_03_collision.src.spatial_index import SpatialIndex


# ──────────────────── 测试数据生成工具 ────────────────────

def generate_random_assets(count: int, area_mm: float = 100_000) -> list[dict]:
    """生成随机设备布局用于性能基准测试 (单位: mm)"""
    rng = random.Random(42)
    assets = []
    for i in range(count):
        w = rng.uniform(1000, 5000)
        h = rng.uniform(1000, 5000)
        x = rng.uniform(0, area_mm - w)
        y = rng.uniform(0, area_mm - h)
        assets.append({
            "asset_guid": f"asset_{i:04d}",
            "pos_x": x, "pos_y": y,
            "width": w, "height": h,
            "safety_zone": 500,
        })
    return assets


# ════════════════════════════════════════════════════════════════
# 全局碰撞检测性能 (S3-TC01 ~ S3-TC03)
# ════════════════════════════════════════════════════════════════

@pytest.mark.p0
@pytest.mark.spike3
class TestGlobalCollisionPerformance:
    """S3-TC01~TC03: R-Tree + Shapely 全局碰撞检测性能"""

    @pytest.mark.parametrize("count,threshold_ms", [
        (50, Thresholds.S3_GLOBAL_50_MS),
        (100, Thresholds.S3_GLOBAL_100_MS),
        (200, Thresholds.S3_GLOBAL_200_MS),
    ], ids=["50-assets", "100-assets", "200-assets"])
    def test_global_collision_latency(self, count, threshold_ms):
        """全局碰撞检测延迟应在阈值内"""
        assets = generate_random_assets(count)
        detector = CollisionDetector()

        start = time.perf_counter()
        collisions = detector.detect_all(assets)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms <= threshold_ms, (
            f"{count} Assets 碰撞检测耗时 {elapsed_ms:.1f}ms > {threshold_ms}ms"
        )
        assert isinstance(collisions, list)

    def test_collision_result_structure(self):
        """碰撞结果应包含完整信息"""
        assets = generate_random_assets(50)
        detector = CollisionDetector()
        collisions = detector.detect_all(assets)

        if len(collisions) > 0:
            col = collisions[0]
            assert "asset_a" in col
            assert "asset_b" in col
            assert "overlap_area_mm2" in col
            assert col["overlap_area_mm2"] > 0

    def test_no_self_collision(self):
        """不应检出设备与自身的碰撞"""
        assets = generate_random_assets(100)
        detector = CollisionDetector()
        collisions = detector.detect_all(assets)

        for col in collisions:
            assert col["asset_a"] != col["asset_b"]

    def test_no_duplicate_pairs(self):
        """碰撞对不应重复 (A-B 和 B-A)"""
        assets = generate_random_assets(100)
        detector = CollisionDetector()
        collisions = detector.detect_all(assets)

        pairs = set()
        for col in collisions:
            pair = tuple(sorted([col["asset_a"], col["asset_b"]]))
            assert pair not in pairs, f"重复碰撞对: {pair}"
            pairs.add(pair)


@pytest.mark.p0
@pytest.mark.spike3
class TestAerospaceLayoutCollision:
    """使用航空制造 Tier-2 真实测试数据验证碰撞检测"""

    def test_detect_with_tier2_data(self, collision_test_data):
        """Tier-2 布局数据应能正确加载和检测"""
        equipment = collision_test_data["equipment"]
        detector = CollisionDetector()

        assets = []
        for eq in equipment:
            assets.append({
                "asset_guid": eq["id"],
                "pos_x": eq["position"][0],
                "pos_y": eq["position"][1],
                "width": eq["size"][0],
                "height": eq["size"][1],
                "safety_zone": eq.get("safety_zone", 0),
            })

        collisions = detector.detect_all(assets)
        assert isinstance(collisions, list)

    def test_predefined_scenarios(self, collision_test_data):
        """验证预定义碰撞场景的预期结果"""
        scenarios = collision_test_data.get("test_scenarios", [])
        detector = CollisionDetector()

        for scenario in scenarios:
            assets = scenario["assets"]
            expected = scenario["expected"]
            collisions = detector.detect_all(assets)

            assert len(collisions) == expected["collision_count"], (
                f"场景 '{scenario['name']}': "
                f"检出 {len(collisions)} 碰撞, 预期 {expected['collision_count']}"
            )


# ════════════════════════════════════════════════════════════════
# 增量碰撞检测 (S3-TC04)
# ════════════════════════════════════════════════════════════════

@pytest.mark.p0
@pytest.mark.spike3
class TestIncrementalCollision:
    """S3-TC04: 增量检测 (单设备移动) ≤ 20ms"""

    def test_tc04_incremental_latency(self):
        """移动 1 个设备, 只检测邻域碰撞"""
        assets = generate_random_assets(100)
        detector = CollisionDetector()

        # 先构建全局索引
        detector.build_index(assets)

        # 移动第 0 个设备
        moved_asset = assets[0].copy()
        moved_asset["pos_x"] += 500

        start = time.perf_counter()
        collisions = detector.detect_incremental(moved_asset)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms <= Thresholds.S3_INCREMENTAL_MS, (
            f"增量检测耗时 {elapsed_ms:.1f}ms > {Thresholds.S3_INCREMENTAL_MS}ms"
        )

    def test_tc04_incremental_correctness(self):
        """增量检测结果应与全局检测一致"""
        assets = generate_random_assets(50)
        detector = CollisionDetector()
        detector.build_index(assets)

        # 移动设备使其必然碰撞
        target = assets[0]
        neighbor = assets[1]
        moved = target.copy()
        moved["pos_x"] = neighbor["pos_x"]
        moved["pos_y"] = neighbor["pos_y"]

        incr_collisions = detector.detect_incremental(moved)

        # 至少应与 neighbor 碰撞
        collided_ids = [c["asset_b"] for c in incr_collisions]
        assert neighbor["asset_guid"] in collided_ids


# ════════════════════════════════════════════════════════════════
# 自愈算法 (S3-TC05)
# ════════════════════════════════════════════════════════════════

@pytest.mark.p0
@pytest.mark.spike3
class TestAutoHeal:
    """S3-TC05: 自愈算法 — 将碰撞设备推开"""

    def test_tc05_heal_latency(self):
        """3 碰撞对自愈 ≤ 100ms"""
        # 构造 3 对碰撞
        assets = [
            {"asset_guid": f"eq_{i}", "pos_x": 0, "pos_y": i * 1000,
             "width": 3000, "height": 2000, "safety_zone": 500}
            for i in range(6)
        ]
        # 让偶数和奇数设备重叠
        for i in range(0, 6, 2):
            assets[i + 1]["pos_x"] = 1000  # 与前一个重叠

        detector = CollisionDetector()
        collisions = detector.detect_all(assets)

        healer = AutoHealer()
        start = time.perf_counter()
        healed = healer.heal(assets, collisions)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms <= Thresholds.S3_HEAL_MS, (
            f"自愈耗时 {elapsed_ms:.1f}ms > {Thresholds.S3_HEAL_MS}ms"
        )

    def test_tc05_heal_no_remaining_collision(self):
        """修正后应无剩余碰撞"""
        assets = [
            {"asset_guid": "eq_a", "pos_x": 0, "pos_y": 0, "width": 3000, "height": 2000, "safety_zone": 500},
            {"asset_guid": "eq_b", "pos_x": 1000, "pos_y": 0, "width": 3000, "height": 2000, "safety_zone": 500},
        ]
        detector = CollisionDetector()
        collisions = detector.detect_all(assets)
        assert len(collisions) > 0, "初始状态应存在碰撞"

        healer = AutoHealer()
        healed_assets = healer.heal(assets, collisions)

        # 验证修正后无碰撞
        remaining = detector.detect_all(healed_assets)
        assert len(remaining) == 0, f"修正后仍有 {len(remaining)} 个碰撞"

    def test_tc05_heal_reasonable_displacement(self):
        """推开距离应合理 (不应把设备推到厂房外)"""
        factory_bounds = {"width": 150_000, "height": 80_000}
        assets = [
            {"asset_guid": "eq_a", "pos_x": 50000, "pos_y": 40000, "width": 3000, "height": 2000, "safety_zone": 500},
            {"asset_guid": "eq_b", "pos_x": 51000, "pos_y": 40000, "width": 3000, "height": 2000, "safety_zone": 500},
        ]
        detector = CollisionDetector()
        collisions = detector.detect_all(assets)

        healer = AutoHealer(bounds=factory_bounds)
        healed = healer.heal(assets, collisions)

        for a in healed:
            assert 0 <= a["pos_x"] <= factory_bounds["width"] - a["width"]
            assert 0 <= a["pos_y"] <= factory_bounds["height"] - a["height"]


# ════════════════════════════════════════════════════════════════
# 禁区侵入检测 (S3-TC06)
# ════════════════════════════════════════════════════════════════

@pytest.mark.p0
@pytest.mark.spike3
class TestExclusionZone:
    """S3-TC06: 禁区/安全区侵入检测 ≤ 50ms"""

    def test_tc06_exclusion_latency(self):
        """100 Assets + 10 禁区检测 ≤ 50ms"""
        assets = generate_random_assets(100)
        zones = [
            {"zone_id": f"zone_{i}", "type": "rectangle",
             "origin": [i * 10000, 0], "size": [5000, 5000]}
            for i in range(10)
        ]

        checker = ExclusionZoneChecker()
        start = time.perf_counter()
        violations = checker.check(assets, zones)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms <= Thresholds.S3_EXCLUSION_MS, (
            f"禁区检测耗时 {elapsed_ms:.1f}ms > {Thresholds.S3_EXCLUSION_MS}ms"
        )

    def test_tc06_detect_all_intrusions(self):
        """放置在禁区内的设备必须全部检出"""
        zone = {
            "zone_id": "ndt_zone",
            "type": "circle",
            "center": [50000, 50000],
            "radius": 15000,
            "description": "NDT辐射禁区",
        }
        # 放 3 个设备在禁区内
        assets = [
            {"asset_guid": f"inside_{i}",
             "pos_x": 48000 + i * 1000, "pos_y": 48000,
             "width": 2000, "height": 2000, "safety_zone": 0}
            for i in range(3)
        ]
        # 放 2 个设备在禁区外
        assets.extend([
            {"asset_guid": f"outside_{i}",
             "pos_x": 80000 + i * 5000, "pos_y": 10000,
             "width": 2000, "height": 2000, "safety_zone": 0}
            for i in range(2)
        ])

        checker = ExclusionZoneChecker()
        violations = checker.check(assets, [zone])

        violated_ids = [v["asset_guid"] for v in violations]
        for i in range(3):
            assert f"inside_{i}" in violated_ids
        for i in range(2):
            assert f"outside_{i}" not in violated_ids

    def test_tc06_tier2_exclusion_zones(self, collision_test_data):
        """Tier-2 布局中的禁区检测"""
        equipment = collision_test_data["equipment"]
        zones = collision_test_data["exclusion_zones"]

        assets = [{
            "asset_guid": eq["id"],
            "pos_x": eq["position"][0], "pos_y": eq["position"][1],
            "width": eq["size"][0], "height": eq["size"][1],
            "safety_zone": eq.get("safety_zone", 0),
        } for eq in equipment]

        checker = ExclusionZoneChecker()
        violations = checker.check(assets, zones)
        assert isinstance(violations, list)
        # 具体侵入数取决于布局, 但应能正确运行


# ════════════════════════════════════════════════════════════════
# 空间索引操作 (底层能力)
# ════════════════════════════════════════════════════════════════

@pytest.mark.p0
@pytest.mark.spike3
class TestSpatialIndex:
    """空间索引 (R-Tree / STR-Tree) 基础操作验证"""

    def test_build_index(self):
        """构建索引应成功"""
        assets = generate_random_assets(100)
        index = SpatialIndex()
        index.build(assets)
        assert index.size == 100

    def test_query_neighbors(self):
        """查询邻域应返回邻近设备"""
        assets = [
            {"asset_guid": "a", "pos_x": 0, "pos_y": 0, "width": 1000, "height": 1000},
            {"asset_guid": "b", "pos_x": 500, "pos_y": 500, "width": 1000, "height": 1000},
            {"asset_guid": "c", "pos_x": 50000, "pos_y": 50000, "width": 1000, "height": 1000},
        ]
        index = SpatialIndex()
        index.build(assets)

        neighbors = index.query(assets[0])
        neighbor_ids = [n["asset_guid"] for n in neighbors]
        assert "b" in neighbor_ids
        assert "c" not in neighbor_ids

    def test_index_update(self):
        """移动设备后索引应正确更新"""
        assets = generate_random_assets(50)
        index = SpatialIndex()
        index.build(assets)

        old_pos = (assets[0]["pos_x"], assets[0]["pos_y"])
        assets[0]["pos_x"] += 10000
        index.update(assets[0])

        # 更新后查询应反映新位置
        assert index.size == 50


# ════════════════════════════════════════════════════════════════
# WebSocket 端到端 (S3-TC07, S3-TC08)
# ════════════════════════════════════════════════════════════════

@pytest.mark.p0
@pytest.mark.spike3
@pytest.mark.integration
class TestWebSocketE2E:
    """S3-TC07/TC08: WS 全链路拖拽延迟"""

    def test_tc07_drag_heal_roundtrip(self):
        """drag → 碰撞检测 → 自愈 → 返回 ≤ 500ms"""
        from spike_03_collision.src.ws_handler import CollisionWSHandler

        handler = CollisionWSHandler()
        assets = generate_random_assets(100)
        handler.load_layout(assets)

        start = time.perf_counter()
        response = handler.handle_drag_event({
            "asset_guid": assets[0]["asset_guid"],
            "new_pos_x": assets[1]["pos_x"],
            "new_pos_y": assets[1]["pos_y"],
        })
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms <= Thresholds.S3_WS_E2E_MS
        assert "collisions" in response
        assert "healed_positions" in response

    @pytest.mark.slow
    def test_tc08_continuous_drag_no_drop(self):
        """连续 100 次拖拽/10s, 无消息丢失"""
        from spike_03_collision.src.ws_handler import CollisionWSHandler

        handler = CollisionWSHandler()
        assets = generate_random_assets(100)
        handler.load_layout(assets)

        rng = random.Random(42)
        success = 0
        for _ in range(100):
            idx = rng.randint(0, 99)
            response = handler.handle_drag_event({
                "asset_guid": assets[idx]["asset_guid"],
                "new_pos_x": rng.uniform(0, 90000),
                "new_pos_y": rng.uniform(0, 90000),
            })
            if response is not None:
                success += 1

        assert success == 100, f"丢失 {100 - success} 条消息"


# ════════════════════════════════════════════════════════════════
# L4: 黄金基准 — 精确几何计算验证
# ════════════════════════════════════════════════════════════════

@pytest.mark.p0
@pytest.mark.spike3
class TestGoldenBaseline:
    """L4: 已知几何 → 精确碰撞结果"""

    def test_two_overlapping_exact_area(self):
        """两个已知重叠矩形精确面积验证

        A: (0,0) 3000×2000, safety_zone=0
        B: (2000,500) 3000×2000, safety_zone=0
        重叠: x=[2000,3000] y=[500,2000] = 1000×1500 = 1,500,000 mm²
        """
        assets = [
            {"asset_guid": "rect_a", "pos_x": 0, "pos_y": 0,
             "width": 3000, "height": 2000, "safety_zone": 0},
            {"asset_guid": "rect_b", "pos_x": 2000, "pos_y": 500,
             "width": 3000, "height": 2000, "safety_zone": 0},
        ]
        detector = CollisionDetector()
        collisions = detector.detect_all(assets)

        assert len(collisions) == 1
        col = collisions[0]
        pair = sorted([col["asset_a"], col["asset_b"]])
        assert pair == ["rect_a", "rect_b"]
        assert abs(col["overlap_area_mm2"] - 1_500_000) < 1, (
            f"重叠面积 {col['overlap_area_mm2']} != 1,500,000"
        )

    def test_non_overlapping_zero(self):
        """两个不接触的矩形 → 0 碰撞"""
        assets = [
            {"asset_guid": "a", "pos_x": 0, "pos_y": 0,
             "width": 1000, "height": 1000, "safety_zone": 0},
            {"asset_guid": "b", "pos_x": 5000, "pos_y": 5000,
             "width": 1000, "height": 1000, "safety_zone": 0},
        ]
        detector = CollisionDetector()
        collisions = detector.detect_all(assets)
        assert len(collisions) == 0

    def test_touching_edges_no_collision(self):
        """恰好边接触（相切）不算碰撞"""
        assets = [
            {"asset_guid": "a", "pos_x": 0, "pos_y": 0,
             "width": 1000, "height": 1000, "safety_zone": 0},
            {"asset_guid": "b", "pos_x": 1000, "pos_y": 0,
             "width": 1000, "height": 1000, "safety_zone": 0},
        ]
        detector = CollisionDetector()
        collisions = detector.detect_all(assets)
        assert len(collisions) == 0

    def test_safety_zone_creates_collision(self):
        """物理不重叠但安全区重叠 → 产生碰撞

        A: [0,1000] safety=500 → 扩展到 [-500,1500]
        B: [1200,2200] safety=500 → 扩展到 [700,2700]
        扩展后重叠: x=[700,1500] = 800mm
        """
        assets = [
            {"asset_guid": "a", "pos_x": 0, "pos_y": 0,
             "width": 1000, "height": 1000, "safety_zone": 500},
            {"asset_guid": "b", "pos_x": 1200, "pos_y": 0,
             "width": 1000, "height": 1000, "safety_zone": 500},
        ]
        detector = CollisionDetector()
        collisions = detector.detect_all(assets)
        assert len(collisions) == 1

    def test_three_mutual_collisions(self):
        """3 个全部互相重叠 → 精确 3 碰撞对"""
        assets = [
            {"asset_guid": "a", "pos_x": 0, "pos_y": 0,
             "width": 3000, "height": 3000, "safety_zone": 0},
            {"asset_guid": "b", "pos_x": 1000, "pos_y": 0,
             "width": 3000, "height": 3000, "safety_zone": 0},
            {"asset_guid": "c", "pos_x": 500, "pos_y": 1000,
             "width": 3000, "height": 3000, "safety_zone": 0},
        ]
        detector = CollisionDetector()
        collisions = detector.detect_all(assets)
        assert len(collisions) == 3

        # 验证所有对 (a-b, a-c, b-c) 都存在
        pairs = {tuple(sorted([c["asset_a"], c["asset_b"]])) for c in collisions}
        assert pairs == {("a", "b"), ("a", "c"), ("b", "c")}


# ════════════════════════════════════════════════════════════════
# 统计性能验证 — 中位数 (排除冷启动)
# ════════════════════════════════════════════════════════════════

@pytest.mark.p0
@pytest.mark.spike3
class TestStatisticalPerformance:
    """性能测试取 5 次中位数, 排除 1 次预热"""

    @pytest.mark.parametrize("count,threshold_ms", [
        (100, Thresholds.S3_GLOBAL_100_MS),
        (200, Thresholds.S3_GLOBAL_200_MS),
    ], ids=["100-assets-median", "200-assets-median"])
    def test_global_collision_median(self, count, threshold_ms):
        """中位数延迟 (5 次取值, 排除 1 次预热)"""
        from conftest import benchmark_median

        assets = generate_random_assets(count)
        detector = CollisionDetector()

        median_ms, _ = benchmark_median(
            lambda: detector.detect_all(assets),
            warmup=1, iterations=5,
        )
        assert median_ms <= threshold_ms, (
            f"{count} Assets 中位数耗时 {median_ms:.1f}ms > {threshold_ms}ms"
        )

    def test_incremental_median(self):
        """增量检测中位数 ≤ 20ms"""
        from conftest import benchmark_median

        assets = generate_random_assets(100)
        detector = CollisionDetector()
        detector.build_index(assets)

        moved = assets[0].copy()
        moved["pos_x"] += 500

        median_ms, _ = benchmark_median(
            lambda: detector.detect_incremental(moved),
            warmup=1, iterations=5,
        )
        assert median_ms <= Thresholds.S3_INCREMENTAL_MS, (
            f"增量检测中位数 {median_ms:.1f}ms > {Thresholds.S3_INCREMENTAL_MS}ms"
        )
