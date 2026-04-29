"""
认证路由模块 (Authentication Router Module)

本模块定义了用户认证相关的 REST API 接口，包括登录、登出等功能。
使用 FastAPI 的依赖注入系统实现安全的用户认证流程。

主要功能：
1. 用户登录：验证用户名密码，返回 JWT token
2. 用户登出：撤销 token，清理会话
3. 认证中间件：通过依赖注入提供当前用户信息

安全特性：
- JWT token 认证机制
- 密码安全验证（哈希存储）
- Token 撤销列表管理
- 自动过期处理

API 端点：
- POST /auth/login: 用户登录
- POST /auth/logout: 用户登出（需要认证）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.models import User
from app.services.auth import login, logout
from app.services.common import success
from app.services.dependencies import get_current_user

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login_api(payload: LoginRequest, db: Session = Depends(get_db)):
    try:
        return success(login(db, payload.username, payload.password))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/auth/logout")
def logout_api(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    logout(db, user._token_payload)  # type: ignore[attr-defined]
    return success()


@router.get("/user/me")
def me(user: User = Depends(get_current_user)):
    return success({"id": user.id, "username": user.username, "nickname": user.nickname, "role": user.role})



