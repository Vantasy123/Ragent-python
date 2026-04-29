"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.models import User
from app.services.common import page, success
from app.services.dependencies import require_admin
from app.services.security import hash_password

router = APIRouter(tags=["users"])


class UserPayload(BaseModel):
    username: str
    nickname: str = ""
    password: str | None = None
    role: str = "user"
    is_active: bool = True


@router.get("/users")
def list_users(
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = db.query(User).order_by(User.created_at.desc())
    total = query.count()
    rows = query.offset((pageNo - 1) * pageSize).limit(pageSize).all()
    items = [
        {
            "id": row.id,
            "username": row.username,
            "nickname": row.nickname,
            "role": row.role,
            "isActive": row.is_active,
        }
        for row in rows
    ]
    return success(page(items, total, pageNo, pageSize))


@router.post("/users")
def create_user(payload: UserPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    row = User(
        username=payload.username,
        nickname=payload.nickname,
        password_hash=hash_password(payload.password or "123456"),
        role=payload.role,
        is_active=payload.is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return success({"id": row.id})


@router.put("/users/{user_id}")
def update_user(user_id: str, payload: UserPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = db.query(User).filter(User.id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    row.nickname = payload.nickname
    row.role = payload.role
    row.is_active = payload.is_active
    if payload.password:
        row.password_hash = hash_password(payload.password)
    db.commit()
    return success({"id": row.id})


@router.delete("/users/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = db.query(User).filter(User.id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    db.delete(row)
    db.commit()
    return success()
