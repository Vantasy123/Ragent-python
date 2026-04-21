"""
追踪收集器
收集和记录全链路追踪信息
"""
import logging
import time
import uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class TraceStatus(Enum):
    """追踪状态"""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class TraceSpan:
    """追踪跨度（单个操作）"""
    span_id: str
    trace_id: str
    operation: str           # 操作名称
    start_time: float        # 开始时间戳
    end_time: Optional[float] = None  # 结束时间戳
    duration_ms: Optional[float] = None  # 耗时（毫秒）
    status: TraceStatus = TraceStatus.SUCCESS
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    
    def complete(self, status: TraceStatus = TraceStatus.SUCCESS, error: str = None):
        """完成跨度"""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.status = status
        if error:
            self.error_message = error
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "operation": self.operation,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "end_time": datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
            "duration_ms": round(self.duration_ms, 2) if self.duration_ms else None,
            "status": self.status.value,
            "metadata": self.metadata,
            "error_message": self.error_message
        }


@dataclass
class TraceContext:
    """追踪上下文"""
    trace_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    spans: List[TraceSpan] = field(default_factory=list)
    status: TraceStatus = TraceStatus.SUCCESS
    total_duration_ms: Optional[float] = None
    
    def create_span(self, operation: str, **metadata) -> TraceSpan:
        """
        创建新的跨度
        
        Args:
            operation: 操作名称
            **metadata: 元数据
            
        Returns:
            创建的跨度
        """
        span = TraceSpan(
            span_id=str(uuid.uuid4())[:8],
            trace_id=self.trace_id,
            operation=operation,
            start_time=time.time(),
            metadata=metadata
        )
        self.spans.append(span)
        
        logger.debug(f"[Trace] Span created: {operation} ({span.span_id})")
        
        return span
    
    def complete(self, status: TraceStatus = TraceStatus.SUCCESS):
        """完成追踪"""
        end_time = time.time()
        self.total_duration_ms = (end_time - self.start_time) * 1000
        self.status = status
        
        logger.info(f"[Trace] Completed: {self.trace_id}, duration={self.total_duration_ms:.2f}ms, spans={len(self.spans)}")
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "trace_id": self.trace_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
            "total_duration_ms": round(self.total_duration_ms, 2) if self.total_duration_ms else None,
            "status": self.status.value,
            "spans": [span.to_dict() for span in self.spans],
            "span_count": len(self.spans)
        }


class TraceCollector:
    """追踪收集器"""
    
    def __init__(self, max_traces: int = 1000):
        """
        初始化追踪收集器
        
        Args:
            max_traces: 最大保留的追踪数量
        """
        self.traces: Dict[str, TraceContext] = {}
        self.max_traces = max_traces
        
        logger.info(f"Trace Collector initialized (max_traces={max_traces})")
    
    def start_trace(self, user_id: str = None, session_id: str = None) -> TraceContext:
        """
        开始新的追踪
        
        Args:
            user_id: 用户ID
            session_id: 会话ID
            
        Returns:
            追踪上下文
        """
        trace_id = str(uuid.uuid4())
        
        context = TraceContext(
            trace_id=trace_id,
            user_id=user_id,
            session_id=session_id
        )
        
        # 限制追踪数量
        if len(self.traces) >= self.max_traces:
            # 删除最旧的追踪
            oldest_trace_id = min(self.traces.keys(), key=lambda k: self.traces[k].start_time)
            del self.traces[oldest_trace_id]
        
        self.traces[trace_id] = context
        
        logger.info(f"[Trace] Started: {trace_id}")
        
        return context
    
    def get_trace(self, trace_id: str) -> Optional[TraceContext]:
        """
        获取追踪
        
        Args:
            trace_id: 追踪ID
            
        Returns:
            追踪上下文，如果不存在则返回 None
        """
        return self.traces.get(trace_id)
    
    def list_traces(self, limit: int = 50) -> List[Dict]:
        """
        列出最近的追踪
        
        Args:
            limit: 返回数量限制
            
        Returns:
            追踪列表（简化版）
        """
        # 按开始时间降序排序
        sorted_traces = sorted(
            self.traces.values(),
            key=lambda t: t.start_time,
            reverse=True
        )
        
        result = []
        for trace in sorted_traces[:limit]:
            result.append({
                "trace_id": trace.trace_id,
                "user_id": trace.user_id,
                "session_id": trace.session_id,
                "start_time": datetime.fromtimestamp(trace.start_time).isoformat(),
                "total_duration_ms": round(trace.total_duration_ms, 2) if trace.total_duration_ms else None,
                "status": trace.status.value,
                "span_count": len(trace.spans)
            })
        
        return result
    
    def get_trace_summary(self) -> Dict[str, Any]:
        """获取追踪统计摘要"""
        if not self.traces:
            return {
                "total_traces": 0,
                "avg_duration_ms": 0,
                "success_rate": 0
            }
        
        total = len(self.traces)
        success_count = sum(1 for t in self.traces.values() if t.status == TraceStatus.SUCCESS)
        durations = [t.total_duration_ms for t in self.traces.values() if t.total_duration_ms]
        
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        return {
            "total_traces": total,
            "success_count": success_count,
            "error_count": total - success_count,
            "success_rate": f"{(success_count / total * 100):.2f}%" if total > 0 else "0%",
            "avg_duration_ms": round(avg_duration, 2),
            "max_duration_ms": round(max(durations), 2) if durations else 0,
            "min_duration_ms": round(min(durations), 2) if durations else 0
        }
    
    def clear_old_traces(self, older_than_seconds: int = 3600):
        """
        清理旧追踪
        
        Args:
            older_than_seconds: 清理超过此时间的追踪
        """
        current_time = time.time()
        traces_to_remove = [
            trace_id for trace_id, trace in self.traces.items()
            if (current_time - trace.start_time) > older_than_seconds
        ]
        
        for trace_id in traces_to_remove:
            del self.traces[trace_id]
        
        if traces_to_remove:
            logger.info(f"Cleared {len(traces_to_remove)} old traces")
