"""ParseAgent 功能测试 — 共享 fixtures。

为 PT-P0 系列测试用例提供:
- 真实 DWG 文件路径 (绑定 real_world 测试数据)
- ParseService 单例
- 输入组映射 (与功能测试计划 §6 对齐)
"""
import pytest
from pathlib import Path

from agents.parse_agent.service import ParseService

# ──────────────── 路径常量 ────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # Epic01_ProLine_CAD/
REAL_WORLD = PROJECT_ROOT / "spikes" / "spike_01_dwg_parse" / "test_data" / "real_world"


# ──────────────── ParseService fixture ────────────────

@pytest.fixture(scope="session")
def parse_service():
    """全局唯一 ParseService 实例。"""
    return ParseService()


# ──────────────── 输入组 A: P0 基线组 ────────────────

@pytest.fixture(scope="session")
def g_p0_base_01() -> Path:
    """G-P0-BASE-01: 20180109_机加车间平面布局图.dwg — 必选主样本。"""
    p = REAL_WORLD / "20180109_机加车间平面布局图.dwg"
    if not p.exists():
        pytest.skip(f"测试数据文件不存在: {p}")
    return p


@pytest.fixture(scope="session")
def g_p0_base_02() -> Path:
    """G-P0-BASE-02: cold_rolled_steel_production.dwg — 基线补充。"""
    p = REAL_WORLD / "cold_rolled_steel_production.dwg"
    if not p.exists():
        pytest.skip(f"测试数据文件不存在: {p}")
    return p


# ──────────────── 输入组 C: 业务语义组 ────────────────

@pytest.fixture(scope="session")
def g_sem_02() -> Path:
    """G-SEM-02: cold_rolled_steel_production.dwg — 产线流程型语义。"""
    p = REAL_WORLD / "cold_rolled_steel_production.dwg"
    if not p.exists():
        pytest.skip(f"测试数据文件不存在: {p}")
    return p


# ──────────────── 输入组 D: 版本兼容组 ────────────────

@pytest.fixture(scope="session")
def g_ver_2000() -> Path:
    """G-VER-2000: example_2000.dwg — R2000 版本。"""
    p = REAL_WORLD / "example_2000.dwg"
    if not p.exists():
        pytest.skip(f"测试数据文件不存在: {p}")
    return p


@pytest.fixture(scope="session")
def g_ver_2007() -> Path:
    """G-VER-2007: example_2007.dwg — R2007 版本。"""
    p = REAL_WORLD / "example_2007.dwg"
    if not p.exists():
        pytest.skip(f"测试数据文件不存在: {p}")
    return p


@pytest.fixture(scope="session")
def g_ver_2018() -> Path:
    """G-VER-2018: example_2018.dwg — R2018 版本。"""
    p = REAL_WORLD / "example_2018.dwg"
    if not p.exists():
        pytest.skip(f"测试数据文件不存在: {p}")
    return p
