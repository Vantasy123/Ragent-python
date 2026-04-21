"""
Indexer node for writing chunk documents into PGVector.
"""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


class IndexerNode:
    def __init__(self, vector_store=None, embeddings=None):
        self.vector_store = vector_store
        self.embeddings = embeddings

    def execute(self, context, settings: dict[str, Any]) -> dict[str, Any]:
        try:
            if not context.chunks:
                return {"success": False, "error": "No chunks to index"}

            logger.info("Indexing %s chunks to vector store", len(context.chunks))

            if self.vector_store is None:
                from vector_store import vector_store

                self.vector_store = vector_store

            if self.embeddings is None:
                from vector_store import embeddings

                self.embeddings = embeddings

            from langchain_core.documents import Document

            indexed_count = 0
            failures: list[str] = []

            for chunk in context.chunks:
                try:
                    doc = Document(
                        page_content=chunk.content,
                        metadata={
                            **chunk.metadata,
                            "task_id": context.task_id,
                            "doc_id": context.metadata.get("doc_id"),
                            "kb_id": context.metadata.get("kb_id"),
                        },
                    )
                    self.vector_store.add_documents([doc], ids=[chunk.chunk_id])
                    indexed_count += 1
                except Exception as exc:
                    logger.error("Failed to index chunk %s: %s", chunk.chunk_id, exc)
                    failures.append(f"{chunk.chunk_id}: {exc}")

            logger.info(
                "Indexing completed: %s/%s chunks indexed",
                indexed_count,
                len(context.chunks),
            )

            if indexed_count == 0:
                return {
                    "success": False,
                    "error": f"Vector indexing failed: {failures[0] if failures else 'no chunks indexed'}",
                }

            if indexed_count < len(context.chunks):
                return {
                    "success": False,
                    "error": f"Only indexed {indexed_count}/{len(context.chunks)} chunks. First error: {failures[0]}",
                }

            return {"success": True, "indexed_count": indexed_count}
        except Exception as exc:
            logger.error("Indexer node failed: %s", exc, exc_info=True)
            return {"success": False, "error": str(exc)}
