"""多通道检索：合并意图限定检索和全局向量检索结果。"""

from __future__ import annotations

import logging
from typing import Any

from app.services.settings_service import get_runtime_settings

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
        self.vector_store = vector_store
        self.embeddings = embeddings

    def _ensure_vector_store(self):
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
        effective_top_k = top_k if top_k is not None else get_runtime_settings().top_k
        logger.info("Starting multi-channel retrieval: top_k=%s query=%s", effective_top_k, query[:50])
        self._ensure_vector_store()

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
        seen_contents: dict[str, RetrievedChunk] = {}
        for chunk in chunks:
            content_key = chunk.content[:100]
            existing = seen_contents.get(content_key)
            if existing is None or chunk.score > existing.score:
                seen_contents[content_key] = chunk
        return list(seen_contents.values())
