"""
Spike-9 测试用例：RAG 知识检索召回率
====================================
Test Case IDs: S9-TC01 ~ S9-TC06 (关键技术验证计划 §10.2)

Go/No-Go 必须标准:
  - Recall@5 ≥ 0.80
  - 检索延迟 ≤ 500ms
"""
import time
import pytest
from conftest import SPIKE9_DATA, Thresholds

# ════════════════════════════════════════════════════════════════
# 待实现模块导入 — TDD RED phase
# ════════════════════════════════════════════════════════════════
from spike_09_rag.src.document_processor import DocumentProcessor
from spike_09_rag.src.vector_store import VectorStore
from spike_09_rag.src.retriever import HybridRetriever
from spike_09_rag.src.chunker import ChineseTextChunker


# ──────────────────── 标注查询集 ────────────────────
# 预标注的 Query → 正确文档 / 正确段落 映射
ANNOTATED_QUERIES = [
    {
        "query": "焊接车间最小安全距离",
        "relevant_doc": "GJB2639A_excerpt.md",
        "relevant_section": "安全距离",
    },
    {
        "query": "铝合金化学铣切质量检验",
        "relevant_doc": "HB5469_chemical_milling.md",
        "relevant_section": "化学铣切",
    },
    {
        "query": "航空航天质量管理体系基础设施",
        "relevant_doc": "AS9100D_layout_requirements.md",
        "relevant_section": "基础设施",
    },
    {
        "query": "C919总装脉动线站位设计",
        "relevant_doc": "COMAC_FAL_design_spec.md",
        "relevant_section": "脉动线",
    },
    {
        "query": "数控加工精度要求",
        "relevant_doc": "GJB2639A_excerpt.md",
        "relevant_section": "数控加工",
    },
    {
        "query": "NDT无损检测区域布局",
        "relevant_doc": "COMAC_FAL_design_spec.md",
        "relevant_section": "NDT",
    },
    {
        "query": "喷涂区域通风排气要求",
        "relevant_doc": "AS9100D_layout_requirements.md",
        "relevant_section": "环境要求",
    },
    {
        "query": "起落架安装工位吊车要求",
        "relevant_doc": "COMAC_FAL_design_spec.md",
        "relevant_section": "起落架",
    },
    {
        "query": "铆接工艺质量标准",
        "relevant_doc": "GJB2639A_excerpt.md",
        "relevant_section": "铆接",
    },
    {
        "query": "化学品存储安全规范",
        "relevant_doc": "HB5469_chemical_milling.md",
        "relevant_section": "化学品",
    },
    {
        "query": "适航审定文件追溯性",
        "relevant_doc": "AS9100D_layout_requirements.md",
        "relevant_section": "追溯",
    },
    {
        "query": "AGV自动导引运输通道规划",
        "relevant_doc": "COMAC_FAL_design_spec.md",
        "relevant_section": "AGV",
    },
    {
        "query": "设备间距与工位布局间距标准",
        "relevant_doc": "GJB2639A_excerpt.md",
        "relevant_section": "间距",
    },
    {
        "query": "复合材料加工废液处理",
        "relevant_doc": "HB5469_chemical_milling.md",
        "relevant_section": "废液",
    },
    {
        "query": "测量设备校准与计量管理",
        "relevant_doc": "AS9100D_layout_requirements.md",
        "relevant_section": "校准",
    },
    {
        "query": "翼身对接精度对齐系统",
        "relevant_doc": "COMAC_FAL_design_spec.md",
        "relevant_section": "翼身",
    },
    {
        "query": "工装夹具定位精度",
        "relevant_doc": "GJB2639A_excerpt.md",
        "relevant_section": "工装",
    },
    {
        "query": "表面处理清洗脱脂工艺",
        "relevant_doc": "HB5469_chemical_milling.md",
        "relevant_section": "表面处理",
    },
    {
        "query": "不合格品控制隔离区",
        "relevant_doc": "AS9100D_layout_requirements.md",
        "relevant_section": "不合格品",
    },
    {
        "query": "脉动线节拍时间与缓冲区设计",
        "relevant_doc": "COMAC_FAL_design_spec.md",
        "relevant_section": "节拍",
    },
]


