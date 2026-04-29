"""
聊天路由模块 (Chat Router Module)

本模块定义了聊天对话相关的 REST API 接口，支持流式响应和 RAG 增强生成。
实现了完整的对话生命周期管理，包括创建对话、发送消息、流式响应等。

主要功能：
1. RAG 增强聊天：结合检索和生成提供准确回答
2. 流式响应：支持实时 token 输出，提升用户体验
3. 对话管理：创建、查询、删除对话历史
4. 消息管理：添加消息、生成摘要、获取反馈
5. 任务控制：支持停止正在进行的聊天任务

核心特性：
- 异步流式处理：使用 StreamingResponse 实现实时响应
- 上下文管理：自动维护对话历史和上下文
- 错误处理：完善的异常处理和降级策略
- 性能优化：对话摘要、历史截断等优化措施

API 端点：
- GET /rag/v3/chat: RAG 增强聊天（流式）
- GET /conversations: 获取用户对话列表
- POST /conversations: 创建新对话
- DELETE /conversations/{id}: 删除对话
- GET /conversations/{id}/messages: 获取对话消息
- POST /conversations/{id}/messages: 添加消息
- POST /conversations/{id}/feedback: 提交反馈
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.domain.models import User
from app.services.chat_service import ConversationService, STOP_TASKS, stream_chat
from app.services.common import success
from app.services.dependencies import get_current_user
from app.services.runtime_state import concurrency_slot

router = APIRouter(tags=["chat"])


@router.get("/rag/v3/chat")
async def rag_chat(
    question: str,
    conversationId: str | None = None,
    deepThinking: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    service = ConversationService(db)
    conversation = service.get_conversation(conversationId) if conversationId else None
    if not conversation:
        conversation = service.create_conversation(user.id, question[:30] or "新对话")
    task_id = str(uuid.uuid4())

    async def event_stream():
        with concurrency_slot(f"chat:user:{user.id}", settings.CHAT_MAX_CONCURRENCY_PER_USER, settings.CONCURRENCY_COUNTER_TTL_SECONDS) as acquired:
            if not acquired:
                yield f"data: {json.dumps({'type': 'error', 'content': '当前用户聊天并发已满，请等待上一轮回答完成'}, ensure_ascii=False)}\n\n"
                return
            async for event in stream_chat(db, conversation.id, question, task_id, deep_thinking=deepThinking):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/rag/v3/stop")
def stop_chat(taskId: str = Query(...)):
    STOP_TASKS.add(taskId)
    return success()



