"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

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
        self.sessions: dict[str, ChatSession] = {}

    def create_session(self, user_id: str | None = None, title: str = "新对话") -> str:
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = ChatSession(id=session_id, user_id=user_id, title=title)
        return session_id

    def get_session(self, session_id: str) -> ChatSession | None:
        return self.sessions.get(session_id)

    def append_message(self, session_id: str, role: str, content: str) -> None:
        session = self.sessions.setdefault(session_id, ChatSession(id=session_id))
        session.messages.append({"role": role, "content": content})
