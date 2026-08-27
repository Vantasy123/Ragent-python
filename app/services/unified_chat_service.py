"""统一求职 Agent 聊天入口服务，支持智能求职模式 (job/auto) 与面经知识库问答模式 (rag)。"""

from __future__ import annotations

import uuid
from typing import AsyncIterator, Literal
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models import User
from app.services.chat_service import ConversationService, stream_chat
from app.services.runtime_state import concurrency_slot

ChatMode = Literal["auto", "rag", "job"]


class UnifiedChatService:
    """统一求职 Agent 聊天入口服务。

    - 智能求职 (job/auto)：优先走 ReAct 工具调用（简历解析、STAR 润色、人岗匹配、模拟面试出题、打招呼生成）。
    - 知识库问答 (rag)：走八股面经检索与标准知识库 RAG。
    """

    def __init__(self, db: Session):
        self.db = db

    async def stream(
        self,
        message: str,
        user: User,
        mode: ChatMode = "auto",
        conversation_id: str | None = None,
        deep_thinking: bool = False,
        attachments: list[dict] | None = None,
        model: str | None = None,
    ) -> AsyncIterator[dict]:
        """输出统一 SSE 聊天事件。"""

        service = ConversationService(self.db)
        conversation = service.get_conversation(conversation_id) if conversation_id else None
        if not conversation:
            conversation = service.create_conversation(user.id, message[:30] or "求职咨询会话")

        task_id = str(uuid.uuid4())
        channel = "job" if mode in {"job", "auto"} else "rag"

        # 融合附件文档文本
        full_message = message
        if attachments:
            snippets = []
            for att in attachments:
                fname = att.get("filename") or "附件文档"
                text = att.get("text") or ""
                if text:
                    snippets.append(
                        f"【用户上传的附件文档: {fname}】\n<attachment_content>\n{text}\n</attachment_content>"
                    )
            if snippets:
                full_message = f"{message}\n\n" + "\n\n".join(snippets)

        with concurrency_slot(f"chat:user:{user.id}", settings.CHAT_MAX_CONCURRENCY_PER_USER, settings.CONCURRENCY_COUNTER_TTL_SECONDS) as acquired:
            if not acquired:
                yield {"type": "error", "channel": channel, "content": "当前用户聊天并发已满，请等待上一轮回答完成"}
                return
            async for event in stream_chat(
                self.db,
                conversation.id,
                full_message,
                task_id,
                deep_thinking=deep_thinking,
                display_message=message,
                attachments_meta=attachments,
                model=model,
            ):
                event["channel"] = channel
                event.setdefault("conversationId", conversation.id)
                yield event
