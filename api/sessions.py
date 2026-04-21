"""
会话管理 API
提供会话 CRUD 和消息历史查询
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from database import get_db
from memory.session_manager import SessionManager
from models import ChatSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


# ==================== Pydantic 模型 ====================

class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    user_id: Optional[str] = None
    title: str = "新对话"


class AddMessageRequest(BaseModel):
    """添加消息请求"""
    role: str  # user/assistant/system
    content: str
    metadata: Optional[dict] = None


class SessionResponse(BaseModel):
    """会话响应"""
    id: str
    user_id: Optional[str]
    title: str
    message_count: int
    created_at: str
    
    class Config:
        from_attributes = True


# ==================== API 端点 ====================

@router.post("", response_model=dict)
def create_session(
    request: CreateSessionRequest,
    db: Session = Depends(get_db)
):
    """创建新会话"""
    try:
        session_mgr = SessionManager(db)
        session_id = session_mgr.create_session(
            user_id=request.user_id,
            title=request.title
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": {"session_id": session_id}
        }
    except Exception as e:
        logger.error(f"Failed to create session: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}", response_model=dict)
def get_session(session_id: str, db: Session = Depends(get_db)):
    """获取会话详情"""
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "code": 200,
        "message": "success",
        "data": session
    }


@router.get("/{session_id}/messages", response_model=dict)
def get_session_messages(
    session_id: str,
    max_rounds: int = 10,
    db: Session = Depends(get_db)
):
    """获取会话消息历史"""
    session_mgr = SessionManager(db)
    
    # 验证会话存在
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    history = session_mgr.get_chat_history(session_id, max_rounds=max_rounds)
    
    return {
        "code": 200,
        "message": "success",
        "data": {
            "session_id": session_id,
            "messages": history
        }
    }


@router.post("/{session_id}/messages", response_model=dict)
def add_message(
    session_id: str,
    request: AddMessageRequest,
    db: Session = Depends(get_db)
):
    """添加消息到会话"""
    session_mgr = SessionManager(db)
    
    # 验证会话存在
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session_mgr.add_message(
        session_id=session_id,
        role=request.role,
        content=request.content,
        metadata=request.metadata
    )
    
    return {
        "code": 200,
        "message": "success"
    }


@router.delete("/{session_id}", response_model=dict)
def delete_session(session_id: str, db: Session = Depends(get_db)):
    """删除会话"""
    session_mgr = SessionManager(db)
    
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session_mgr.delete_session(session_id)
    
    return {
        "code": 200,
        "message": "success"
    }


@router.post("/{session_id}/clear", response_model=dict)
def clear_session(session_id: str, db: Session = Depends(get_db)):
    """清空会话历史"""
    session_mgr = SessionManager(db)
    
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session_mgr.clear_session(session_id)
    
    return {
        "code": 200,
        "message": "success"
    }