@pytest.mark.p2
@pytest.mark.spike9
class TestDocumentIngestion:
    """S9-TC01: 文档向量化入库"""

    def test_tc01_ingest_all_documents(self, rag_documents):
        """5 份行业规范文档分块 + Embedding + 写入"""
        processor = DocumentProcessor()
        store = VectorStore()

        for doc_path in rag_documents:
            chunks = processor.process(doc_path)
            assert len(chunks) > 0, f"文档 {doc_path.name} 分块失败"
            store.add_chunks(chunks, source=doc_path.name)

        assert store.total_chunks >= len(rag_documents)

    def test_tc01_chunk_metadata(self, rag_documents):
        """分块应包含来源文件、段落编号、原文等元数据"""
        processor = DocumentProcessor()
        chunks = processor.process(rag_documents[0])

        for chunk in chunks:
            assert chunk.source is not None
            assert chunk.text is not None
            assert len(chunk.text) > 0
            assert chunk.chunk_index >= 0


@pytest.mark.p2
@pytest.mark.spike9
class TestPreciseQuery:
    """S9-TC02: 精确查询"""

    def test_tc02_exact_query(self, rag_documents):
        """"焊接车间最小安全距离" 应在 Top-5 中返回正确条款"""
        processor = DocumentProcessor()
        store = VectorStore()
        for doc_path in rag_documents:
            store.add_chunks(processor.process(doc_path), source=doc_path.name)

        retriever = HybridRetriever(store)
        results = retriever.retrieve("焊接车间最小安全距离", top_k=5)

        assert len(results) > 0
        sources = [r.source for r in results]
        assert "GJB2639A_excerpt.md" in sources


@pytest.mark.p2
@pytest.mark.spike9
class TestFuzzyQuery:
    """S9-TC03: 模糊查询"""

    def test_tc03_fuzzy_query(self, rag_documents):
        """"喷涂区域通风要求" 应在 Top-5 中返回相关条款"""
        processor = DocumentProcessor()
        store = VectorStore()
        for doc_path in rag_documents:
            store.add_chunks(processor.process(doc_path), source=doc_path.name)

        retriever = HybridRetriever(store)
        results = retriever.retrieve("喷涂区域通风要求", top_k=5)

        assert len(results) > 0
        # 至少有一条结果来自包含环境/通风要求的文档
        all_texts = " ".join([r.text for r in results])
        assert any(kw in all_texts for kw in ["通风", "排气", "环境"]), (
            "模糊查询结果中未包含通风/排气相关内容"
        )


@pytest.mark.p2
@pytest.mark.spike9
class TestHybridSearchPerformance:
    """S9-TC04: 混合检索 (向量 + BM25) 延迟"""

    def test_tc04_latency(self, rag_documents):
        """混合检索延迟 ≤ 500ms"""
        processor = DocumentProcessor()
        store = VectorStore()
        for doc_path in rag_documents:
            store.add_chunks(processor.process(doc_path), source=doc_path.name)

        retriever = HybridRetriever(store)

        latencies = []
        for q in ANNOTATED_QUERIES[:5]:
            start = time.perf_counter()
            _ = retriever.retrieve(q["query"], top_k=5)
            latencies.append((time.perf_counter() - start) * 1000)

        avg_ms = sum(latencies) / len(latencies)
        assert avg_ms <= Thresholds.S9_LATENCY_MS, (
            f"平均检索延迟 {avg_ms:.0f}ms > {Thresholds.S9_LATENCY_MS}ms"
        )


@pytest.mark.p2
@pytest.mark.spike9
class TestChineseChunking:
    """S9-TC05: 中文分块质量"""

    def test_tc05_no_mid_sentence_break(self, rag_documents):
        """分块不应在句子中间截断"""
        chunker = ChineseTextChunker(
            chunk_size=500,
            chunk_overlap=50,
            separators=["。", "；", "\n\n", "\n"],
        )

        for doc_path in rag_documents:
            text = doc_path.read_text(encoding="utf-8")
            chunks = chunker.split(text)

            for i, chunk in enumerate(chunks):
                # 非最后一块应以句号/分号/换行结尾
                if i < len(chunks) - 1:
                    stripped = chunk.strip()
                    assert stripped[-1] in "。；\n）)", (
                        f"分块 {i} 在非自然边界截断: ...{stripped[-20:]}"
                    )


