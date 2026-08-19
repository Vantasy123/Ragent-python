"""模块导读：本文件位于 app/api/routers/unified_chat.py，属于 API 路由层。

主要职责：提供统一 Agent 对话流式接口与对话附件/简历文件解析上传接口。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.models import User
from app.services.chat_file_service import ChatFileService
from app.services.dependencies import get_current_user
from app.services.unified_chat_service import UnifiedChatService

router = APIRouter(tags=["unified-chat"])


class AttachmentItem(BaseModel):
    """对话附件元数据。"""

    filename: str
    file_type: str = "TXT"
    file_size: int = 0
    char_count: int = 0
    text: str = ""
    summary: str = ""


class UnifiedChatRequest(BaseModel):
    """统一聊天请求体。"""

    message: str
    mode: Literal["auto", "rag", "job", "ops"] = "auto"
    conversationId: str | None = None
    deepThinking: bool = False
    attachments: Optional[List[AttachmentItem]] = None


@router.post("/agent/upload-file")
async def upload_chat_file(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """对话工作台附件上传与解析接口。支持 PDF、DOCX、TXT、MD 等格式。"""
    try:
        result = await ChatFileService.process_upload(file)
        return {"code": 200, "message": "success", "data": result}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"文件解析失败: {exc}")


@router.post("/agent/chat")
async def unified_chat(
    payload: UnifiedChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """统一聊天 SSE 入口。支持智能求职模式与多格式附件流式问答。"""

    attachments_data = [a.model_dump() for a in payload.attachments] if payload.attachments else None

    async def event_stream():
        async for event in UnifiedChatService(db).stream(
            payload.message,
            user,
            mode=payload.mode if payload.mode in {"auto", "rag", "job"} else "auto",
            conversation_id=payload.conversationId,
            deep_thinking=payload.deepThinking,
            attachments=attachments_data,
        ):
            # SSE 每个事件都用 data 行输出，ensure_ascii=False 保留中文诊断信息。
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
