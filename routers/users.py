from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import User
from services.common import page, success
from services.dependencies import get_current_user, require_admin
from services.security import hash_password

router = APIRouter(tags=["users"])


class UserCreateRequest(BaseModel):
    username: str
    nickname: str = ""
    password: str
    role: str = "user"


class UserUpdateRequest(BaseModel):
    nickname: str | None = None
    role: str | None = None
    is_active: bool | None = None


class ChangePasswordRequest(BaseModel):
    password: str


@router.get("/users")
def list_users(pageNo: int = 1, pageSize: int = 10, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    query = db.query(User).order_by(User.created_at.desc())
    total = query.count()
    rows = query.offset((pageNo - 1) * pageSize).limit(pageSize).all()
    items = [{"id": row.id, "username": row.username, "nickname": row.nickname, "role": row.role, "isActive": row.is_active} for row in rows]
    return success(page(items, total, pageNo, pageSize))


@router.post("/users")
def create_user(payload: UserCreateRequest, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    row = User(username=payload.username, nickname=payload.nickname, password_hash=hash_password(payload.password), role=payload.role)
    db.add(row)
    db.commit()
    db.refresh(row)
    return success({"id": row.id})


@router.put("/users/{user_id}")
def update_user(user_id: str, payload: UserUpdateRequest, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = db.query(User).filter(User.id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    for key, value in payload.model_dump(exclude_none=True).items():
        if key == "is_active":
            row.is_active = value
        else:
            setattr(row, key, value)
    db.commit()
    return success()


@router.delete("/users/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = db.query(User).filter(User.id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    db.delete(row)
    db.commit()
    return success()


@router.put("/user/password")
def change_password(payload: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.password_hash = hash_password(payload.password)
    db.commit()
    return success()
