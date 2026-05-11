"""模块导读：本文件位于 app/api/routers/users.py，属于API 路由层。

主要职责：把 HTTP 请求转换成服务层调用，并把结果整理成前端可以直接使用的响应。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

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
    """UserPayload 请求模型：描述前端提交到接口的字段，FastAPI 会用它完成参数校验和类型转换。"""
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
    """list_users 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
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
    """create_user 函数：创建新的业务记录，负责组织入库字段并返回创建后的结果。"""
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
    """update_user 函数：更新已有业务记录，只修改调用方明确传入的字段。"""
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
    """delete_user 函数：删除业务记录，并在需要时同步清理关联资源或缓存。"""
    row = db.query(User).filter(User.id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    db.delete(row)
    db.commit()
    return success()
