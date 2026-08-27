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

import httpx
from app.core.config import settings

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
    model: Optional[str] = None


PRESET_MODELS = [
    {
        "id": "Qwen/Qwen2.5-14B-Instruct",
        "name": "Qwen 2.5 14B",
        "provider": "阿里通义",
        "category": "qwen",
        "tag": "官方推荐",
        "description": "求职对话与简历润色综合推荐，响应迅速，逻辑严密",
        "pricingTag": "约 ¥0.002 / 千Token",
        "inputPrice": 0.002,
        "outputPrice": 0.004,
        "isRecommended": True,
    },
    {
        "id": "deepseek-ai/DeepSeek-R1",
        "name": "DeepSeek R1",
        "provider": "DeepSeek",
        "category": "deepseek",
        "tag": "深度推理",
        "description": "具备超强思维链推理能力，擅长高难度技术模拟面试与复杂 STAR 挖掘",
        "pricingTag": "约 ¥0.004 / 千Token",
        "inputPrice": 0.004,
        "outputPrice": 0.016,
        "isRecommended": True,
    },
    {
        "id": "deepseek-ai/DeepSeek-V3",
        "name": "DeepSeek V3",
        "provider": "DeepSeek",
        "category": "deepseek",
        "tag": "高性价比",
        "description": "满血 671B MoE 架构，极速响应，综合问答与通用能力兼备",
        "pricingTag": "约 ¥0.002 / 千Token",
        "inputPrice": 0.002,
        "outputPrice": 0.008,
        "isRecommended": True,
    },
    {
        "id": "deepseek-ai/DeepSeek-V3.2",
        "name": "DeepSeek V3.2",
        "provider": "DeepSeek",
        "category": "deepseek",
        "tag": "新一代MoE",
        "description": "新一代优化架构，文本生成更流畅、代码与结构化输出能力更强",
        "pricingTag": "约 ¥0.002 / 千Token",
        "inputPrice": 0.002,
        "outputPrice": 0.008,
        "isRecommended": False,
    },
    {
        "id": "Qwen/Qwen2.5-72B-Instruct",
        "name": "Qwen 2.5 72B",
        "provider": "阿里通义",
        "category": "qwen",
        "tag": "旗舰性能",
        "description": "千问旗舰超大规模模型，长上下文理解与知识储备极全面",
        "pricingTag": "约 ¥0.004 / 千Token",
        "inputPrice": 0.004,
        "outputPrice": 0.012,
        "isRecommended": True,
    },
    {
        "id": "Qwen/Qwen2.5-32B-Instruct",
        "name": "Qwen 2.5 32B",
        "provider": "阿里通义",
        "category": "qwen",
        "tag": "平衡高效",
        "description": "兼顾高精度与低时延，适合高频交互求职辅导",
        "pricingTag": "约 ¥0.0025 / 千Token",
        "inputPrice": 0.0025,
        "outputPrice": 0.005,
        "isRecommended": False,
    },
    {
        "id": "Qwen/Qwen2.5-7B-Instruct",
        "name": "Qwen 2.5 7B",
        "provider": "阿里通义",
        "category": "qwen",
        "tag": "极速轻量",
        "description": "轻量级高频模型，超低延迟响应",
        "pricingTag": "约 ¥0.001 / 千Token",
        "inputPrice": 0.001,
        "outputPrice": 0.002,
        "isRecommended": False,
    },
    {
        "id": "zai-org/GLM-5.2",
        "name": "GLM 5.2",
        "provider": "智谱AI",
        "category": "glm",
        "tag": "智谱旗舰",
        "description": "智谱新一代基座大模型，逻辑推理与 Agent 任务编排表现出众",
        "pricingTag": "约 ¥0.003 / 千Token",
        "inputPrice": 0.003,
        "outputPrice": 0.008,
        "isRecommended": False,
    },
    {
        "id": "zai-org/GLM-4.5-Air",
        "name": "GLM 4.5 Air",
        "provider": "智谱AI",
        "category": "glm",
        "tag": "极速高性价",
        "description": "轻量高效版智谱模型，适合快速问答与轻量任务",
        "pricingTag": "约 ¥0.001 / 千Token",
        "inputPrice": 0.001,
        "outputPrice": 0.002,
        "isRecommended": False,
    },
    {
        "id": "Pro/moonshotai/Kimi-K2.6",
        "name": "Kimi K2.6",
        "provider": "月之暗面",
        "category": "kimi",
        "tag": "长文专家",
        "description": "超长上下文专家模型，适合解析长篇招聘 JD 和详实工作经历",
        "pricingTag": "约 ¥0.003 / 千Token",
        "inputPrice": 0.003,
        "outputPrice": 0.008,
        "isRecommended": False,
    },
    {
        "id": "moonshotai/Kimi-K2.7-Code",
        "name": "Kimi K2.7 Code",
        "provider": "月之暗面",
        "category": "kimi",
        "tag": "代码专家",
        "description": "专为技术面试、编程题考核与代码项目拆解优化",
        "pricingTag": "约 ¥0.003 / 千Token",
        "inputPrice": 0.003,
        "outputPrice": 0.008,
        "isRecommended": False,
    },
]


@router.get("/agent/models")
async def list_available_models(
    user: User = Depends(get_current_user),
):
    """获取系统支持的大模型列表、计费单价及当前默认模型配置。"""
    default_model = getattr(settings, "CHAT_MODEL", "Qwen/Qwen2.5-14B-Instruct")
    models = [dict(m) for m in PRESET_MODELS]

    for item in models:
        item["isDefault"] = (item["id"] == default_model)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "currentDefault": default_model,
            "models": models,
        },
    }


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
    """统一聊天 SSE 入口。支持智能求职模式、多模型动态选择与多格式附件流式问答。"""

    attachments_data = [a.model_dump() for a in payload.attachments] if payload.attachments else None

    async def event_stream():
        async for event in UnifiedChatService(db).stream(
            payload.message,
            user,
            mode=payload.mode if payload.mode in {"auto", "rag", "job"} else "auto",
            conversation_id=payload.conversationId,
            deep_thinking=payload.deepThinking,
            attachments=attachments_data,
            model=payload.model,
        ):
            # SSE 每个事件都用 data 行输出，ensure_ascii=False 保留中文诊断信息。
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
