from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from models import Conversation, ConversationMessage
from services.settings_service import get_runtime_settings

logger = logging.getLogger(__name__)


def _role_label(role: str) -> str:
    return "用户" if role == "user" else "助手"


class SessionManager:
    """Compatibility layer for the older workflow session manager API."""

    def __init__(self, db_session: Session):
        self.db = db_session
        self.max_history_rounds = 10

    def create_session(self, user_id: str | None = None, title: str = "新对话") -> str:
        session_id = str(uuid.uuid4())
        session = Conversation(id=session_id, user_id=user_id, title=title, message_count=0)
        self.db.add(session)
        self.db.commit()
        logger.info("Session created: %s", session_id)
        return session_id

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        message = ConversationMessage(
            id=str(uuid.uuid4()),
            conversation_id=session_id,
            role=role,
            content=content,
            meta_data=metadata or {},
        )
        self.db.add(message)
        session = self.db.query(Conversation).filter(Conversation.id == session_id).first()
        if session:
            session.message_count += 1
            session.updated_at = datetime.utcnow()
        self.db.commit()

    def get_chat_history(self, session_id: str, max_rounds: int | None = None) -> list[dict[str, str]]:
        runtime_settings = get_runtime_settings(self.db)
        limit = (max_rounds or runtime_settings.history_keep_turns or self.max_history_rounds) * 2
        messages = (
            self.db.query(ConversationMessage)
            .filter(ConversationMessage.conversation_id == session_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
            .all()
        )
        messages.reverse()
        history = [{"role": msg.role, "content": msg.content} for msg in messages]
        session = self.db.query(Conversation).filter(Conversation.id == session_id).first()
        if runtime_settings.summary_enabled and session and session.summary:
            return [{"role": "system", "content": f"对话摘要:\n{session.summary}"}] + history
        return history

    def compress_context(self, session_id: str) -> str:
        history = self.get_chat_history(session_id, max_rounds=self.max_history_rounds)
        return self._format_history_for_prompt(history)

    def _format_history_for_prompt(self, history: list[dict[str, str]]) -> str:
        lines: list[str] = []
        for msg in history:
            role = "系统" if msg["role"] == "system" else _role_label(msg["role"])
            lines.append(f"{role}: {msg['content']}")
        return "\n".join(lines)

    def clear_session(self, session_id: str) -> None:
        self.db.query(ConversationMessage).filter(ConversationMessage.conversation_id == session_id).delete()
        session = self.db.query(Conversation).filter(Conversation.id == session_id).first()
        if session:
            session.message_count = 0
            session.summary = ""
        self.db.commit()

    def delete_session(self, session_id: str) -> None:
        session = self.db.query(Conversation).filter(Conversation.id == session_id).first()
        if session:
            self.db.delete(session)
            self.db.commit()
