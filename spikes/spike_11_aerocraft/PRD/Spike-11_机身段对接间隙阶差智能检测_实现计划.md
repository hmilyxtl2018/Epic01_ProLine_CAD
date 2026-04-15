# Plan: Spike-11 机身段对接间隙/阶差智能检测

## TL;DR

新建 spike_11_fuselage_gap，验证"点云-模型配准 → 间隙阶差检测 → 垫片方案优化"三步闭环。
核心挑战：真实航空点云数据不存在公开数据集，采用 CPACS+TiGL 生成参数化机身段 STEP 模型 + Open3D 合成带偏差点云的方式构建 Ground Truth 测试数据。

---

## Phase 0: 测试数据获取与生成

### 0.1 STEP 设计模型获取 (真实数据)

**来源 A — DLR CPACS + TiGL（推荐，首选）**
- CPACS: `github.com/DLR-SL/CPACS` (Apache-2.0) — XML 格式参数化飞机定义
  - `examples/` 目录有完整飞机 CPACS 文件
- TiGL: `github.com/DLR-SC/tigl` (Apache-2.0) — 从 CPACS 生成 NURBS 几何
  - `conda install -c dlr-sc tigl3` 即可安装
  - API: `tigl3.import_cpacs(filename)` → `fuselage.get_section()` → `export_step()`
  - 可精确导出机身段 barrel section 的 STEP AP214 文件
- 脚本方案: 编写 `acquire_fuselage_step.py`
  1. 从 CPACS examples 下载 D150 (类 A320) CPACS 数据
  2. 用 TiGL Python API 提取 fuselage section 13~18 (mid-barrel)
  3. 导出为 STEP AP214 文件 → `test_data/design_model/fuselage_barrel_section.stp`

**来源 B — OpenVSP（备选）**
- `github.com/OpenVSP/OpenVSP` (NOSA-1.3) — NASA 参数化飞机设计
- 可导出 STEP (依赖 STEPcode)，但精度不如 TiGL (非 NURBS 原生表达)
- 作为 fallback：下载预编译包，脚本化生成 B737-like fuselage → STEP

**来源 C — NIST PMI Test Models（补充验证）**
- `nist.gov/...mbe-pmi-0` — 免费 STEP 文件含 PMI/GD&T 标注
- 非飞机模型，但可用于验证 STEP 解析管线 + AP242 PMI 读取能力

**来源 D — GrabCAD 社区模型（仅参考）**
- 搜索 "fuselage section" / "aircraft barrel" — 有 SOLIDWORKS/STEP 可下载
- 许可证不稳定，不作为主数据源，仅做视觉参考

### 0.2 点云数据生成 (合成 + 已知 Ground Truth)

**现实：公开航空机身段 3D 扫描点云数据集不存在。**
工业级激光扫描数据属于 OEM 机密 (Boeing/Airbus/COMAC)，学术数据集 (ModelNet/ShapeNet) 分辨率太低且无航空件。

**策略：从 STEP 模型合成带偏差的点云，已知 Ground Truth → 精确验证检测算法**

脚本 `generate_synthetic_pointcloud.py`:
1. **基础点云生成**
   - 用 Open3D / PythonOCC 从 STEP 提取 mesh → 均匀采样 50,000~200,000 点
   - 添加高斯噪声 σ=0.05mm (模拟激光扫描仪精度)
   - 输出: `test_data/scan_data/barrel_scan_nominal.ply`

2. **对接偏差注入** (关键 — 模拟真实装配偏差)
   - **间隙 (Gap)**: Section A 前端面向 Z+ 偏移 0.3mm~2.0mm → 对接面出现间隙
   - **阶差 (Step/Flush)**: Section B 径向偏移 0.1mm~1.5mm → 对接面蒙皮不齐平
   - **扭转 (Twist)**: Section A 绕轴线旋转 0.05°~0.3° → 局部间隙不均匀
   - 每种偏差生成 3 档 (小/中/大)，共 9 个偏差点云文件
   - 偏差 Ground Truth 记录在 JSON: `test_data/scan_data/deviation_ground_truth.json`

3. **多格式输出**
   - PLY (Open3D 原生, 含法线)
   - PCD (PCL 标准格式)
   - LAS (工业点云通用格式, 可选)

### 0.3 数据获取脚本汇总

| 脚本 | 功能 | 依赖 | 输出 |
|------|------|------|------|
| `acquire_fuselage_step.py` | 从 CPACS+TiGL 生成 STEP 模型 | tigl3, lxml | `test_data/design_model/*.stp` |
| `generate_synthetic_pointcloud.py` | 从 STEP 合成点云 + 注入偏差 | open3d, pythonocc-core | `test_data/scan_data/*.ply` |
| `preview_test_data.py` | 可视化 STEP + 点云 + 偏差热力图 | open3d, matplotlib | `test_data/previews/*.png` |

