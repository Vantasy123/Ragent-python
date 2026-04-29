"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

import uuid
from typing import AsyncIterator, Literal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models import User
from app.services.chat_service import ConversationService, stream_chat
from app.services.ops_agent_service import OpsAgentService
from app.services.runtime_state import concurrency_slot

ChatMode = Literal["auto", "rag", "ops"]


# 自动路由关键词。命中这些词时，auto 模式会进入运维 Agent。
OPS_KEYWORDS = {
    "502",
    "docker",
    "compose",
    "容器",
    "日志",
    "健康检查",
    "重启",
    "nginx",
    "端口",
    "postgres",
    "mysql",
    "数据库连接",
    "api health",
    "服务异常",
    "后端",
    "前端代理",
}


def resolve_chat_mode(message: str, mode: ChatMode) -> Literal["rag", "ops"]:
    """根据用户指定模式或关键词规则选择底层通道。"""

    if mode != "auto":
        return mode
    lowered = message.lower()
    return "ops" if any(keyword in lowered or keyword in message for keyword in OPS_KEYWORDS) else "rag"


class UnifiedChatService:
    """统一聊天入口服务。

    前端只需要调用 /agent/chat：
    - 普通知识问答走 RAG 链路。
    - 运维问题走多 Agent 诊断链路。
    - auto 模式由 resolve_chat_mode 进行轻量路由。
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
    ) -> AsyncIterator[dict]:
        """根据通道输出统一 SSE 事件，并补充 channel 字段。"""

        channel = resolve_chat_mode(message, mode)

        if channel == "ops":
            # 运维 Agent 可以读取容器状态和触发审批，必须限制为管理员。
            if user.role != "admin":
                yield {"type": "error", "channel": "ops", "content": "运维诊断需要管理员权限"}
                return
            with concurrency_slot("ops:global", settings.OPS_AGENT_MAX_CONCURRENCY, settings.CONCURRENCY_COUNTER_TTL_SECONDS) as acquired:
                if not acquired:
                    yield {"type": "error", "channel": "ops", "content": "运维 Agent 当前并发已满，请稍后再试"}
                    return
                async for event in OpsAgentService(self.db).stream_chat(message, user, conversation_id=conversation_id):
                    event["channel"] = "ops"
                    yield event
            return

        # RAG 链路需要确保存在会话；没有 conversationId 时自动创建。
        service = ConversationService(self.db)
        conversation = service.get_conversation(conversation_id) if conversation_id else None
        if not conversation:
            conversation = service.create_conversation(user.id, message[:30] or "新对话")

        task_id = str(uuid.uuid4())
        with concurrency_slot(f"chat:user:{user.id}", settings.CHAT_MAX_CONCURRENCY_PER_USER, settings.CONCURRENCY_COUNTER_TTL_SECONDS) as acquired:
            if not acquired:
                yield {"type": "error", "channel": "rag", "content": "当前用户聊天并发已满，请等待上一轮回答完成"}
                return
            async for event in stream_chat(self.db, conversation.id, message, task_id, deep_thinking=deep_thinking):
                event["channel"] = "rag"
                event.setdefault("conversationId", conversation.id)
                yield event
