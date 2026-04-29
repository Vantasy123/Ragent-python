"""
认证服务模块。

负责默认管理员初始化、登录签发令牌、退出登录和令牌撤销校验。
"""

from __future__ import annotations

from datetime import UTC, datetime
import time

from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models import RevokedToken, User
from app.services.runtime_state import is_token_revoked_cached, mark_token_revoked, remember_token_revoked
from app.services.security import create_token, hash_password, verify_password


def ensure_default_admin(db: Session) -> None:
    """
    确保系统里始终存在一个默认管理员账号。

    这个函数会在应用启动时执行一次。如果默认管理员已存在则直接返回，
    不会覆盖用户后来手动修改过的昵称、密码或角色。
    """
    admin = db.query(User).filter(User.username == settings.DEFAULT_ADMIN_USERNAME).first()
    if admin:
        return
    db.add(
        User(
            username=settings.DEFAULT_ADMIN_USERNAME,
            nickname=settings.DEFAULT_ADMIN_NICKNAME,
            password_hash=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
            role="admin",
            is_active=True,
        )
    )
    db.commit()


def login(db: Session, username: str, password: str) -> dict:
    """
    校验用户名密码并签发 JWT。

    登录成功后只返回前端需要的最小用户信息，不回传任何敏感字段。
    """
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash) or not user.is_active:
        raise ValueError("用户名或密码错误")
    token = create_token({"sub": user.id, "username": user.username, "role": user.role})
    return {
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
            "role": user.role,
        },
    }


def logout(db: Session, token_payload: dict) -> None:
    """
    撤销当前访问令牌。

    这里把 JWT 的唯一标识写入撤销表，让未过期的旧令牌也无法继续使用。
    """
    jti = token_payload["jti"]
    expires_at = datetime.fromtimestamp(token_payload["exp"], UTC).replace(tzinfo=None)
    exists = db.query(RevokedToken).filter(RevokedToken.token_id == jti).first()
    if not exists:
        db.add(
            RevokedToken(
                token_id=jti,
                # JWT 的 exp 本身是 UTC epoch，这里显式转成 UTC 再去掉 tzinfo，和数据库旧口径保持一致。
                expires_at=expires_at,
            )
        )
        db.commit()
    mark_token_revoked(jti, max(int(token_payload["exp"]) - int(time.time()), 1))


def is_token_revoked(db: Session, token_payload: dict) -> bool:
    """
    检查令牌是否已被撤销。

    一般在 JWT 验签和过期检查之后调用，用于完成服务端注销控制。
    """
    jti = token_payload["jti"]
    if is_token_revoked_cached(jti):
        return True
    token = db.query(RevokedToken).filter(RevokedToken.token_id == jti).first()
    if token is not None:
        ttl = max(int(token_payload.get("exp", 0)) - int(time.time()), 1)
        remember_token_revoked(jti, ttl)
        return True
    return False
