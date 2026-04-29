from __future__ import annotations

import math
import os

from langchain_core.documents import Document
from sqlalchemy.orm import joinedload

from app.core.database import SessionLocal
from app.domain.models import KnowledgeChunk, KnowledgeDocument, KnowledgeBase
from app.knowledge.vector_store import get_vector_store


def main() -> None:
    """把 MySQL 中已启用的知识库分块批量回填到 Milvus。"""

    batch_size = int(os.getenv("BATCH_SIZE", "16"))
    db = SessionLocal()
    store = get_vector_store()

    try:
        query = (
            db.query(KnowledgeChunk)
            .join(KnowledgeDocument, KnowledgeChunk.doc_id == KnowledgeDocument.id)
            .join(KnowledgeBase, KnowledgeChunk.kb_id == KnowledgeBase.id)
            .options(joinedload(KnowledgeChunk.document))
            .filter(KnowledgeChunk.enabled.is_(True))
            .filter(KnowledgeDocument.enabled.is_(True))
            .filter(KnowledgeBase.enabled.is_(True))
            .order_by(KnowledgeChunk.created_at.asc())
        )

        chunks = query.all()
        total = len(chunks)
        print(f"TOTAL_CHUNKS: {total}")
        if total == 0:
            return

        for index in range(0, total, batch_size):
            batch = chunks[index : index + batch_size]
            documents: list[Document] = []
            ids: list[str] = []

            for chunk in batch:
                document = chunk.document
                metadata = dict(chunk.meta_data or {})
                metadata.update(
                    {
                        "chunk_id": chunk.id,
                        "kb_id": chunk.kb_id,
                        "doc_id": chunk.doc_id,
                        "source": getattr(document, "doc_name", ""),
                        "file_url": getattr(document, "file_url", ""),
                        "chunk_index": chunk.chunk_index,
                    }
                )
                documents.append(Document(page_content=chunk.content, metadata=metadata))
                ids.append(chunk.id)

            # add_documents 内部已做幂等删除，这里直接批量写入即可。
            store.add_documents(documents, ids=ids)
            current = min(index + batch_size, total)
            print(f"BATCH: {math.ceil(current / batch_size)} WRITTEN: {current}/{total}")

        store.collection.load()
        print(f"MILVUS_ENTITIES: {store.collection.num_entities}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
