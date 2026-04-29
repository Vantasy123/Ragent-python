"""Trace 服务，负责链路运行和节点 span 的持久化。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.domain.models import TraceRun, TraceSpan


@dataclass
class TraceSpanHandle:
    """Trace span 的临时句柄，完成时再写入数据库。"""

    trace_id: str
    operation: str
    started_at: float = field(default_factory=time.time)
    input_data: dict[str, Any] = field(default_factory=dict)
    context_data: dict[str, Any] = field(default_factory=dict)


class TraceService:
    """数据库持久化 Trace 服务。"""

    def __init__(self, db: Session):
        self.db = db

    def start_run(self, session_id: str | None = None, user_id: str | None = None, task_id: str | None = None) -> TraceRun:
        run = TraceRun(session_id=session_id, user_id=user_id, task_id=task_id, status="running")
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def create_span(
        self,
        trace_id: str,
        operation: str,
        input_data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        **legacy_input: Any,
    ) -> TraceSpanHandle:
        """创建 span 句柄。

        - `input_data`：显式输入摘要
        - `metadata`：节点上下文，不参与输入输出混用
        - `legacy_input`：兼容旧调用，默认视为输入摘要
        """

        return TraceSpanHandle(
            trace_id=trace_id,
            operation=operation,
            input_data=input_data or legacy_input,
            context_data=metadata or {},
        )

    def complete_span(
        self,
        handle: TraceSpanHandle,
        status: str = "success",
        error_message: str = "",
        output_data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        **legacy_output: Any,
    ) -> None:
        """完成 span 并写入结构化输入输出。

        为兼容旧代码，`metadata=` 在这里仍然可传，但统一视为输出摘要。
        """

        resolved_output = dict(output_data or {})
        if metadata:
            resolved_output.update(metadata)
        if legacy_output:
            resolved_output.update(legacy_output)

        span_metadata = {
            "input": handle.input_data,
            "output": resolved_output,
            "context": handle.context_data,
        }

        resolved_duration_ms = duration_ms if duration_ms is not None else int((time.time() - handle.started_at) * 1000)
        # Trace 节点是面向排障查看的最小单位，低于 1ms 的节点也保留为 1ms，避免页面误判为未计时。
        resolved_duration_ms = max(1, int(resolved_duration_ms))

        span = TraceSpan(
            trace_id=handle.trace_id,
            operation=handle.operation,
            status=status,
            duration_ms=resolved_duration_ms,
            metadata_json=span_metadata,
            error_message=error_message,
        )
        self.db.add(span)
        self.db.commit()

    def complete_run(self, trace_id: str, status: str = "success") -> None:
        run = self.db.query(TraceRun).filter(TraceRun.id == trace_id).first()
        if not run:
            return
        total = self.db.query(TraceSpan.duration_ms).filter(TraceSpan.trace_id == trace_id).all()
        run.total_duration_ms = sum(item[0] or 0 for item in total)
        run.status = status
        self.db.commit()
