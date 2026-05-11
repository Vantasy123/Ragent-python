"""
对话路由模块 (Conversations Router Module)

本模块定义了对话管理相关的 REST API 接口，负责对话的 CRUD 操作。
提供对话的创建、查询、更新、删除等基础管理功能。

主要功能：
1. 对话列表：分页获取用户的对话历史
2. 对话详情：获取单个对话的详细信息
3. 对话创建：创建新的对话会话
4. 对话删除：删除指定的对话及其所有消息
5. 对话更新：修改对话标题等元数据

数据结构：
- 对话包含：ID、标题、创建时间、更新时间、用户ID
- 支持分页查询和时间排序
- 级联删除保护：删除对话时自动清理相关消息

API 端点：
- GET /conversations: 获取对话列表（分页）
- POST /conversations: 创建新对话
- GET /conversations/{id}: 获取对话详情
- PUT /conversations/{id}: 更新对话信息
- DELETE /conversations/{id}: 删除对话
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.time_utils import to_shanghai_iso
from app.domain.models import User
from app.services.chat_service import ConversationService
from app.services.common import page, success
from app.services.dependencies import get_current_user

router = APIRouter(tags=["conversations"])


class ConversationRenameRequest(BaseModel):
    """ConversationRenameRequest 请求模型：描述前端提交到接口的字段，FastAPI 会用它完成参数校验和类型转换。"""
    title: str


class FeedbackRequest(BaseModel):
    """FeedbackRequest 请求模型：描述前端提交到接口的字段，FastAPI 会用它完成参数校验和类型转换。"""
    feedback_type: str
    comment: str = ""
    reasonTags: list[str] = Field(default_factory=list)
    expectedAnswer: str = ""


@router.get("/conversations")
def list_conversations(pageNo: int = 1, pageSize: int = 10, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """list_conversations 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
    rows, total = ConversationService(db).list_conversations(user.id, pageNo, pageSize)
    items = [{"id": row.id, "title": row.title, "messageCount": row.message_count, "updatedAt": to_shanghai_iso(row.updated_at)} for row in rows]
    return success(page(items, total, pageNo, pageSize))


@router.put("/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, payload: ConversationRenameRequest, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """rename_conversation 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    row = ConversationService(db).rename_conversation(conversation_id, payload.title)
    if not row:
        raise HTTPException(status_code=404, detail="会话不存在")
    return success()


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """delete_conversation 函数：删除业务记录，并在需要时同步清理关联资源或缓存。"""
    if not ConversationService(db).delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return success()


@router.delete("/conversations/{conversation_id}/messages")
def clear_conversation_messages(conversation_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """只清空对话记录，保留会话主体数据，便于用户继续复用同一个会话。"""
    deleted = ConversationService(db).clear_messages(conversation_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return success({"deleted": deleted})


@router.get("/conversations/{conversation_id}/messages")
def list_messages(conversation_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """list_messages 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
    rows = ConversationService(db).list_messages(conversation_id)
    return success([{"id": row.id, "role": row.role, "content": row.content, "metadata": row.meta_data, "createdAt": to_shanghai_iso(row.created_at)} for row in rows])


@router.post("/conversations/messages/{message_id}/feedback")
def message_feedback(message_id: str, payload: FeedbackRequest, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """message_feedback 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    extra = {}
    if payload.reasonTags:
        extra["reasonTags"] = payload.reasonTags
    if payload.expectedAnswer:
        extra["expectedAnswer"] = payload.expectedAnswer
    comment = payload.comment
    if extra:
        comment = json.dumps({"comment": payload.comment, **extra}, ensure_ascii=False)
    row = ConversationService(db).add_feedback(message_id, payload.feedback_type, comment)
    return success({"id": row.id})