@pytest.mark.p2
@pytest.mark.spike9
class TestRecallEvaluation:
    """S9-TC06: Recall@5 评估 — 20 个预标注 Query"""

    def test_tc06_recall_at_5(self, rag_documents):
        """Recall@5 ≥ 0.80"""
        processor = DocumentProcessor()
        store = VectorStore()
        for doc_path in rag_documents:
            store.add_chunks(processor.process(doc_path), source=doc_path.name)

        retriever = HybridRetriever(store)

        hits = 0
        for aq in ANNOTATED_QUERIES:
            results = retriever.retrieve(aq["query"], top_k=5)
            sources = [r.source for r in results]
            if aq["relevant_doc"] in sources:
                hits += 1

        recall_at_5 = hits / len(ANNOTATED_QUERIES)
        assert recall_at_5 >= Thresholds.S9_RECALL_AT_5, (
            f"Recall@5 = {recall_at_5:.2f} < {Thresholds.S9_RECALL_AT_5}"
            f" ({hits}/{len(ANNOTATED_QUERIES)} 命中)"
        )


# ════════════════════════════════════════════════════════════════
# L4: Mock Embedding 确定性检索验证
# ════════════════════════════════════════════════════════════════

@pytest.mark.p2
@pytest.mark.spike9
class TestMockDeterministicRetrieval:
    """L4: Mock Embedding → 精确排序验证 (消除向量模型非确定性)"""

    def test_exact_ranking_with_mock(self, rag_documents):
        """固定 embedding → 检索排序必须精确匹配"""
        processor = DocumentProcessor()
        store = VectorStore()
        for doc_path in rag_documents:
            store.add_chunks(processor.process(doc_path), source=doc_path.name)

        # Mock: "焊接" 或 "GJB" 相关文本返回相同向量方向
        def mock_embedding(text):
            if "焊接" in text or "GJB" in text or "安全距离" in text:
                return [1.0, 0.0, 0.0]
            return [0.0, 1.0, 0.0]

        retriever = HybridRetriever(store, embedding_model=mock_embedding)
        results = retriever.retrieve("焊接车间安全距离", top_k=3)

        assert len(results) > 0
        assert results[0].source == "GJB2639A_excerpt.md", (
            f"Top-1 应为 GJB2639A, 实际: {results[0].source}"
        )

    def test_mock_score_ordering(self, rag_documents):
        """检索结果 score 应降序排列"""
        processor = DocumentProcessor()
        store = VectorStore()
        for doc_path in rag_documents:
            store.add_chunks(processor.process(doc_path), source=doc_path.name)

        retriever = HybridRetriever(store)
        results = retriever.retrieve("C919总装脉动线", top_k=5)

        if len(results) > 1:
            scores = [r.score for r in results]
            assert scores == sorted(scores, reverse=True), (
                f"Score 非降序: {scores}"
            )


# ════════════════════════════════════════════════════════════════
# 统计性能验证 — 检索延迟中位数
# ════════════════════════════════════════════════════════════════

@pytest.mark.p2
@pytest.mark.spike9
class TestRAGStatisticalPerformance:
    """检索延迟取 5 次中位数"""

    def test_latency_median(self, rag_documents):
        """混合检索中位数延迟 ≤ 500ms"""
        from conftest import benchmark_median

        processor = DocumentProcessor()
        store = VectorStore()
        for doc_path in rag_documents:
            store.add_chunks(processor.process(doc_path), source=doc_path.name)

        retriever = HybridRetriever(store)

        median_ms, _ = benchmark_median(
            lambda: retriever.retrieve("焊接车间安全距离", top_k=5),
            warmup=1, iterations=5,
        )
        assert median_ms <= Thresholds.S9_LATENCY_MS, (
            f"检索中位数 {median_ms:.0f}ms > {Thresholds.S9_LATENCY_MS}ms"
        )
