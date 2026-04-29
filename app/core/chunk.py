"""文档向量分块的核心数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorChunk:
    """解析后的单个文档分块，可用于向量化前后传递。"""

    chunk_id: str
    content: str
    index: int
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


