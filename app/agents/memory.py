"""模块导读：本文件位于 app/agents/memory.py，属于Agent 编排层。

主要职责：描述智能体、工具调用、计划执行、审批边界和流式事件的运行方式。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.time_utils import shanghai_now, to_shanghai_iso


@dataclass
class MemoryItem:
    """共享记忆中的一条事件。"""

    agent: str
    event_type: str
    content: str
    data: dict[str, Any] = field(default_factory=dict)
    # 共享记忆只存在于单次运行内，直接按东八区记录可读时间，便于报告展示。
    created_at: datetime = field(default_factory=shanghai_now)


class SharedMemory:
    """单次编排运行内的轻量共享记忆。

    这里不是长期记忆，只在一次 OrchestratorAgent.run 中收集关键观察，
    用于最终报告汇总，避免报告只罗列原始工具返回。
    """

    def __init__(self) -> None:
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
        self.items: list[MemoryItem] = []

    def add(self, agent: str, event_type: str, content: str, data: dict[str, Any] | None = None) -> None:
        """追加一条共享事件。"""

        self.items.append(MemoryItem(agent=agent, event_type=event_type, content=content, data=data or {}))

    def summarize(self) -> str:
        """返回最近观察摘要，避免最终报告过长。"""

        return "\n".join(f"[{item.agent}] {item.content}" for item in self.items[-20:])

    def to_dict(self) -> list[dict[str, Any]]:
        """转换为可序列化结构，供 SSE report 事件返回。"""

        return [
            {
                "agent": item.agent,
                "eventType": item.event_type,
                "content": item.content,
                "data": item.data,
                "createdAt": to_shanghai_iso(item.created_at),
            }
            for item in self.items
        ]
