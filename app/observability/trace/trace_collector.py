"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TraceStatus(str, Enum):
    """进程内 Trace 状态。"""

    SUCCESS = "success"
    ERROR = "error"
    RUNNING = "running"


@dataclass
class TraceSpan:
    name: str
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    status: TraceStatus = TraceStatus.RUNNING
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def complete(self, status: TraceStatus = TraceStatus.SUCCESS, error: str = "", **metadata: Any) -> None:
        self.end_time = time.time()
        self.status = status
        self.error = error
        self.metadata.update(metadata)


@dataclass
class TraceContext:
    trace_id: str
    question: str = ""
    spans: list[TraceSpan] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    status: TraceStatus = TraceStatus.RUNNING

    def add_span(self, name: str, **metadata: Any) -> TraceSpan:
        span = TraceSpan(name=name, metadata=metadata)
        self.spans.append(span)
        return span

    def complete(self, status: TraceStatus = TraceStatus.SUCCESS) -> None:
        self.status = status


class TraceCollector:
    """兼容旧工作流的进程内 Trace 收集器。"""

    def __init__(self, max_traces: int = 1000) -> None:
        self.max_traces = max_traces
        self.traces: dict[str, TraceContext] = {}

    def start_trace(self, question: str = "", trace_id: str | None = None) -> TraceContext:
        trace_id = trace_id or str(uuid.uuid4())
        if len(self.traces) >= self.max_traces:
            oldest = next(iter(self.traces))
            self.traces.pop(oldest, None)
        ctx = TraceContext(trace_id=trace_id, question=question)
        self.traces[trace_id] = ctx
        return ctx

    def get_trace(self, trace_id: str | None) -> TraceContext | None:
        if not trace_id:
            return None
        return self.traces.get(trace_id)
