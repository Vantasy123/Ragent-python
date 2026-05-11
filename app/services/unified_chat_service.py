"""模块导读：本文件位于 app/services/unified_chat_service.py，属于服务层。

主要职责：承接路由层请求，组织数据库、缓存、Trace、Agent 和外部组件完成业务流程。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

import uuid
from typing import AsyncIterator, Literal

from langchain_core.messages import HumanMessage
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models import User
from app.rag.workflow import build_primary_llm
from app.services.chat_service import ConversationService, stream_chat
from app.services.ops_agent_service import OpsAgentService
from app.services.runtime_state import concurrency_slot

ChatMode = Literal["auto", "rag", "ops"]


# 自动路由兜底关键词。LLM 判定失败时，auto 模式会回退到这套规则。
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


ROUTE_CLASSIFIER_PROMPT = """你是 Ragent 的聊天入口路由器，需要判断用户消息应该进入哪个通道。

可选通道：
- ops：用户要排查、观察或处理本系统/服务的运维问题，例如容器、日志、健康检查、端口、数据库连接、服务异常、重启、部署、接口 502、前后端代理等。
- rag：普通知识问答、文档问答、概念解释、代码解释、写作、方案咨询，或只是询问运维概念但不要求检查/操作当前系统。

只输出一个小写单词：ops 或 rag。不要输出解释。

用户消息：
{message}
"""


def _resolve_chat_mode_by_keywords(message: str, mode: ChatMode) -> Literal["rag", "ops"]:
    """使用关键词规则兜底选择底层通道。"""

    if mode != "auto":
        return mode
    lowered = message.lower()
    return "ops" if any(keyword in lowered or keyword in message for keyword in OPS_KEYWORDS) else "rag"


async def resolve_chat_mode(message: str, mode: ChatMode) -> Literal["rag", "ops"]:
    """根据用户指定模式或 LLM 意图判定选择底层通道。"""

    if mode != "auto":
        return mode

    try:
        # 路由判定使用非流式主模型，避免占用聊天输出流。
        llm = build_primary_llm(streaming=False)
        response = await llm.ainvoke([HumanMessage(content=ROUTE_CLASSIFIER_PROMPT.format(message=message))])
        channel = str(getattr(response, "content", "")).strip().lower()
        if channel in {"rag", "ops"}:
            return channel
    except Exception:
        pass

    return _resolve_chat_mode_by_keywords(message, mode)


class UnifiedChatService:
    """统一聊天入口服务。

    前端只需要调用 /agent/chat：
    - 普通知识问答走 RAG 链路。
    - 运维问题走多 Agent 诊断链路。
    - auto 模式优先由 LLM 判断路由，失败时回退到关键词规则。
    """

    def __init__(self, db: Session):
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
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

        channel = await resolve_chat_mode(message, mode)

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
