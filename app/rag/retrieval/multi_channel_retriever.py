"""多通道检索：合并意图限定检索和全局向量检索结果。"""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.rag.retrieval.keyword_bm25 import KeywordBM25Retriever
from app.services.settings_service import get_runtime_settings

logger = logging.getLogger(__name__)


class RetrievedChunk:
    """RetrievedChunk 辅助类型：把相关字段和行为组织在一起，减少跨模块传递零散数据。"""
    def __init__(self, content: str, score: float, metadata: dict[str, Any], channel: str):
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
        self.content = content
        self.score = score
        self.metadata = metadata
        self.channel = channel

    def to_dict(self) -> dict[str, Any]:
        """to_dict 函数：把内部对象转换成普通 dict，便于 JSON 序列化、接口返回或 Trace 记录。"""
        return {
            "content": self.content,
            "score": self.score,
            "metadata": self.metadata,
            "channel": self.channel,
        }


class MultiChannelRetriever:
    """MultiChannelRetriever 检索器：负责从知识库或索引中召回候选片段，供 RAG 后续拼接和回答使用。"""
    def __init__(self, vector_store=None, embeddings=None, keyword_retriever: KeywordBM25Retriever | None = None):
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
        self.vector_store = vector_store
        self.embeddings = embeddings
        self.keyword_retriever = keyword_retriever or KeywordBM25Retriever()

    def _ensure_vector_store(self):
        """_ensure_vector_store 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        if self.vector_store is None:
            from app.knowledge.vector_store import vector_store as shared_vector_store

            self.vector_store = shared_vector_store
        if self.embeddings is None:
            from app.knowledge.vector_store import embeddings as shared_embeddings

            self.embeddings = shared_embeddings
        return self.vector_store

    def retrieve(
        self,
        query: str,
        kb_id: str | None = None,
        collection_name: str | None = None,
        top_k: int | None = None,
        intent_nodes: list[dict[str, Any]] | None = None,
    ) -> list[RetrievedChunk]:
        """retrieve 函数：执行检索逻辑，从知识库或索引中找出和用户问题最相关的内容。"""
        effective_top_k = top_k if top_k is not None else get_runtime_settings().top_k
        logger.info("Starting multi-channel retrieval: top_k=%s query=%s", effective_top_k, query[:50])

        vector_chunks: list[RetrievedChunk] = []
        try:
            self._ensure_vector_store()
            if intent_nodes and kb_id:
                vector_chunks.extend(self._intent_based_retrieve(query, kb_id, intent_nodes, effective_top_k))

            vector_chunks.extend(self._global_vector_retrieve(query, collection_name or kb_id, effective_top_k))
        except Exception as exc:
            logger.error("Vector retrieval setup failed: %s", exc)

        if not getattr(settings, "HYBRID_RETRIEVAL_ENABLED", True):
            return self._rank_and_trim(vector_chunks, effective_top_k)

        keyword_chunks = self._keyword_retrieve(query, collection_name or kb_id, effective_top_k)
        if not keyword_chunks:
            return self._rank_and_trim(vector_chunks, effective_top_k)
        if not vector_chunks:
            return self._rank_and_trim(keyword_chunks, effective_top_k)

        return self._rrf_fuse(vector_chunks, keyword_chunks, effective_top_k)

    def _intent_based_retrieve(
        self,
        query: str,
        kb_id: str,
        intent_nodes: list[dict[str, Any]],
        top_k: int,
    ) -> list[RetrievedChunk]:
        """_intent_based_retrieve 函数：执行检索逻辑，从知识库或索引中找出和用户问题最相关的内容。"""
        chunks: list[RetrievedChunk] = []

        for node in intent_nodes:
            node_id = node.get("id")
            node_name = node.get("name", "")
            # Milvus 侧把 kb_id 拉平成独立字段，检索时直接按字段过滤即可。
            filter_expr = f'kb_id == "{kb_id}"'

            try:
                results = self.vector_store.similarity_search_with_score(query=query, k=top_k, filter=filter_expr)
                for doc, score in results:
                    chunks.append(
                        RetrievedChunk(
                            content=doc.page_content,
                            score=score,
                            metadata={**doc.metadata, "intent_node": node_id},
                            channel=f"intent:{node_name}",
                        )
                    )
            except Exception as exc:
                logger.error("Intent-based retrieval failed for node %s: %s", node_id, exc)

        return chunks

    def _global_vector_retrieve(self, query: str, collection_name: str | None, top_k: int) -> list[RetrievedChunk]:
        """_global_vector_retrieve 函数：执行检索逻辑，从知识库或索引中找出和用户问题最相关的内容。"""
        chunks: list[RetrievedChunk] = []

        try:
            filter_expr = f'kb_id == "{collection_name}"' if collection_name else None
            results = self.vector_store.similarity_search_with_score(query=query, k=top_k * 2, filter=filter_expr)
            for doc, score in results:
                chunks.append(
                    RetrievedChunk(
                        content=doc.page_content,
                        score=score,
                        metadata=doc.metadata,
                        channel="global",
                    )
                )
        except Exception as exc:
            logger.error("Global vector retrieval failed: %s", exc)

        return chunks

    def _deduplicate_chunks(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """_deduplicate_chunks 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        seen_contents: dict[str, RetrievedChunk] = {}
        for chunk in chunks:
            content_key = self._chunk_key(chunk)
            existing = seen_contents.get(content_key)
            if existing is None or chunk.score > existing.score:
                seen_contents[content_key] = chunk
        return list(seen_contents.values())

    def _keyword_retrieve(self, query: str, kb_id: str | None, top_k: int) -> list[RetrievedChunk]:
        """执行 BM25 关键词召回；失败时返回空列表，保留向量检索可用性。"""

        try:
            rows = self.keyword_retriever.retrieve(query=query, kb_id=kb_id, top_k=top_k * 2)
        except Exception as exc:
            logger.warning("Keyword BM25 retrieval failed, fallback to vector only: %s", exc)
            return []

        return [
            RetrievedChunk(
                content=row.content,
                score=row.score,
                metadata={**row.metadata, "keywordScore": row.score},
                channel="keyword",
            )
            for row in rows
        ]

    def _rank_and_trim(self, chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
        """按当前分数排序并截断，供单路召回或降级路径复用。"""

        deduplicated = self._deduplicate_chunks(chunks)
        deduplicated.sort(key=lambda chunk: chunk.score, reverse=True)
        return deduplicated[:top_k]

    def _rrf_fuse(self, vector_chunks: list[RetrievedChunk], keyword_chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
        """用 Reciprocal Rank Fusion 融合向量和关键词两路结果。"""

        rrf_k = max(1, int(getattr(settings, "HYBRID_RRF_K", 60)))
        ranked_sources = [
            ("vector", self._rank_and_trim(vector_chunks, top_k * 2)),
            ("keyword", self._rank_and_trim(keyword_chunks, top_k * 2)),
        ]
        merged: dict[str, RetrievedChunk] = {}

        for source_name, chunks in ranked_sources:
            for rank, chunk in enumerate(chunks, start=1):
                key = self._chunk_key(chunk)
                rrf_score = 1.0 / (rrf_k + rank)
                existing = merged.get(key)
                if existing is None:
                    metadata = dict(chunk.metadata or {})
                    metadata["hybridChannels"] = [chunk.channel]
                    metadata["rrfScore"] = rrf_score
                    if source_name == "vector":
                        metadata["vectorScore"] = chunk.score
                    else:
                        metadata["keywordScore"] = chunk.score
                    merged[key] = RetrievedChunk(content=chunk.content, score=rrf_score, metadata=metadata, channel="hybrid")
                    continue

                existing.score += rrf_score
                existing.metadata["rrfScore"] = existing.score
                channels = existing.metadata.setdefault("hybridChannels", [])
                if chunk.channel not in channels:
                    channels.append(chunk.channel)
                if source_name == "vector":
                    existing.metadata["vectorScore"] = max(float(existing.metadata.get("vectorScore", 0.0)), float(chunk.score))
                else:
                    existing.metadata["keywordScore"] = max(float(existing.metadata.get("keywordScore", 0.0)), float(chunk.score))

        fused = list(merged.values())
        fused.sort(key=lambda chunk: chunk.score, reverse=True)
        return fused[:top_k]

    def _chunk_key(self, chunk: RetrievedChunk) -> str:
        """优先按 chunk_id 去重；缺少 ID 时回退到内容前缀。"""

        metadata = chunk.metadata or {}
        chunk_id = metadata.get("chunk_id") or metadata.get("chunkId")
        if chunk_id:
            return f"id:{chunk_id}"
        return f"content:{chunk.content[:100]}"
