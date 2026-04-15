"""
Spike-5 测试用例：LLM 工艺约束提取准确性
==========================================
Test Case IDs: S5-TC01 ~ S5-TC07 (关键技术验证计划 §6.4)

Go/No-Go 必须标准:
  - Precision ≥ 0.80  (3份文档平均)
  - Recall ≥ 0.70
  - JSON 输出可解析率 = 100%
  - source_ref 回溯准确率 ≥ 90%
  - 幻觉率 ≤ 10%
"""
import json
import pytest
from conftest import SPIKE5_DATA, Thresholds

# ════════════════════════════════════════════════════════════════
# 待实现模块导入 — TDD RED phase
# ════════════════════════════════════════════════════════════════
from spike_05_llm_extract.src.constraint_extractor import ConstraintExtractor
from spike_05_llm_extract.src.evaluator import ExtractionEvaluator
from spike_05_llm_extract.src.contradiction_detector import ContradictionDetector


@pytest.mark.p1
@pytest.mark.spike5
class TestConstraintExtractionSOP_A:
    """S5-TC01: SOP-A 机翼蒙皮铣削 — 12条约束"""

    def test_tc01_precision(self, sop_a_text, gold_standard_a):
        """Precision ≥ 0.80"""
        extractor = ConstraintExtractor(strategy="few_shot")
        result = extractor.extract(sop_a_text)
        evaluator = ExtractionEvaluator()

        metrics = evaluator.evaluate(result.constraints, gold_standard_a)
        assert metrics.precision >= Thresholds.S5_PRECISION, (
            f"SOP-A Precision {metrics.precision:.2f} < {Thresholds.S5_PRECISION}"
        )

    def test_tc01_recall(self, sop_a_text, gold_standard_a):
        """Recall ≥ 0.70"""
        extractor = ConstraintExtractor(strategy="few_shot")
        result = extractor.extract(sop_a_text)
        evaluator = ExtractionEvaluator()

        metrics = evaluator.evaluate(result.constraints, gold_standard_a)
        assert metrics.recall >= Thresholds.S5_RECALL, (
            f"SOP-A Recall {metrics.recall:.2f} < {Thresholds.S5_RECALL}"
        )

    def test_tc01_constraint_structure(self, sop_a_text):
        """每条约束应包含 id, type, rule, source_ref"""
        extractor = ConstraintExtractor(strategy="few_shot")
        result = extractor.extract(sop_a_text)

        for constraint in result.constraints:
            assert constraint.id is not None
            assert constraint.type in ("hard", "soft")
            assert len(constraint.rule) > 0
            assert constraint.source_ref is not None


@pytest.mark.p1
@pytest.mark.spike5
class TestConstraintExtractionSOP_B:
    """S5-TC02: SOP-B 机身壁板钻铆 — 18条约束 + 2对矛盾"""

    def test_tc02_precision(self, sop_b_text, gold_standard_b):
        extractor = ConstraintExtractor(strategy="few_shot")
        result = extractor.extract(sop_b_text)
        evaluator = ExtractionEvaluator()

        metrics = evaluator.evaluate(result.constraints, gold_standard_b)
        assert metrics.precision >= Thresholds.S5_PRECISION

    def test_tc02_recall(self, sop_b_text, gold_standard_b):
        extractor = ConstraintExtractor(strategy="few_shot")
        result = extractor.extract(sop_b_text)
        evaluator = ExtractionEvaluator()

        metrics = evaluator.evaluate(result.constraints, gold_standard_b)
        assert metrics.recall >= Thresholds.S5_RECALL


@pytest.mark.p1
@pytest.mark.spike5
class TestConstraintExtractionSOP_C:
    """S5-TC03: SOP-C 总装翼身对接 — 25条约束 + 3对矛盾 + 矛盾检出"""

    def test_tc03_precision(self, sop_c_text, gold_standard_c):
        extractor = ConstraintExtractor(strategy="few_shot")
        result = extractor.extract(sop_c_text)
        evaluator = ExtractionEvaluator()

        metrics = evaluator.evaluate(result.constraints, gold_standard_c)
        assert metrics.precision >= Thresholds.S5_PRECISION

    def test_tc03_recall(self, sop_c_text, gold_standard_c):
        extractor = ConstraintExtractor(strategy="few_shot")
        result = extractor.extract(sop_c_text)
        evaluator = ExtractionEvaluator()

        metrics = evaluator.evaluate(result.constraints, gold_standard_c)
        assert metrics.recall >= Thresholds.S5_RECALL

    def test_tc03_contradiction_detected(self, sop_c_text, gold_standard_c):
        """SOP-C 含 3 对矛盾, 至少检出 1 对"""
        extractor = ConstraintExtractor(strategy="chain_of_thought")
        result = extractor.extract(sop_c_text)

        detector = ContradictionDetector()
        contradictions = detector.detect(result.constraints)

        assert len(contradictions) >= 1, (
            f"SOP-C 有 {gold_standard_c['contradiction_count']} 对矛盾, "
            f"仅检出 {len(contradictions)} 对"
        )