---

## Phase 1: Spike 基础结构搭建

### 1.1 目录结构

```
spikes/spike_11_fuselage_gap/
├── __init__.py
├── src/
│   ├── __init__.py
│   ├── point_cloud_registrar.py    # ICP 点云-模型配准
│   ├── gap_step_detector.py        # 间隙/阶差检测
│   └── shim_optimizer.py           # 垫片/修配方案优化
├── tests/
│   ├── __init__.py
│   └── test_fuselage_gap.py
├── test_data/
│   ├── design_model/               # STEP 文件
│   ├── scan_data/                   # 点云文件 + deviation GT JSON
│   └── previews/
├── scripts/
│   ├── acquire_fuselage_step.py
│   ├── generate_synthetic_pointcloud.py
│   └── preview_test_data.py
└── README.md
```

### 1.2 conftest.py Thresholds 新增

```python
# Spike-11: 机身段间隙/阶差检测
S11_ICP_REGISTRATION_ERROR_MM = 0.1     # ICP 配准 RMS ≤ 0.1mm
S11_GAP_DETECTION_ERROR_MM = 0.05       # 间隙测量误差 ≤ 0.05mm
S11_STEP_DETECTION_ERROR_MM = 0.05      # 阶差测量误差 ≤ 0.05mm
S11_FALSE_POSITIVE_RATE = 0.02          # 误报率 ≤ 2%
S11_DETECTION_RECALL = 0.95             # 检出率 ≥ 95%
S11_SHIM_COVERAGE_RATE = 0.90           # 垫片方案覆盖率 ≥ 90%
S11_PROCESS_TIME_S = 30                 # 单段检测 ≤ 30s (50K 点)
```

### 1.3 pytest.ini 新增 marker

- 添加 `spike11` marker

---

## Phase 2: Source Stubs (TDD RED)

### 2.1 point_cloud_registrar.py

```python
@dataclass
class RegistrationResult:
    """点云-模型配准结果"""
    transform_matrix: np.ndarray     # 4×4 变换矩阵
    rms_error_mm: float              # RMS 配准误差
    inlier_ratio: float              # 内点比例
    iterations: int                  # 迭代次数

class PointCloudRegistrar:
    """ICP 点云到 STEP 模型配准 (§对接面配准)"""
    def register(self, scan_cloud, design_mesh) -> RegistrationResult:
        raise NotImplementedError
```

### 2.2 gap_step_detector.py

```python
@dataclass
class DeviationPoint:
    """单个检测点的偏差"""
    position: tuple                  # (x, y, z) 检测位置
    gap_mm: float                    # 间隙值 (法向距离)
    step_mm: float                   # 阶差值 (切向偏移)
    normal: tuple                    # 对接面法线方向
    severity: str                    # "OK" / "WARNING" / "CRITICAL"

@dataclass
class DetectionResult:
    """间隙/阶差检测结果"""
    deviation_points: list           # List[DeviationPoint]
    max_gap_mm: float
    max_step_mm: float
    mean_gap_mm: float
    mean_step_mm: float
    critical_count: int
    inspection_point_count: int

class GapStepDetector:
    """间隙/阶差检测器 (HB 5800 系列标准)"""
    def detect(self, registered_cloud, design_model, joint_zone) -> DetectionResult:
        raise NotImplementedError
```

### 2.3 shim_optimizer.py

```python
@dataclass
class ShimPlan:
    """垫片方案"""
    shim_count: int                  # 垫片数量
    shim_specs: list                 # List[{position, thickness_mm, material}]
    residual_gap_mm: float           # 垫片后残余间隙
    total_cost_factor: float         # 成本因子 (1.0=标准)
    
class ShimOptimizer:
    """垫片/修配方案优化器"""
    def optimize(self, detection_result, tolerance_spec) -> ShimPlan:
        raise NotImplementedError
```

---

## Phase 3: Tests (TDD RED)

### 测试用例设计

| Test ID | 描述 | 断言 |
|---------|------|------|
| S11-TC01 | ICP 配准 — 无偏差点云 → 设计模型 | rms_error ≤ 0.1mm |
| S11-TC02 | ICP 配准 — 带噪声点云 (σ=0.05mm) | rms_error ≤ 0.1mm |
| S11-TC03 | 间隙检测 — 0.5mm 已知间隙 | |gap_detected - 0.5| ≤ 0.05mm |
| S11-TC04 | 间隙检测 — 2.0mm 大间隙 | |gap_detected - 2.0| ≤ 0.05mm |
| S11-TC05 | 阶差检测 — 0.3mm 径向偏移 | |step_detected - 0.3| ≤ 0.05mm |
| S11-TC06 | 阶差检测 — 扭转 0.1° 不均匀变化 | recall ≥ 0.95 |
| S11-TC07 | 无偏差时 false positive ≤ 2% | false_positive_rate ≤ 0.02 |
| S11-TC08 | 垫片方案覆盖率 | coverage ≥ 0.90 |
| S11-TC09 | 50K 点处理时间 ≤ 30s | process_time ≤ 30s |
| S11-TC10 | 垫片方案后残余间隙 ≤ tolerance | residual ≤ spec |

