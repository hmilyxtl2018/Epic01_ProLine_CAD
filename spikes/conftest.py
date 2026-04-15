"""
ProLine CAD 技术验证 Spike 共享 Fixtures
========================================
为所有 Spike 提供统一的测试数据路径、通用工具函数和验收阈值常量。
"""
import json
import time
import statistics
import pytest
from pathlib import Path

# ──────────────────── 路径常量 ────────────────────
SPIKES_ROOT = Path(__file__).parent
PROJECT_ROOT = SPIKES_ROOT.parent

# Spike-1 路径
SPIKE1_DATA = SPIKES_ROOT / "spike_01_dwg_parse" / "test_data"
SPIKE1_REAL = SPIKE1_DATA / "real_world"

# Spike-2 路径
SPIKE2_DATA = SPIKES_ROOT / "spike_02_mcp_e2e" / "test_data"

# Spike-3 路径
SPIKE3_DATA = SPIKES_ROOT / "spike_03_collision" / "test_data"

# Spike-4 路径
SPIKE4_DATA = SPIKES_ROOT / "spike_04_des_sim" / "test_data"

# Spike-5 路径
SPIKE5_DATA = SPIKES_ROOT / "spike_05_llm_extract" / "test_data"

# Spike-9 路径
SPIKE9_DATA = SPIKES_ROOT / "spike_09_rag" / "test_data"

# Spike-10 路径
SPIKE10_DATA = SPIKES_ROOT / "spike_10_report" / "test_data"
SPIKE10_TEMPLATES = SPIKES_ROOT / "spike_10_report" / "templates"


# ──────────────────── 验收阈值常量 ────────────────────
class Thresholds:
    """来自 关键技术验证计划.md 的 Go/No-Go 阈值"""

    # Spike-1: DWG 解析
    S1_ENTITY_DIFF_PCT = 1          # 实体数量差异 ≤ 1%
    S1_LAYER_CLASSIFY_RATE = 0.85   # 图层识别率 ≥ 85%
    S1_COORD_ERROR_MM = 10          # 坐标对齐误差 ≤ 10mm
    S1_LARGE_FILE_MEMORY_MB = 2048  # 大文件内存 ≤ 2GB
    S1_LARGE_FILE_TIME_S = 30       # 大文件耗时 ≤ 30s
    S1_ERROR_CODE_CORRUPT = 5001    # 损坏文件错误码

    # Spike-2: MCP 通信
    S2_STDIO_SUCCESS_RATE = 1.0     # stdio 100次成功率 100%
    S2_SSE_SUCCESS_RATE = 0.99      # SSE 成功率 ≥ 99%
    S2_SSE_P99_LATENCY_MS = 500     # SSE P99 延迟 ≤ 500ms
    S2_TOOL_TIMEOUT_S = 10          # Tool 超时阈值

    # Spike-3: 碰撞检测
    S3_GLOBAL_50_MS = 50            # 50 Assets ≤ 50ms
    S3_GLOBAL_100_MS = 100          # 100 Assets ≤ 100ms
    S3_GLOBAL_200_MS = 200          # 200 Assets ≤ 200ms
    S3_INCREMENTAL_MS = 20          # 增量检测 ≤ 20ms
    S3_HEAL_MS = 100                # 自愈算法 ≤ 100ms
    S3_EXCLUSION_MS = 50            # 禁区检测 ≤ 50ms
    S3_WS_E2E_MS = 500              # 全链路 ≤ 500ms

    # Spike-4: DES 仿真
    S4_DETERMINISTIC_ERROR_PCT = 1   # 确定性 JPH 误差 ≤ 1%
    S4_STOCHASTIC_ERROR_PCT = 5      # 随机故障 JPH 误差 ≤ 5% (10次均值)
    S4_10STATION_TIME_S = 30         # 10工站 ≤ 30s
    S4_20STATION_TIME_S = 60         # 20工站 ≤ 60s
    S4_50STATION_TIME_S = 180        # 50工站 ≤ 180s

    # Spike-5: LLM 提取
    S5_PRECISION = 0.80              # Precision ≥ 0.80
    S5_RECALL = 0.70                 # Recall ≥ 0.70
    S5_SOURCE_REF_ACCURACY = 0.90    # 回溯准确率 ≥ 90%
    S5_HALLUCINATION_RATE = 0.10     # 幻觉率 ≤ 10%

    # Spike-6: Temporal
    S6_RETRY_MAX_ATTEMPTS = 3        # 重试3次内成功

    # Spike-7: 3D 渲染
    S7_FPS_200_ASSETS = 30           # 200 Assets FPS ≥ 30
    S7_FIRST_PAINT_S = 3             # 首屏 ≤ 3s

    # Spike-8: PINN
    S8_INFERENCE_ERROR_PCT = 10      # 推理误差 ≤ 10% MAE
    S8_INFERENCE_LATENCY_MS = 100    # 推理延迟 ≤ 100ms
    S8_OOD_ERROR_PCT = 20            # 分布外误差 ≤ 20%

    # Spike-9: RAG
    S9_RECALL_AT_5 = 0.80            # Recall@5 ≥ 0.80
    S9_LATENCY_MS = 500              # 检索延迟 ≤ 500ms

    # Spike-10: 报告
    S10_LARGE_REPORT_TIME_S = 30     # 50页报告 ≤ 30s