@pytest.mark.p1
@pytest.mark.spike5
class TestSourceRefTraceability:
    """S5-TC04: source_ref 回溯准确率 ≥ 90%"""

    @pytest.mark.parametrize("sop_fixture", ["sop_a_text", "sop_b_text", "sop_c_text"])
    def test_tc04_source_ref_accuracy(self, sop_fixture, request):
        """每条约束的 source_ref 应能在原文中定位"""
        sop_text = request.getfixturevalue(sop_fixture)
        extractor = ConstraintExtractor(strategy="few_shot")
        result = extractor.extract(sop_text)
        evaluator = ExtractionEvaluator()

        ref_accuracy = evaluator.check_source_refs(result.constraints, sop_text)
        assert ref_accuracy >= Thresholds.S5_SOURCE_REF_ACCURACY, (
            f"source_ref 回溯准确率 {ref_accuracy:.2%} < {Thresholds.S5_SOURCE_REF_ACCURACY:.0%}"
        )


@pytest.mark.p1
@pytest.mark.spike5
class TestPromptStrategies:
    """S5-TC05: 3 种 Prompt 策略效果对比"""

    @pytest.mark.parametrize("strategy", ["zero_shot", "few_shot", "chain_of_thought"])
    def test_tc05_strategy_produces_results(self, sop_a_text, strategy):
        """每种策略都应能产出约束（不为空）"""
        extractor = ConstraintExtractor(strategy=strategy)
        result = extractor.extract(sop_a_text)

        assert len(result.constraints) > 0, (
            f"策略 '{strategy}' 未提取到任何约束"
        )

    def test_tc05_best_strategy(self, sop_a_text, gold_standard_a):
        """至少一种策略满足 Precision ≥ 0.80 & Recall ≥ 0.70"""
        evaluator = ExtractionEvaluator()
        best_f1 = 0
        best_strategy = None

        for strategy in ["zero_shot", "few_shot", "chain_of_thought"]:
            extractor = ConstraintExtractor(strategy=strategy)
            result = extractor.extract(sop_a_text)
            metrics = evaluator.evaluate(result.constraints, gold_standard_a)
            if metrics.f1 > best_f1:
                best_f1 = metrics.f1
                best_strategy = strategy

        assert best_strategy is not None
        # 最优策略应满足门槛
        extractor = ConstraintExtractor(strategy=best_strategy)
        result = extractor.extract(sop_a_text)
        metrics = evaluator.evaluate(result.constraints, gold_standard_a)
        assert metrics.precision >= Thresholds.S5_PRECISION
        assert metrics.recall >= Thresholds.S5_RECALL


@pytest.mark.p1
@pytest.mark.spike5
class TestHallucinationDetection:
    """S5-TC06: 幻觉检测 — 幻觉率 ≤ 10%"""

    def test_tc06_hallucination_rate(self, sop_a_text, gold_standard_a):
        """LLM 输出中非文档内容占比 ≤ 10%"""
        extractor = ConstraintExtractor(strategy="few_shot")
        result = extractor.extract(sop_a_text)
        evaluator = ExtractionEvaluator()

        metrics = evaluator.evaluate(result.constraints, gold_standard_a)
        assert metrics.hallucination_rate <= Thresholds.S5_HALLUCINATION_RATE, (
            f"幻觉率 {metrics.hallucination_rate:.2%} > {Thresholds.S5_HALLUCINATION_RATE:.0%}"
        )


