"""模块导读：本文件位于 app/rag/retrieval/reranker.py，属于RAG 问答链路。

主要职责：处理问题改写、知识检索、结果融合、重排和最终回答生成。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

import logging
import math
import re

from app.core.config import settings

logger = logging.getLogger(__name__)


class RerankerService:
    """检索结果重排服务；优先使用专用模型，失败时回退到轻量词项相关性。"""

    def __init__(self) -> None:
        """延迟加载重排模型，避免应用启动时强依赖本地模型可用。"""
        self._model = None
        self._model_load_failed = False

    def rerank_with_threshold(self, query: str, documents: list[str], threshold: float = 0.0) -> list[dict]:
        """按相关性分数重排文档，并按阈值过滤低质量候选。"""
        if not documents:
            return []

        scores = self._model_scores(query, documents)
        source = "model" if scores is not None else "lexical"
        effective_threshold = max(0.0, float(threshold or 0.0)) if source == "model" else 0.0
        if scores is None:
            scores = self._lexical_scores(query, documents)

        ranked = [
            {"index": index, "score": float(score), "source": source}
            for index, score in enumerate(scores)
            if float(score) >= effective_threshold
        ]
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked

    def _model_scores(self, query: str, documents: list[str]) -> list[float] | None:
        """使用 FlagEmbedding reranker 计算 query-document 相关性分数。"""
        if not getattr(settings, "RERANK_ENABLED", True):
            return None
        if str(getattr(settings, "RERANK_PROVIDER", "flag_embedding")).lower() != "flag_embedding":
            return None

        model = self._load_model()
        if model is None:
            return None

        try:
            pairs = [[query, doc] for doc in documents]
            raw_scores = model.compute_score(pairs, normalize=True)
            if isinstance(raw_scores, (int, float)):
                raw_scores = [float(raw_scores)]
            scores = [float(score) for score in raw_scores]
            if len(scores) != len(documents):
                raise RuntimeError("rerank 模型返回分数数量与文档数量不一致")
            return scores
        except Exception as exc:
            logger.warning("Rerank model scoring failed, falling back to lexical rerank: %s", exc)
            return None

    def _load_model(self):
        """懒加载本地 rerank 模型；加载失败后本进程内不反复重试。"""
        if self._model is not None:
            return self._model
        if self._model_load_failed:
            return None
        try:
            from FlagEmbedding import FlagReranker

            self._model = FlagReranker(
                getattr(settings, "RERANK_MODEL", "BAAI/bge-reranker-base"),
                use_fp16=False,
            )
            return self._model
        except Exception as exc:
            self._model_load_failed = True
            logger.warning("Rerank model unavailable, using lexical fallback: %s", exc)
            return None

    def _lexical_scores(self, query: str, documents: list[str]) -> list[float]:
        """无模型时使用词项覆盖率、短文本惩罚和原始排序生成稳定分数。"""
        query_tokens = self._tokenize(query)
        query_set = set(query_tokens)
        if not query_set:
            return [1.0 / (index + 1) for index, _ in enumerate(documents)]

        scores: list[float] = []
        for index, document in enumerate(documents):
            doc_tokens = self._tokenize(document)
            doc_set = set(doc_tokens)
            overlap = len(query_set.intersection(doc_set))
            coverage = overlap / max(len(query_set), 1)
            density = overlap / math.sqrt(max(len(doc_set), 1))
            order_bonus = 1.0 / (index + 2)
            scores.append(round(coverage * 0.65 + density * 0.25 + order_bonus * 0.10, 6))
        return scores

    def _tokenize(self, text: str) -> list[str]:
        """中英文统一分词，优先用 jieba，缺失时回退正则。"""
        normalized = (text or "").strip().lower()
        if not normalized:
            return []
        try:
            import jieba

            tokens = [token.strip() for token in jieba.cut(normalized) if token.strip()]
        except Exception:
            tokens = re.findall(r"[\w\u4e00-\u9fff]+", normalized)
        expanded = [token for token in tokens if len(token) > 1 or token.isdigit()]
        for span in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
            expanded.extend(span[index : index + 2] for index in range(0, len(span) - 1))
        return list(dict.fromkeys(expanded))
