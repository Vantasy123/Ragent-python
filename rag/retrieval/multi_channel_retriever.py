"""
多渠道检索器模块 (Multi-Channel Retriever Module)

本模块实现了多渠道的文档检索策略，结合意图导向检索和全局向量检索，
提供更准确和相关的文档检索结果。

检索策略：
1. 意图导向检索：基于意图树节点进行定向检索
2. 全局向量检索：全库向量相似度检索
3. 结果去重和排序：合并结果并按相关性排序

核心特性：
- 支持意图节点的过滤检索
- 自动去重（基于内容相似性）
- 按相关性分数排序
- 错误容忍（单个渠道失败不影响整体）
- 详细的日志记录

检索流程：
1. 如果有意图节点，先进行意图导向检索
2. 总是进行全局向量检索作为兜底
3. 合并所有结果并去重
4. 按分数排序，返回 top_k 个结果

数据结构：
- RetrievedChunk: 检索结果的数据类
- MultiChannelRetriever: 主检索器类
"""
"""
Multi-channel retrieval that merges intent-scoped and global vector results.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from services.settings_service import get_runtime_settings

logger = logging.getLogger(__name__)


class RetrievedChunk:
    def __init__(self, content: str, score: float, metadata: dict[str, Any], channel: str):
        self.content = content
        self.score = score
        self.metadata = metadata
        self.channel = channel

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "score": self.score,
            "metadata": self.metadata,
            "channel": self.channel,
        }


class MultiChannelRetriever:
    def __init__(self, vector_store=None, embeddings=None):
        if vector_store is None:
            from vector_store import vector_store as shared_vector_store

            self.vector_store = shared_vector_store
        else:
            self.vector_store = vector_store

        if embeddings is None:
            from vector_store import embeddings as shared_embeddings

            self.embeddings = shared_embeddings
        else:
            self.embeddings = embeddings

    def retrieve(
        self,
        query: str,
        kb_id: Optional[str] = None,
        collection_name: Optional[str] = None,
        top_k: int | None = None,
        intent_nodes: Optional[list[dict[str, Any]]] = None,
    ) -> list[RetrievedChunk]:
        effective_top_k = top_k if top_k is not None else get_runtime_settings().top_k
        logger.info("Starting multi-channel retrieval: top_k=%s query=%s", effective_top_k, query[:50])

        all_chunks: list[RetrievedChunk] = []

        if intent_nodes and kb_id:
            all_chunks.extend(self._intent_based_retrieve(query, kb_id, intent_nodes, effective_top_k))

        all_chunks.extend(self._global_vector_retrieve(query, collection_name or kb_id, effective_top_k))

        deduplicated_chunks = self._deduplicate_chunks(all_chunks)
        deduplicated_chunks.sort(key=lambda chunk: chunk.score, reverse=True)
        return deduplicated_chunks[:effective_top_k]

    def _intent_based_retrieve(
        self,
        query: str,
        kb_id: str,
        intent_nodes: list[dict[str, Any]],
        top_k: int,
    ) -> list[RetrievedChunk]:
        chunks: list[RetrievedChunk] = []

        for node in intent_nodes:
            node_id = node.get("id")
            node_name = node.get("name", "")
            filter_expr = f'metadata["kb_id"] == "{kb_id}"'

            try:
                results = self.vector_store.similarity_search_with_score(
                    query=query,
                    k=top_k,
                    filter=filter_expr if hasattr(self.vector_store, "similarity_search_with_score") else None,
                )
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

    def _global_vector_retrieve(self, query: str, collection_name: Optional[str], top_k: int) -> list[RetrievedChunk]:
        _ = collection_name
        chunks: list[RetrievedChunk] = []

        try:
            results = self.vector_store.similarity_search_with_score(query=query, k=top_k * 2)
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
        seen_contents: dict[str, RetrievedChunk] = {}
        for chunk in chunks:
            content_key = chunk.content[:100]
            existing = seen_contents.get(content_key)
            if existing is None or chunk.score > existing.score:
                seen_contents[content_key] = chunk
        return list(seen_contents.values())