@pytest.mark.p1
@pytest.mark.spike5
class TestJSONOutput:
    """S5-TC07: JSON 结构化输出 — 100% 可解析"""

    @pytest.mark.parametrize("sop_fixture", ["sop_a_text", "sop_b_text", "sop_c_text"])
    def test_tc07_json_parseable(self, sop_fixture, request):
        """LLM 输出应为合法的 JSON ConstraintSet"""
        sop_text = request.getfixturevalue(sop_fixture)
        extractor = ConstraintExtractor(strategy="few_shot")
        result = extractor.extract(sop_text)

        # 应能序列化为 JSON
        json_str = result.to_json()
        parsed = json.loads(json_str)

        assert "constraints" in parsed
        assert isinstance(parsed["constraints"], list)
        assert len(parsed["constraints"]) > 0

    def test_tc07_constraint_schema(self, sop_a_text):
        """每条约束应符合 ConstraintRule schema"""
        extractor = ConstraintExtractor(strategy="few_shot")
        result = extractor.extract(sop_a_text)

        required_fields = {"id", "type", "rule", "source_ref"}
        for c in result.constraints:
            c_dict = c.to_dict()
            missing = required_fields - set(c_dict.keys())
            assert len(missing) == 0, f"约束缺少字段: {missing}"


# ════════════════════════════════════════════════════════════════
# L4: Mock LLM 确定性验证 (消除非确定性)
# ════════════════════════════════════════════════════════════════

@pytest.mark.p1
@pytest.mark.spike5
class TestMockDeterministicExtraction:
    """L4: Mock LLM 回复 → 精确约束 ID 比对"""

    MOCK_LLM_RESPONSE = {
        "constraints": [
            {"id": "WLE-C01", "type": "hard", "rule": "铣削深度公差±0.05mm", "source_ref": "§3.1"},
            {"id": "WLE-C02", "type": "hard", "rule": "蒙皮最小厚度1.2mm", "source_ref": "§3.2"},
            {"id": "WLE-C03", "type": "soft", "rule": "刀具更换间隔≤200件", "source_ref": "§4.1"},
        ]
    }

    def test_mock_extraction_exact_ids(self, sop_a_text):
        """Mock LLM → 提取的 constraint IDs 精确匹配"""
        mock_backend = lambda doc, strategy: self.MOCK_LLM_RESPONSE
        extractor = ConstraintExtractor(strategy="few_shot", llm_backend=mock_backend)
        result = extractor.extract(sop_a_text)

        ids = [c.id for c in result.constraints]
        assert ids == ["WLE-C01", "WLE-C02", "WLE-C03"]

    def test_mock_extraction_exact_types(self, sop_a_text):
        """Mock LLM → 约束类型精确匹配"""
        mock_backend = lambda doc, strategy: self.MOCK_LLM_RESPONSE
        extractor = ConstraintExtractor(strategy="few_shot", llm_backend=mock_backend)
        result = extractor.extract(sop_a_text)

        types = [c.type for c in result.constraints]
        assert types == ["hard", "hard", "soft"]

    def test_evaluator_known_precision_recall(self):
        """Evaluator 在已知数据上精确计算 Precision/Recall

        Gold: {C01, C02, C03, C04}
        Extracted: {C01, C02, C05}
        TP=2, FP=1(C05), FN=2(C03,C04)
        Precision=2/3, Recall=2/4
        """
        from spike_05_llm_extract.src.constraint_extractor import ConstraintRule

        gold = {"constraint_ids": ["C01", "C02", "C03", "C04"], "constraint_count": 4}
        extracted = [
            ConstraintRule(id="C01", type="hard", rule="r1"),
            ConstraintRule(id="C02", type="hard", rule="r2"),
            ConstraintRule(id="C05", type="soft", rule="r5"),  # 幻觉
        ]

        evaluator = ExtractionEvaluator()
        metrics = evaluator.evaluate(extracted, gold)

        assert abs(metrics.precision - 2 / 3) < 0.01, f"Precision={metrics.precision}"
        assert abs(metrics.recall - 2 / 4) < 0.01, f"Recall={metrics.recall}"
        assert metrics.hallucination_count == 1

    def test_evaluator_perfect_match(self):
        """Extracted 与 Gold 完全一致 → Precision=1.0, Recall=1.0"""
        from spike_05_llm_extract.src.constraint_extractor import ConstraintRule

        gold = {"constraint_ids": ["C01", "C02"], "constraint_count": 2}
        extracted = [
            ConstraintRule(id="C01", type="hard", rule="r1"),
            ConstraintRule(id="C02", type="soft", rule="r2"),
        ]

        evaluator = ExtractionEvaluator()
        metrics = evaluator.evaluate(extracted, gold)

        assert metrics.precision == 1.0
        assert metrics.recall == 1.0
        assert metrics.hallucination_count == 0
