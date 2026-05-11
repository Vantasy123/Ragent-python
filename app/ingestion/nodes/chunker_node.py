"""文本分块节点，支持固定窗口、递归规则、Markdown 和语义分块。"""

from __future__ import annotations

import logging
import math
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.chunk import VectorChunk
from app.core.config import settings as app_settings
from app.core.text_sanitizer import sanitize_text

logger = logging.getLogger(__name__)


@dataclass
class TextSegment:
    """分块前的候选文本片段。"""

    content: str
    start: int
    end: int
    metadata: dict[str, Any] = field(default_factory=dict)


class ChunkerNode:
    """将解析后的文本切成可索引片段。

    fixed 保留历史字符滑窗行为；recursive/markdown 尽量保留自然边界；
    semantic 在规则候选段基础上用 embedding 相似度寻找低相关断点。
    """

    def execute(self, context, settings: dict[str, Any]) -> dict[str, Any]:
        """执行当前节点的核心逻辑，输入上下文并返回结构化处理结果。"""
        text = sanitize_text(context.raw_text or "")
        if not text.strip():
            return {"success": False, "error": "解析文本为空"}

        config = self._normalize_settings(settings)
        strategy = str(settings.get("strategy") or "recursive").lower()
        if strategy not in {"fixed", "recursive", "markdown", "semantic"}:
            strategy = "recursive"

        if strategy == "fixed":
            chunks = self._fixed_chunks(text, context, config)
            fallback = ""
        elif strategy == "markdown":
            chunks = self._rule_chunks(text, context, config, strategy="markdown")
            fallback = ""
        elif strategy == "semantic":
            chunks, fallback = self._semantic_chunks(text, context, config)
        else:
            chunks = self._rule_chunks(text, context, config, strategy="recursive")
            fallback = ""

        context.chunks = chunks
        result = {"success": True, "chunk_count": len(chunks), "strategy": strategy}
        if fallback:
            context.metadata["chunker_fallback"] = fallback
            result["fallback"] = fallback
        return result

    def _normalize_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """规范分块参数，避免重叠大于长度导致死循环。"""

        chunk_size = max(1, int(settings.get("chunk_size") or app_settings.CHUNK_SIZE))
        overlap = max(0, int(settings.get("chunk_overlap") or app_settings.CHUNK_OVERLAP))
        overlap = min(overlap, max(0, chunk_size - 1))
        min_chunk_size = max(20, int(settings.get("min_chunk_size") or max(80, chunk_size // 3)))
        max_chunk_size = max(chunk_size, int(settings.get("max_chunk_size") or chunk_size))
        semantic_threshold = float(settings.get("semantic_threshold") or 0.72)
        return {
            "chunk_size": chunk_size,
            "chunk_overlap": overlap,
            "min_chunk_size": min(min_chunk_size, max_chunk_size),
            "max_chunk_size": max_chunk_size,
            "semantic_threshold": semantic_threshold,
            "preserve_headings": bool(settings.get("preserve_headings", True)),
        }

    def _fixed_chunks(self, text: str, context, config: dict[str, Any]) -> list[VectorChunk]:
        """历史固定字符滑窗分块，保持兼容。"""

        chunk_size = int(config["chunk_size"])
        overlap = int(config["chunk_overlap"])
        step = max(1, chunk_size - overlap)
        chunks: list[VectorChunk] = []
        for index, start in enumerate(range(0, len(text), step)):
            end = min(len(text), start + chunk_size)
            content = text[start:end].strip()
            if not content:
                continue
            chunks.append(self._make_chunk(context, index, content, "fixed", start, end))
        return chunks

    def _rule_chunks(self, text: str, context, config: dict[str, Any], strategy: str) -> list[VectorChunk]:
        """按自然边界聚合候选段，超长片段固定窗口兜底。"""

        segments = self._markdown_segments(text) if strategy == "markdown" else self._recursive_segments(text)
        packed = self._pack_segments(segments, config)
        return [
            self._make_chunk(
                context,
                index,
                segment.content,
                strategy,
                segment.start,
                segment.end,
                extra_metadata=segment.metadata,
            )
            for index, segment in enumerate(packed)
        ]

    def _semantic_chunks(self, text: str, context, config: dict[str, Any]) -> tuple[list[VectorChunk], str]:
        """规则候选段 + embedding 相似度断点；失败时回退 recursive。"""

        try:
            segments = self._recursive_segments(text)
            if len(segments) <= 1:
                return self._rule_chunks(text, context, config, strategy="recursive"), ""

            vectors = self._embed_segments([segment.content for segment in segments])
            if len(vectors) != len(segments):
                raise RuntimeError("embedding 返回数量与候选段不一致")

            semantic_segments = self._pack_semantic_segments(segments, vectors, config)
            chunks = [
                self._make_chunk(
                    context,
                    index,
                    segment.content,
                    "semantic",
                    segment.start,
                    segment.end,
                    extra_metadata=segment.metadata,
                )
                for index, segment in enumerate(semantic_segments)
            ]
            return chunks, ""
        except Exception as exc:
            logger.warning("语义分块失败，回退 recursive：%s", exc)
            return self._rule_chunks(text, context, config, strategy="recursive"), f"semantic fallback to recursive: {exc}"

    def _recursive_segments(self, text: str) -> list[TextSegment]:
        """优先按空行段落切分，段落过长时按句子边界切分。"""

        segments: list[TextSegment] = []
        for match in re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", text, flags=re.S):
            paragraph = match.group(0).strip()
            if not paragraph:
                continue
            start = match.start()
            end = match.end()
            segments.extend(self._split_long_segment(TextSegment(paragraph, start, end), max_chars=900))
        return segments or [TextSegment(text.strip(), 0, len(text))]

    def _markdown_segments(self, text: str) -> list[TextSegment]:
        """按 Markdown 标题、列表、代码块和空行生成候选段。"""

        segments: list[TextSegment] = []
        heading_path: list[str] = []
        buffer: list[str] = []
        buffer_start = 0
        cursor = 0
        in_code = False

        def flush(end_pos: int) -> None:
            """flush 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
            nonlocal buffer, buffer_start
            content = "".join(buffer).strip()
            if content:
                metadata = {"heading_path": list(heading_path)}
                segments.extend(self._split_long_segment(TextSegment(content, buffer_start, end_pos, metadata), max_chars=900))
            buffer = []

        for line in text.splitlines(keepends=True):
            line_start = cursor
            line_end = cursor + len(line)
            stripped = line.strip()
            heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if stripped.startswith("```"):
                in_code = not in_code

            if heading and not in_code:
                flush(line_start)
                level = len(heading.group(1))
                title = heading.group(2).strip()
                heading_path = heading_path[: level - 1] + [title]
                buffer_start = line_start
                buffer = [line]
            elif not stripped and not in_code:
                flush(line_end)
            else:
                if not buffer:
                    buffer_start = line_start
                buffer.append(line)
            cursor = line_end

        flush(len(text))
        return segments or self._recursive_segments(text)

    def _split_long_segment(self, segment: TextSegment, max_chars: int) -> list[TextSegment]:
        """过长候选段按句子边界继续拆分。"""

        if len(segment.content) <= max_chars:
            return [segment]

        parts: list[TextSegment] = []
        offset = segment.start
        sentence_matches = list(re.finditer(r"[^。！？!?；;\n]+[。！？!?；;]?", segment.content))
        for match in sentence_matches:
            content = match.group(0).strip()
            if not content:
                continue
            start = offset + match.start()
            end = offset + match.end()
            if len(content) <= max_chars:
                parts.append(TextSegment(content, start, end, dict(segment.metadata)))
                continue
            parts.extend(self._fixed_segments(content, start, max_chars, overlap=0, metadata=segment.metadata))
        return parts or self._fixed_segments(segment.content, segment.start, max_chars, overlap=0, metadata=segment.metadata)

    def _fixed_segments(self, content: str, base_start: int, chunk_size: int, overlap: int, metadata: dict[str, Any]) -> list[TextSegment]:
        """固定窗口生成候选段，供超长片段兜底。"""

        step = max(1, chunk_size - overlap)
        segments = []
        for start in range(0, len(content), step):
            end = min(len(content), start + chunk_size)
            piece = content[start:end].strip()
            if piece:
                segments.append(TextSegment(piece, base_start + start, base_start + end, dict(metadata)))
        return segments

    def _pack_segments(self, segments: list[TextSegment], config: dict[str, Any]) -> list[TextSegment]:
        """把候选段聚合到目标 chunk 大小，尽量不跨越自然边界。"""

        chunk_size = int(config["chunk_size"])
        overlap = int(config["chunk_overlap"])
        packed: list[TextSegment] = []
        current: list[TextSegment] = []

        def flush() -> None:
            """flush 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
            nonlocal current
            if not current:
                return
            packed.append(self._merge_segments(current, overlap))
            current = []

        for segment in segments:
            if len(segment.content) > chunk_size:
                flush()
                packed.extend(self._fixed_segments(segment.content, segment.start, chunk_size, overlap, segment.metadata))
                continue
            next_length = len("\n\n".join([item.content for item in current] + [segment.content]))
            if current and next_length > chunk_size:
                flush()
            current.append(segment)
        flush()
        return self._apply_overlap(packed, overlap)

    def _pack_semantic_segments(self, segments: list[TextSegment], vectors: list[list[float]], config: dict[str, Any]) -> list[TextSegment]:
        """根据相邻段落语义相似度与长度共同决定断点。"""

        threshold = float(config["semantic_threshold"])
        max_chunk_size = int(config["max_chunk_size"])
        min_chunk_size = int(config["min_chunk_size"])
        overlap = int(config["chunk_overlap"])
        packed: list[TextSegment] = []
        current: list[TextSegment] = []

        def current_length() -> int:
            """current_length 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
            return len("\n\n".join(item.content for item in current))

        def flush() -> None:
            """flush 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
            nonlocal current
            if current:
                packed.append(self._merge_segments(current, overlap))
                current = []

        for index, segment in enumerate(segments):
            if not current:
                current.append(segment)
                continue

            similarity = self._cosine(vectors[index - 1], vectors[index])
            would_length = len("\n\n".join([item.content for item in current] + [segment.content]))
            should_break = (similarity < threshold and current_length() >= min_chunk_size) or would_length > max_chunk_size
            if should_break:
                current[-1].metadata["semantic_break_score"] = round(similarity, 4)
                flush()
            current.append(segment)
        flush()
        return self._apply_overlap(packed, overlap)

    def _merge_segments(self, segments: list[TextSegment], overlap: int) -> TextSegment:
        """合并候选段，并把上一段尾部作为轻量 overlap。"""

        content = "\n\n".join(segment.content for segment in segments).strip()
        metadata = dict(segments[0].metadata)
        heading_paths = [segment.metadata.get("heading_path") for segment in segments if segment.metadata.get("heading_path")]
        if heading_paths:
            metadata["heading_path"] = heading_paths[-1]
        break_scores = [segment.metadata.get("semantic_break_score") for segment in segments if segment.metadata.get("semantic_break_score") is not None]
        if break_scores:
            metadata["semantic_break_score"] = break_scores[-1]
        start = segments[0].start
        end = segments[-1].end
        return TextSegment(content, start, end, metadata)

    def _apply_overlap(self, segments: list[TextSegment], overlap: int) -> list[TextSegment]:
        """给规则分块补充相邻 chunk 的真实文本重叠。"""

        if overlap <= 0 or len(segments) <= 1:
            return segments
        with_overlap = [segments[0]]
        for previous, current in zip(segments, segments[1:], strict=False):
            prefix = previous.content[-overlap:].strip()
            if not prefix or current.content.startswith(prefix):
                with_overlap.append(current)
                continue
            metadata = dict(current.metadata)
            metadata["overlap_chars"] = len(prefix)
            with_overlap.append(
                TextSegment(
                    content=f"{prefix}\n\n{current.content}",
                    start=max(0, current.start - len(prefix)),
                    end=current.end,
                    metadata=metadata,
                )
            )
        return with_overlap

    def _embed_segments(self, texts: list[str]) -> list[list[float]]:
        """复用现有 embedding 服务计算候选段向量。"""

        from app.knowledge.vector_store import embeddings

        return embeddings.embed_documents(texts)

    def _cosine(self, left: list[float], right: list[float]) -> float:
        """计算相邻候选段向量余弦相似度。"""

        if not left or not right or len(left) != len(right):
            raise RuntimeError("embedding 向量维度异常")
        dot = sum(a * b for a, b in zip(left, right, strict=False))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)

    def _make_chunk(
        self,
        context,
        index: int,
        content: str,
        strategy: str,
        char_start: int,
        char_end: int,
        extra_metadata: dict[str, Any] | None = None,
    ) -> VectorChunk:
        """创建统一 VectorChunk，补齐检索和审计需要的元数据。"""

        doc_id = context.metadata.get("doc_id") or str(uuid.uuid4())
        metadata = {
            "source": context.metadata.get("source", ""),
            "doc_id": context.metadata.get("doc_id"),
            "kb_id": context.metadata.get("kb_id"),
            "chunk_index": index,
            "chunk_strategy": strategy,
            "char_start": char_start,
            "char_end": char_end,
        }
        metadata.update(extra_metadata or {})
        return VectorChunk(
            chunk_id=f"{doc_id}_chunk_{index}",
            content=content.strip(),
            index=index,
            metadata=metadata,
        )
