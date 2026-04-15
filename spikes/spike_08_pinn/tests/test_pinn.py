"""
Spike-8 测试用例：PINN 代理模型加速可行性
==========================================
Test Case IDs: S8-TC01 ~ S8-TC05 (关键技术验证计划 §9.3)

优先级: P2 (V1.0阶段, PoC不阻塞)

期望标准:
  - 推理误差 ≤ 10% MAE (分布内)
  - 推理延迟 ≤ 100ms
  - 训练数据量 ≤ 500次 SimPy 运行
"""
import time
import pytest
import numpy as np
from conftest import Thresholds

# ════════════════════════════════════════════════════════════════
# 待实现模块导入 — TDD RED phase
# ════════════════════════════════════════════════════════════════
from spike_08_pinn.src.data_generator import SimDataGenerator
from spike_08_pinn.src.pinn_model import PINNSurrogateModel
from spike_08_pinn.src.trainer import PINNTrainer


@pytest.mark.p2
@pytest.mark.spike8
class TestTrainingDataGeneration:
    """S8-TC01: 训练数据生成"""

    @pytest.mark.parametrize("n_samples", [100, 500])
    def test_tc01_generate_dataset(self, n_samples):
        """SimPy 运行 N 次, 记录 (input, output) 对"""
        generator = SimDataGenerator(
            station_count=5,
            cycle_time_range=(20, 40),
        )
        dataset = generator.generate(n_samples=n_samples, seed=42)

        assert len(dataset) == n_samples
        assert dataset.input_dim > 0
        assert dataset.output_dim > 0
        # 每条数据应包含输入参数和 JPH/利用率等输出
        sample = dataset[0]
        assert "inputs" in sample
        assert "outputs" in sample


@pytest.mark.p2
@pytest.mark.spike8
@pytest.mark.gpu
@pytest.mark.slow
class TestPINNTraining:
    """S8-TC02: PINN 模型训练"""

    def test_tc02_training_converges(self):
        """PyTorch 训练 5 工站模型, 应收敛"""
        generator = SimDataGenerator(station_count=5, cycle_time_range=(20, 40))
        dataset = generator.generate(n_samples=500, seed=42)

        model = PINNSurrogateModel(input_dim=dataset.input_dim, output_dim=dataset.output_dim)
        trainer = PINNTrainer(model, learning_rate=1e-3, epochs=100)
        history = trainer.train(dataset)

        # 训练损失应下降
        assert history.final_loss < history.initial_loss
        assert history.final_loss < 0.1  # 应收敛到合理值


@pytest.mark.p2
@pytest.mark.spike8
class TestPINNInference:
    """S8-TC03: PINN 推理精度 — 误差 ≤ 10% MAE"""

    def test_tc03_inference_accuracy(self):
        """PINN 预测 vs SimPy 真值, MAE ≤ 10%"""
        generator = SimDataGenerator(station_count=5, cycle_time_range=(20, 40))
        train_set = generator.generate(n_samples=500, seed=42)
        test_set = generator.generate(n_samples=50, seed=99)

        model = PINNSurrogateModel(input_dim=train_set.input_dim, output_dim=train_set.output_dim)
        trainer = PINNTrainer(model, learning_rate=1e-3, epochs=100)
        trainer.train(train_set)

        predictions = model.predict_batch(test_set.inputs)
        actuals = test_set.outputs

        mae_pct = np.mean(np.abs(predictions - actuals) / np.abs(actuals)) * 100
        assert mae_pct <= Thresholds.S8_INFERENCE_ERROR_PCT, (
            f"PINN MAE {mae_pct:.1f}% > {Thresholds.S8_INFERENCE_ERROR_PCT}%"
        )


@pytest.mark.p2
@pytest.mark.spike8
class TestPINNInferenceSpeed:
    """S8-TC04: 单次 PINN 推理 ≤ 100ms"""

    def test_tc04_inference_latency(self):
        model = PINNSurrogateModel(input_dim=10, output_dim=3)
        # 假设已训练（测试关注速度,不关注精度）
        sample_input = np.random.randn(1, 10).astype(np.float32)

        start = time.perf_counter()
        _ = model.predict(sample_input)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms <= Thresholds.S8_INFERENCE_LATENCY_MS, (
            f"推理延迟 {elapsed_ms:.1f}ms > {Thresholds.S8_INFERENCE_LATENCY_MS}ms"
        )


