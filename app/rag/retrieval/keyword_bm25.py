"""轻量 BM25 关键词检索，用 MySQL 分块补充向量召回。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.core.database import SessionLocal
from app.domain.models import KnowledgeChunk

logger = logging.getLogger(__name__)

try:  # pragma: no cover - 依赖缺失时应降级到纯向量检索。
    import jieba
    from rank_bm25 import BM25Okapi
except Exception:  # pragma: no cover
    jieba = None
    BM25Okapi = None


@dataclass
class KeywordChunk:
    """关键词检索命中的分块。"""

    content: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class KeywordBM25Retriever:
    """基于数据库分块的临时 BM25 检索器。

    当前实现每次按范围读取一批启用分块并构建 BM25，避免新增索引表或数据库迁移。
    """

    def retrieve(self, query: str, kb_id: str | None = None, top_k: int = 10) -> list[KeywordChunk]:
        """执行关键词检索；任何异常由调用方记录后降级。"""

        query_tokens = self.tokenize(query)
        if not query_tokens:
            return []
        if BM25Okapi is None:
            raise RuntimeError("rank-bm25 或 jieba 未安装")

        rows = self._load_chunks(kb_id)
        if not rows:
            return []

        corpus_tokens = [self.tokenize(row.content) for row in rows]
        bm25 = BM25Okapi(corpus_tokens)
        scores = bm25.get_scores(query_tokens)
        ranked = sorted(enumerate(scores), key=lambda item: float(item[1]), reverse=True)
        query_token_set = set(query_tokens)

        results: list[KeywordChunk] = []
        for index, score in ranked[: max(1, top_k)]:
            overlap = len(query_token_set.intersection(corpus_tokens[index]))
            if overlap <= 0:
                continue
            row = rows[index]
            metadata = dict(row.meta_data or {})
            metadata.update(
                {
                    "chunk_id": row.id,
                    "kb_id": row.kb_id,
                    "doc_id": row.doc_id,
                    "chunkIndex": row.chunk_index,
                }
            )
            # 小语料下 BM25 可能出现 0 或负分，叠加命中词数保证精确匹配不会被误过滤。
            results.append(KeywordChunk(content=row.content, score=float(score) + overlap, metadata=metadata))
        return results

    def tokenize(self, text: str) -> list[str]:
        """中英文统一分词；空文本返回空列表。"""

        normalized = (text or "").strip().lower()
        if not normalized:
            return []
        if jieba is not None:
            tokens = [token.strip() for token in jieba.cut(normalized) if token.strip()]
        else:
            tokens = re.findall(r"[\w\u4e00-\u9fff]+", normalized)
        return [token for token in tokens if len(token) > 1 or token.isdigit()]

    def _load_chunks(self, kb_id: str | None) -> list[KnowledgeChunk]:
        """从数据库读取启用分块，按配置限制最大参与 BM25 的数量。"""

        limit = max(1, int(getattr(settings, "HYBRID_KEYWORD_MAX_CHUNKS", 3000)))
        db = SessionLocal()
        try:
            query = db.query(KnowledgeChunk).filter(KnowledgeChunk.enabled.is_(True))
            if kb_id:
                query = query.filter(KnowledgeChunk.kb_id == kb_id)
            return query.order_by(KnowledgeChunk.updated_at.desc()).limit(limit).all()
        finally:
            db.close()
