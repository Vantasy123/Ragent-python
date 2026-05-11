"""模块导读：本文件位于 app/observability/trace/trace_collector.py，属于可观测性层。

主要职责：记录 Trace、Span 和运行过程，帮助回放 Agent 与 RAG 的执行路径。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

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
    """TraceSpan 辅助类型：把相关字段和行为组织在一起，减少跨模块传递零散数据。"""
    name: str
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    status: TraceStatus = TraceStatus.RUNNING
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def complete(self, status: TraceStatus = TraceStatus.SUCCESS, error: str = "", **metadata: Any) -> None:
        """complete 函数：完成一次运行流程，把最终状态、耗时和输出结果写回。"""
        self.end_time = time.time()
        self.status = status
        self.error = error
        self.metadata.update(metadata)


@dataclass
class TraceContext:
    """TraceContext 辅助类型：把相关字段和行为组织在一起，减少跨模块传递零散数据。"""
    trace_id: str
    question: str = ""
    spans: list[TraceSpan] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    status: TraceStatus = TraceStatus.RUNNING

    def add_span(self, name: str, **metadata: Any) -> TraceSpan:
        """add_span 函数：向已有对象或存储中追加一条新数据，用于维护消息、Span 或工具结果。"""
        span = TraceSpan(name=name, metadata=metadata)
        self.spans.append(span)
        return span

    def complete(self, status: TraceStatus = TraceStatus.SUCCESS) -> None:
        """complete 函数：完成一次运行流程，把最终状态、耗时和输出结果写回。"""
        self.status = status


class TraceCollector:
    """兼容旧工作流的进程内 Trace 收集器。"""

    def __init__(self, max_traces: int = 1000) -> None:
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
        self.max_traces = max_traces
        self.traces: dict[str, TraceContext] = {}

    def start_trace(self, question: str = "", trace_id: str | None = None) -> TraceContext:
        """start_trace 函数：启动一次运行流程，并创建后续追踪或状态更新需要的初始记录。"""
        trace_id = trace_id or str(uuid.uuid4())
        if len(self.traces) >= self.max_traces:
            oldest = next(iter(self.traces))
            self.traces.pop(oldest, None)
        ctx = TraceContext(trace_id=trace_id, question=question)
        self.traces[trace_id] = ctx
        return ctx

    def get_trace(self, trace_id: str | None) -> TraceContext | None:
        """get_trace 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
        if not trace_id:
            return None
        return self.traces.get(trace_id)
