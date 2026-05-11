"""模块导读：本文件位于 app/services/dependencies.py，属于服务层。

主要职责：承接路由层请求，组织数据库、缓存、Trace、Agent 和外部组件完成业务流程。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.domain.models import User
from app.services.auth import is_token_revoked
from app.services.runtime_state import allow_fixed_window
from app.services.security import decode_token


def get_current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    """解析 Bearer Token 并返回当前用户。"""

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态无效") from exc
    if is_token_revoked(db, payload):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效")
    if settings.RATE_LIMIT_ENABLED:
        allowed = allow_fixed_window(
            f"user:{payload.get('sub')}",
            settings.RATE_LIMIT_PER_MINUTE,
            60,
        )
        if not allowed:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="请求过于频繁，请稍后再试")
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已停用")
    user._token_payload = payload  # type: ignore[attr-defined]
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """后台接口统一要求管理员角色。"""

    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user
