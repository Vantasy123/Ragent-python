"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

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
