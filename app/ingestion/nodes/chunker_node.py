"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.chunk import VectorChunk
from app.core.text_sanitizer import sanitize_text


class ChunkerNode:
    """将解析后的文本切成可索引片段。"""

    def execute(self, context, settings: dict[str, Any]) -> dict[str, Any]:
        text = sanitize_text(context.raw_text or "")
        if not text.strip():
            return {"success": False, "error": "解析文本为空"}
        chunk_size = int(settings.get("chunk_size") or 500)
        overlap = max(0, int(settings.get("chunk_overlap") or 50))
        step = max(1, chunk_size - overlap)
        chunks: list[VectorChunk] = []
        for index, start in enumerate(range(0, len(text), step)):
            content = text[start : start + chunk_size].strip()
            if not content:
                continue
            chunks.append(
                VectorChunk(
                    chunk_id=f"{context.metadata.get('doc_id') or uuid.uuid4()}_chunk_{index}",
                    content=content,
                    index=index,
                    metadata={
                        "source": context.metadata.get("source", ""),
                        "doc_id": context.metadata.get("doc_id"),
                        "kb_id": context.metadata.get("kb_id"),
                        "chunk_index": index,
                    },
                )
            )
        context.chunks = chunks
        return {"success": True, "chunk_count": len(chunks)}
