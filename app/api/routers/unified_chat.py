"""模块导读：本文件位于 app/api/routers/unified_chat.py，属于API 路由层。

主要职责：把 HTTP 请求转换成服务层调用，并把结果整理成前端可以直接使用的响应。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.models import User
from app.services.dependencies import get_current_user
from app.services.unified_chat_service import UnifiedChatService

router = APIRouter(tags=["unified-chat"])


class UnifiedChatRequest(BaseModel):
    """统一聊天请求体。"""

    message: str
    mode: Literal["auto", "rag", "ops"] = "auto"
    conversationId: str | None = None
    deepThinking: bool = False


@router.post("/agent/chat")
async def unified_chat(payload: UnifiedChatRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """统一聊天 SSE 入口。

    该接口屏蔽底层差异：
    - RAG 通道返回 token/done/error。
    - Ops 通道返回 Agent 计划、工具调用、观察、审批和报告。
    """

    async def event_stream():
        """event_stream 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        async for event in UnifiedChatService(db).stream(
            payload.message,
            user,
            mode=payload.mode,
            conversation_id=payload.conversationId,
            deep_thinking=payload.deepThinking,
        ):
            # SSE 每个事件都用 data 行输出，ensure_ascii=False 保留中文诊断信息。
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
