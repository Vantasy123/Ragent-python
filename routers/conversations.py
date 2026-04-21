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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import User
from services.chat_service import ConversationService
from services.common import page, success
from services.dependencies import get_current_user

router = APIRouter(tags=["conversations"])


class ConversationRenameRequest(BaseModel):
    title: str


class FeedbackRequest(BaseModel):
    feedback_type: str
    comment: str = ""


@router.get("/conversations")
def list_conversations(pageNo: int = 1, pageSize: int = 10, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows, total = ConversationService(db).list_conversations(user.id, pageNo, pageSize)
    items = [{"id": row.id, "title": row.title, "messageCount": row.message_count, "updatedAt": row.updated_at.isoformat()} for row in rows]
    return success(page(items, total, pageNo, pageSize))


@router.put("/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, payload: ConversationRenameRequest, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    row = ConversationService(db).rename_conversation(conversation_id, payload.title)
    if not row:
        raise HTTPException(status_code=404, detail="会话不存在")
    return success()


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if not ConversationService(db).delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return success()


@router.get("/conversations/{conversation_id}/messages")
def list_messages(conversation_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = ConversationService(db).list_messages(conversation_id)
    return success([{"id": row.id, "role": row.role, "content": row.content, "metadata": row.meta_data, "createdAt": row.created_at.isoformat()} for row in rows])


@router.post("/conversations/messages/{message_id}/feedback")
def message_feedback(message_id: str, payload: FeedbackRequest, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    row = ConversationService(db).add_feedback(message_id, payload.feedback_type, payload.comment)
    return success({"id": row.id})

