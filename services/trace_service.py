"""
追踪服务模块 - Trace Service

提供全链路追踪功能，用于记录和分析 RAG 系统中的操作执行情况。
支持追踪运行（TraceRun）和追踪跨度（TraceSpan）的管理，
便于性能监控、问题排查和系统可观测性。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from models import TraceRun, TraceSpan


@dataclass
class TraceSpanHandle:
    """
    追踪跨度句柄类
    
    用于在创建和完成追踪跨度之间传递上下文信息。
    作为临时对象持有追踪跨度的初始状态，直到调用 complete_span 时持久化到数据库。
    
    Attributes:
        trace_id: 追踪运行ID，关联到具体的 TraceRun
        operation: 操作名称，描述当前执行的操作（如 "retrieval", "embedding", "llm_call"）
        started_at: 开始时间戳（Unix timestamp），用于计算持续时间
        metadata: 元数据字典，存储操作的额外信息（如输入参数、配置等）
    """
    trace_id: str
    operation: str
    started_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class TraceService:
    """
    追踪服务类
    
    提供追踪运行的生命周期管理，包括：
    - 启动新的追踪运行（start_run）
    - 创建追踪跨度（create_span）
    - 完成追踪跨度并记录结果（complete_span）
    - 完成追踪运行并汇总统计信息（complete_run）
    
    使用示例:
        ```python
        # 1. 启动追踪运行
        trace_service = TraceService(db_session)
        run = trace_service.start_run(session_id="session_123", user_id="user_456")
        
        # 2. 创建并记录操作跨度
        span_handle = trace_service.create_span(
            trace_id=run.id, 
            operation="document_parsing",
            file_name="example.pdf"
        )
        # ... 执行实际操作 ...
        trace_service.complete_span(span_handle, status="success")
        
        # 3. 完成追踪运行
        trace_service.complete_run(run.id, status="success")
        ```
    
    Attributes:
        db: SQLAlchemy 数据库会话对象，用于持久化追踪数据
    """

    def __init__(self, db: Session):
        """
        初始化追踪服务
        
        Args:
            db: SQLAlchemy 数据库会话，用于访问和操作追踪数据表
        """
        self.db = db

    def start_run(self, session_id: str | None = None, user_id: str | None = None, task_id: str | None = None) -> TraceRun:
        """
        启动一个新的追踪运行
        
        创建一条追踪运行记录，表示一个完整的业务流程或用户请求的开始。
        每个追踪运行可以包含多个追踪跨度，用于记录其中的各个子操作。
        
        Args:
            session_id: 会话ID，可选，用于关联到特定的对话会话
            user_id: 用户ID，可选，用于标识发起请求的用户
            task_id: 任务ID，可选，用于关联到特定的后台任务
            
        Returns:
            TraceRun: 新创建的追踪运行对象，包含自动生成的ID和初始状态
            
        Note:
            - 初始状态设置为 "running"
            - 创建后立即提交到数据库并刷新以获取生成的ID
        """
        run = TraceRun(session_id=session_id, user_id=user_id, task_id=task_id, status="running")
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def create_span(self, trace_id: str, operation: str, **metadata: Any) -> TraceSpanHandle:
        """
        创建一个追踪跨度句柄
        
        为追踪运行中的某个具体操作创建跨度句柄。此时不会立即写入数据库，
        而是返回一个句柄对象，等待操作完成后调用 complete_span 进行持久化。
        
        Args:
            trace_id: 追踪运行ID，关联到父级 TraceRun
            operation: 操作名称，描述当前执行的操作类型
                      常见值: "document_fetching", "text_parsing", "chunking", 
                             "embedding", "vector_search", "reranking", "llm_generation"
            **metadata: 可变数量的关键字参数，作为操作的元数据
                       例如: file_name="doc.pdf", model_name="gpt-4", chunk_count=100
                       
        Returns:
            TraceSpanHandle: 追踪跨度句柄对象，包含开始时间和元数据
            
        Note:
            - 开始时间在创建句柄时自动记录（time.time()）
            - 此方法不执行数据库操作，仅在内存中创建句柄
        """
        return TraceSpanHandle(trace_id=trace_id, operation=operation, metadata=metadata)

    def complete_span(self, handle: TraceSpanHandle, status: str = "success", error_message: str = "", **metadata: Any) -> None:
        """
        完成追踪跨度并持久化到数据库
        
        计算操作的持续时间，合并元数据，并将追踪跨度记录保存到数据库。
        这是追踪生命周期中的关键步骤，标志着某个子操作的完成。
        
        Args:
            handle: 之前通过 create_span 创建的追踪跨度句柄
            status: 操作状态，默认为 "success"
                   常见值: "success", "failed", "timeout", "cancelled"
            error_message: 错误信息，当 status 为 "failed" 时提供详细错误描述
            **metadata: 额外的元数据，将与创建时的元数据合并
                       例如: result_count=5, latency_ms=230, tokens_used=1500
                        
        Note:
            - 持续时间（duration_ms）根据开始时间和当前时间自动计算
            - 元数据合并策略：将 create_span 时的元数据与 complete_span 时的元数据合并
            - 特殊处理：如果合并后的元数据只包含一个 "metadata" 键且其值为字典，
              则展开该字典作为最终的元数据（避免嵌套过深）
            - 立即提交到数据库，确保追踪数据持久化
        """
        # 计算操作持续时间（毫秒）
        duration_ms = int((time.time() - handle.started_at) * 1000)
        
        # 合并元数据：创建时的元数据 + 完成时的元数据
        span_metadata = {**handle.metadata, **metadata}
        
        # 特殊处理：避免元数据嵌套过深
        # 如果最终只有一个 "metadata" 键且其值是字典，则展开它
        if set(span_metadata.keys()) == {"metadata"} and isinstance(span_metadata["metadata"], dict):
            span_metadata = span_metadata["metadata"]
        
        # 创建追踪跨度对象并保存到数据库
        span = TraceSpan(
            trace_id=handle.trace_id,
            operation=handle.operation,
            status=status,
            duration_ms=duration_ms,
            metadata_json=span_metadata,
            error_message=error_message,
        )
        self.db.add(span)
        self.db.commit()

    def complete_run(self, trace_id: str, status: str = "success") -> None:
        """
        完成追踪运行并汇总统计信息
        
        标记追踪运行为完成状态，并计算所有关联跨度的总持续时间。
        这标志着一个完整业务流程的结束。
        
        Args:
            trace_id: 追踪运行ID，指定要完成的追踪运行
            status: 最终状态，默认为 "success"
                   常见值: "success", "failed", "partial_success"
                   
        Note:
            - 如果找不到对应的追踪运行，静默返回（不抛出异常）
            - 总持续时间是所有关联跨度的 duration_ms 之和
            - 更新状态和总持续时间后立即提交到数据库
            
        Warning:
            - 该方法会查询所有关联的跨度来计算总持续时间，
              对于包含大量跨度的追踪运行可能影响性能
            - 建议在高频场景下考虑异步汇总或缓存优化
        """
        # 查询追踪运行记录
        run = self.db.query(TraceRun).filter(TraceRun.id == trace_id).first()
        if not run:
            # 如果追踪运行不存在，静默返回
            return
        
        # 查询该追踪运行下的所有跨度，获取持续时间列表
        total = (
            self.db.query(TraceSpan)
            .filter(TraceSpan.trace_id == trace_id)
            .with_entities(TraceSpan.duration_ms)
            .all()
        )
        
        # 计算总持续时间（所有跨度持续时间之和）
        run.total_duration_ms = sum(item[0] for item in total)
        
        # 更新追踪运行状态
        run.status = status
        
        # 提交更改到数据库
        self.db.commit()