@pytest.mark.p2
@pytest.mark.spike8
class TestOODGeneralization:
    """S8-TC05: 分布外泛化 — 偏离训练分布 20%"""

    def test_tc05_ood_error(self):
        """输入偏离训练分布 20%, 误差 ≤ 20%"""
        generator = SimDataGenerator(station_count=5, cycle_time_range=(20, 40))
        train_set = generator.generate(n_samples=500, seed=42)

        # 生成 OOD 数据: cycle_time 扩大到 16~48 (±20%)
        ood_generator = SimDataGenerator(station_count=5, cycle_time_range=(16, 48))
        ood_set = ood_generator.generate(n_samples=50, seed=123)

        model = PINNSurrogateModel(input_dim=train_set.input_dim, output_dim=train_set.output_dim)
        trainer = PINNTrainer(model, learning_rate=1e-3, epochs=100)
        trainer.train(train_set)

        predictions = model.predict_batch(ood_set.inputs)
        actuals = ood_set.outputs

        mae_pct = np.mean(np.abs(predictions - actuals) / np.abs(actuals)) * 100
        assert mae_pct <= Thresholds.S8_OOD_ERROR_PCT, (
            f"OOD MAE {mae_pct:.1f}% > {Thresholds.S8_OOD_ERROR_PCT}%"
        )


# ════════════════════════════════════════════════════════════════
# L4: 黄金基准 — 已知解析解验证
# ════════════════════════════════════════════════════════════════

@pytest.mark.p2
@pytest.mark.spike8
class TestAnalyticalSolution:
    """L4: 已知线性函数精确拟合 (排除 NN 近似误差干扰)"""

    def test_linear_function_exact_fit(self):
        """y = 2*x1 + 3*x2 + 1 的精确数据 → PINN 应完美拟合

        训练 200 样本, 测试 3 个精确点:
        (1,1)→6, (0,0)→1, (-1,2)→6
        """
        from spike_08_pinn.src.data_generator import SimDataset

        np.random.seed(42)
        n = 200
        x = np.random.randn(n, 2).astype(np.float32)
        y = (2 * x[:, 0:1] + 3 * x[:, 1:2] + 1).astype(np.float32)
        dataset = SimDataset(input_dim=2, output_dim=1, inputs=x, outputs=y)

        model = PINNSurrogateModel(input_dim=2, output_dim=1)
        trainer = PINNTrainer(model, learning_rate=1e-3, epochs=200)
        trainer.train(dataset)

        x_test = np.array([[1.0, 1.0], [0.0, 0.0], [-1.0, 2.0]], dtype=np.float32)
        y_expected = np.array([[6.0], [1.0], [6.0]], dtype=np.float32)

        y_pred = model.predict_batch(x_test)
        mae = float(np.mean(np.abs(y_pred - y_expected)))

        assert mae < 0.5, f"线性函数拟合 MAE={mae:.3f}, 应 < 0.5"

    def test_constant_function(self):
        """y = 42 (常数) → 预测应精确等于 42"""
        from spike_08_pinn.src.data_generator import SimDataset

        np.random.seed(42)
        n = 100
        x = np.random.randn(n, 3).astype(np.float32)
        y = np.full((n, 1), 42.0, dtype=np.float32)
        dataset = SimDataset(input_dim=3, output_dim=1, inputs=x, outputs=y)

        model = PINNSurrogateModel(input_dim=3, output_dim=1)
        trainer = PINNTrainer(model, learning_rate=1e-3, epochs=200)
        trainer.train(dataset)

        x_test = np.random.randn(5, 3).astype(np.float32)
        y_pred = model.predict_batch(x_test)
        mae = float(np.mean(np.abs(y_pred - 42.0)))

        assert mae < 1.0, f"常数函数 MAE={mae:.3f}, 应 < 1.0"
