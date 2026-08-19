"""模块导读：本文件位于 app/rag/retrieval/reranker.py，属于 RAG 问答链路。

主要职责：处理知识检索结果重排 (Rerank)，支持 SiliconFlow API、本地 FlagEmbedding 与轻量词项相关性兜底。
"""

from __future__ import annotations

import logging
import math
import re
import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


class RerankerService:
    """检索结果重排服务；支持 SiliconFlow 云端 API、本地 FlagEmbedding 以及词项相关性兜底。"""

    def __init__(self) -> None:
        """延迟加载重排模型或客户端配置。"""
        self._model = None
        self._model_load_failed = False

    def rerank_with_threshold(self, query: str, documents: list[str], threshold: float = 0.0) -> list[dict]:
        """按相关性分数重排文档，并按阈值过滤低质量候选。"""
        if not documents:
            return []

        scores, source = self._compute_scores(query, documents)
        effective_threshold = max(0.0, float(threshold or 0.0)) if source in ("siliconflow", "model") else 0.0

        ranked = [
            {"index": index, "score": float(score), "source": source}
            for index, score in enumerate(scores)
            if float(score) >= effective_threshold
        ]
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked

    def _compute_scores(self, query: str, documents: list[str]) -> tuple[list[float], str]:
        """按配置优先级依次尝试 SiliconFlow API、本地 FlagEmbedding 与词频兜底。"""
        if not getattr(settings, "RERANK_ENABLED", True):
            return self._lexical_scores(query, documents), "lexical"

        provider = str(getattr(settings, "RERANK_PROVIDER", "siliconflow")).lower()

        # 1. 优先尝试 SiliconFlow / API 模式
        if provider in ("siliconflow", "api", "auto"):
            api_scores = self._api_scores(query, documents)
            if api_scores is not None:
                return api_scores, "siliconflow"

        # 2. 尝试本地 FlagEmbedding 模式
        if provider in ("flag_embedding", "local", "auto"):
            model_scores = self._model_scores(query, documents)
            if model_scores is not None:
                return model_scores, "model"

        # 3. 词项覆盖率启发式降级
        return self._lexical_scores(query, documents), "lexical"

    def _api_scores(self, query: str, documents: list[str]) -> list[float] | None:
        """调用 SiliconFlow 等兼容的 /v1/rerank 接口计算 Cross-Encoder 语义匹配得分。"""
        api_key = (
            getattr(settings, "RERANK_API_KEY", "")
            or getattr(settings, "SILICONFLOW_API_KEY", "")
            or getattr(settings, "EMBEDDING_API_KEY", "")
        )
        if not api_key:
            return None

        base_url = (
            getattr(settings, "RERANK_API_BASE", "")
            or getattr(settings, "EMBEDDING_API_BASE", "")
            or "https://api.siliconflow.cn/v1"
        ).rstrip("/")
        if not base_url.endswith("/rerank"):
            base_url = f"{base_url}/rerank"

        model_name = getattr(settings, "RERANK_MODEL", "BAAI/bge-reranker-v2-m3")

        try:
            resp = requests.post(
                base_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "query": query,
                    "documents": documents,
                    "top_n": len(documents),
                    "return_documents": False,
                },
                timeout=15.0,
            )
            if resp.status_code != 200:
                logger.warning("SiliconFlow Rerank API 调用失败: %s - %s", resp.status_code, resp.text)
                return None

            data = resp.json()
            results = data.get("results", [])
            if not results:
                return None

            # 将 results 按原始 index 还原为列表
            scores = [0.0] * len(documents)
            for item in results:
                idx = item.get("index")
                score = item.get("relevance_score", 0.0)
                if idx is not None and 0 <= idx < len(scores):
                    scores[idx] = float(score)

            return scores
        except Exception as exc:
            logger.warning("SiliconFlow Rerank API 请求异常，将自动降级: %s", exc)
            return None

    def _model_scores(self, query: str, documents: list[str]) -> list[float] | None:
        """使用本地 FlagEmbedding reranker 计算 query-document 相关性分数。"""
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
            logger.warning("本地 Rerank 模型计算失败，将回退: %s", exc)
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
            logger.warning("本地 Rerank 模型不可用，使用词项或 API 模式: %s", exc)
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
        """中英文统一分词，优先用 jieba，缺失时回退正则与 2-gram。"""
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