---

## Phase 4: 依赖与环境

### Python 依赖

| 包 | 用途 | 安装 |
|----|------|------|
| `open3d` | 点云处理/ICP/可视化 | `pip install open3d` |
| `pythonocc-core` | STEP 读写/BREP 运算 | `conda install -c conda-forge pythonocc-core` |
| `tigl3` | CPACS→STEP 生成 | `conda install -c dlr-sc tigl3` |
| `numpy` | 数值计算 | 已有 |
| `scipy` | 优化/空间索引 | `pip install scipy` |

### 备选方案 (pythonocc 安装困难时)
- 用 `trimesh` + `stl` 替代 pythonocc 做 STEP→mesh 转换
- 用 FreeCAD Python API (import Part) 读 STEP

---

## Phase 5: 数据获取执行步骤

### Step 5.1: 安装依赖
```bash
conda install -c dlr-sc tigl3
pip install open3d trimesh
```

### Step 5.2: 获取 CPACS 示例文件
```bash
# 从 DLR CPACS repo 下载 D150 示例 (A320-like)
wget https://raw.githubusercontent.com/DLR-SL/CPACS/develop/examples/D150_v4.0.xml
# 或 TiGL test data
wget https://raw.githubusercontent.com/DLR-SC/tigl/main/tests/unittests/TestData/simpletest.cpacs.xml
```

### Step 5.3: 生成 STEP 模型
运行 `acquire_fuselage_step.py`:
1. 加载 CPACS XML
2. TiGL 提取 fuselage segment geometry
3. 导出 barrel section → STEP AP214
4. 验证: 文件 > 10KB, 可被 PythonOCC 读取

### Step 5.4: 生成合成点云
运行 `generate_synthetic_pointcloud.py`:
1. 读取 STEP → mesh → 均匀采样点云
2. 注入 9 种偏差组合 (3 gap × 3 step)
3. 导出 PLY + Ground Truth JSON
4. 验证: 文件可被 Open3D 加载, deviation 与注入值一致

---

## Relevant Files

- `spikes/conftest.py` — 添加 S11_* Thresholds
- `spikes/pytest.ini` — 添加 `spike11` marker
- `spikes/spike_11_fuselage_gap/` — 新建整个 spike 目录 (结构同上)
- `PRD/关键技术验证计划.md` — 可追加 Spike-11 验证条目

---

## Verification

1. `python scripts/acquire_fuselage_step.py` → 成功生成 `fuselage_barrel_section.stp`，文件 > 10KB
2. `python scripts/generate_synthetic_pointcloud.py` → 生成 9+ PLY 文件 + GT JSON，Open3D 可加载
3. `python scripts/preview_test_data.py` → 输出可视化预览图，偏差热力图清晰
4. `cd spikes && python -m pytest spike_11_fuselage_gap/tests/ -m p0` → 所有测试 RED (NotImplementedError)
5. `cd spikes && python -m pytest -m spike11` → marker 生效，仅运行 spike11 测试

---

## Decisions & Assumptions

- **不用真实工业扫描数据**: 公开航空点云数据集不存在 → 合成数据 + Ground Truth 是 Spike 阶段唯一可行路径
- **CPACS+TiGL 作为 STEP 来源**: 这是唯一完全开源、可脚本化、可重现的航空 STEP 生成方案
- **pythonocc 优先，trimesh 兜底**: pythonocc 功能最完整但安装复杂，trimesh 作为轻量 fallback
- **HB 5800 系列标准**: 间隙/阶差容差引用航空行标，具体数值硬编码在 Thresholds 中
- **Spike 范围**: 仅验证"配准→检测→方案"管线可行性，不涉及实时性、大规模并行、或适航认证

## Further Considerations

1. **conda vs pip 环境冲突**: tigl3 和 pythonocc 都需要 conda，当前项目用 pip venv — 可能需要单独 conda env 或用 Docker。建议先尝试 pip 安装 open3d + trimesh，tigl 仅在数据生成脚本中使用（可在独立环境运行后将 STEP 文件 commit 到 test_data）
2. **点云规模**: 50K 点是 PoC 级别，真实扫描 > 5M 点 — Spike 验证算法正确性后，后续可在性能测试中扩展
3. **偏差类型扩展**: 当前仅覆盖 gap/step/twist，实际装配还有弯曲、翘曲、温度变形等 — 按需在 Phase 后续迭代中追加