# ──────────────────── 性能基准工具 ────────────────────

def benchmark_median(fn, warmup=1, iterations=5):
    """运行 fn() 多次, 返回 (中位数耗时ms, 最后一次返回值)。
    排除 warmup 次预热, 取 iterations 次中位数。
    """
    for _ in range(warmup):
        fn()
    times = []
    result = None
    for _ in range(iterations):
        start = time.perf_counter()
        result = fn()
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times), result


# ──────────────────── Pytest Fixtures ────────────────────

@pytest.fixture(scope="session")
def thresholds():
    return Thresholds


# Spike-1 Fixtures
@pytest.fixture(scope="session")
def tier1_dxf_path():
    return SPIKE1_DATA / "tier1_wing_leading_edge_workshop.dxf"

@pytest.fixture(scope="session")
def tier2_dxf_path():
    return SPIKE1_DATA / "tier2_fuselage_join_facility.dxf"

@pytest.fixture(scope="session")
def tier3_dxf_path():
    return SPIKE1_DATA / "tier3_pulse_line_fal.dxf"

@pytest.fixture(scope="session")
def corrupted_dxf_path():
    return SPIKE1_DATA / "corrupted_file.dxf"

@pytest.fixture(scope="session")
def reference_points_dxf_path():
    return SPIKE1_DATA / "reference_points_offset.dxf"

@pytest.fixture(scope="session")
def reference_points_mapping():
    path = SPIKE1_DATA / "reference_points_mapping.json"
    return json.loads(path.read_text(encoding="utf-8"))

@pytest.fixture(scope="session")
def real_dwg_paths():
    dwg_dir = SPIKE1_REAL / "libredwg"
    if not dwg_dir.exists():
        pytest.skip("Real DWG files not downloaded")
    return sorted(dwg_dir.glob("*.dwg"))

@pytest.fixture(scope="session")
def real_dxf_paths():
    dxf_dir = SPIKE1_REAL / "ezdxf"
    if not dxf_dir.exists():
        pytest.skip("Real DXF files not downloaded")
    return sorted(dxf_dir.glob("*.dxf"))


# Spike-2 Fixtures
@pytest.fixture(scope="session")
def mock_agent_tools():
    path = SPIKE2_DATA / "mock_agent_tools.json"
    return json.loads(path.read_text(encoding="utf-8"))


# Spike-3 Fixtures
@pytest.fixture(scope="session")
def collision_test_data():
    path = SPIKE3_DATA / "tier2_layout_assets.json"
    return json.loads(path.read_text(encoding="utf-8"))


# Spike-4 Fixtures
@pytest.fixture(scope="session")
def simulation_scenarios():
    path = SPIKE4_DATA / "simulation_scenarios.json"
    return json.loads(path.read_text(encoding="utf-8"))


# Spike-5 Fixtures
@pytest.fixture(scope="session")
def sop_a_text():
    path = SPIKE5_DATA / "SOP_A_wing_skin_milling.md"
    return path.read_text(encoding="utf-8")

@pytest.fixture(scope="session")
def sop_b_text():
    path = SPIKE5_DATA / "SOP_B_fuselage_panel_riveting.md"
    return path.read_text(encoding="utf-8")

@pytest.fixture(scope="session")
def sop_c_text():
    path = SPIKE5_DATA / "SOP_C_wing_body_join.md"
    return path.read_text(encoding="utf-8")


# Spike-5 Gold Standard （从 SOP 文件头部的标注中提取）
@pytest.fixture(scope="session")
def gold_standard_a():
    """SOP_A: 12 Gold Standard Constraints (WLE-C01~C12)"""
    return {
        "doc_id": "SOP_A",
        "constraint_count": 12,
        "constraint_ids": [f"WLE-C{i:02d}" for i in range(1, 13)],
        "contradiction_count": 0,
    }

@pytest.fixture(scope="session")
def gold_standard_b():
    """SOP_B: 18 Gold Standard Constraints (FSP-C01~C18), 2 contradiction traps"""
    return {
        "doc_id": "SOP_B",
        "constraint_count": 18,
        "constraint_ids": [f"FSP-C{i:02d}" for i in range(1, 19)],
        "contradiction_count": 2,
    }

@pytest.fixture(scope="session")
def gold_standard_c():
    """SOP_C: 25 Gold Standard Constraints (WBJ-C01~C25), 3 contradiction pairs"""
    return {
        "doc_id": "SOP_C",
        "constraint_count": 25,
        "constraint_ids": [f"WBJ-C{i:02d}" for i in range(1, 26)],
        "contradiction_count": 3,
    }


# Spike-9 Fixtures
@pytest.fixture(scope="session")
def rag_documents():
    if not SPIKE9_DATA.exists():
        pytest.skip("RAG test data not found")
    return sorted(SPIKE9_DATA.glob("*.md"))


# Spike-10 Fixtures
@pytest.fixture(scope="session")
def report_template():
    path = SPIKE10_TEMPLATES / "layout_review_report.md"
    return path.read_text(encoding="utf-8")

@pytest.fixture(scope="session")
def sample_report_data():
    path = SPIKE10_DATA / "sample_report_data.json"
    return json.loads(path.read_text(encoding="utf-8"))
