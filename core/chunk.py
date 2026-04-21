"""Core data structures for document vector chunks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorChunk:
    """A single parsed document chunk before or after embedding."""

    chunk_id: str
    content: str
    index: int
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
