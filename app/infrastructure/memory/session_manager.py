"""模块导读：本文件位于 app/infrastructure/memory/session_manager.py，属于基础设施适配层。

主要职责：封装模型、MCP、会话等外部或底层依赖，降低业务代码耦合。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.core.time_utils import shanghai_now


@dataclass
class ChatSession:
    """进程内会话对象，仅用于兼容旧工作流。"""

    id: str
    user_id: str | None = None
    title: str = "新对话"
    messages: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=shanghai_now)


class SessionManager:
    """轻量会话管理器，正式会话仍以数据库 conversation 表为准。"""

    def __init__(self) -> None:
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
        self.sessions: dict[str, ChatSession] = {}

    def create_session(self, user_id: str | None = None, title: str = "新对话") -> str:
        """create_session 函数：创建新的业务记录，负责组织入库字段并返回创建后的结果。"""
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = ChatSession(id=session_id, user_id=user_id, title=title)
        return session_id

    def get_session(self, session_id: str) -> ChatSession | None:
        """get_session 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
        return self.sessions.get(session_id)

    def append_message(self, session_id: str, role: str, content: str) -> None:
        """append_message 函数：向已有对象或存储中追加一条新数据，用于维护消息、Span 或工具结果。"""
        session = self.sessions.setdefault(session_id, ChatSession(id=session_id))
        session.messages.append({"role": role, "content": content})
