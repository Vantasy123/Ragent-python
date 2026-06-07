"""
认证服务模块。

负责默认管理员初始化、登录签发令牌、退出登录和令牌撤销校验。
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import time

from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models import RevokedToken, User
from app.services.runtime_state import (
    delete_temporary_value,
    get_temporary_value,
    increment_temporary_counter,
    is_token_revoked_cached,
    mark_token_revoked,
    remember_token_revoked,
    set_temporary_value,
)
from app.services.security import create_token, hash_password, validate_production_security_settings, verify_password


LOGIN_FAILURE_LIMIT = 5
LOGIN_FAILURE_WINDOW_SECONDS = 5 * 60
LOGIN_LOCK_SECONDS = 5 * 60
LOGIN_RATE_LIMIT_MESSAGE = "登录失败次数过多，请稍后再试"


class LoginRateLimitExceeded(ValueError):
    """登录失败次数超过阈值时抛出，路由层据此返回 429。"""

    def __init__(self, retry_after_seconds: int | None = None) -> None:
        """保存建议重试时间，便于 HTTP 层返回 Retry-After。"""

        super().__init__(LOGIN_RATE_LIMIT_MESSAGE)
        self.retry_after_seconds = retry_after_seconds if retry_after_seconds is not None else LOGIN_LOCK_SECONDS


def ensure_default_admin(db: Session) -> None:
    """
    确保系统里始终存在一个默认管理员账号。

    这个函数会在应用启动时执行一次。如果默认管理员已存在则直接返回，
    不会覆盖用户后来手动修改过的昵称、密码或角色。
    """
    validate_production_security_settings()

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


def login(db: Session, username: str, password: str, client_host: str | None = None) -> dict:
    """
    校验用户名密码并签发 JWT。

    登录成功后只返回前端需要的最小用户信息，不回传任何敏感字段。
    """
    identity = _login_attempt_identity(username, client_host)
    _ensure_login_not_locked(identity)
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash) or not user.is_active:
        _record_failed_login(identity)
        raise ValueError("用户名或密码错误")
    _clear_failed_login(identity)
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


def _login_attempt_identity(username: str, client_host: str | None = None) -> str:
    """生成登录风控身份键，不把原始用户名或 IP 明文写入 Redis key。"""

    normalized_user = (username or "").strip().lower() or "<blank>"
    normalized_host = (client_host or "").strip().lower() or "<unknown>"
    return hashlib.sha256(f"{normalized_user}|{normalized_host}".encode("utf-8")).hexdigest()


def _login_failed_key(identity: str) -> str:
    """返回失败次数计数 key。"""

    return f"auth:login:failed:{identity}"


def _login_lock_key(identity: str) -> str:
    """返回登录锁定 key。"""

    return f"auth:login:locked:{identity}"


def _ensure_login_not_locked(identity: str) -> None:
    """锁定期内拒绝继续校验密码，降低暴力破解成本。"""

    if get_temporary_value(_login_lock_key(identity)):
        raise LoginRateLimitExceeded()


def _record_failed_login(identity: str) -> None:
    """记录一次失败登录；达到阈值后进入短期锁定。"""

    attempts = increment_temporary_counter(_login_failed_key(identity), LOGIN_FAILURE_WINDOW_SECONDS)
    if attempts >= LOGIN_FAILURE_LIMIT:
        set_temporary_value(_login_lock_key(identity), "1", LOGIN_LOCK_SECONDS)
        raise LoginRateLimitExceeded()


def _clear_failed_login(identity: str) -> None:
    """登录成功后清理失败计数和锁定状态。"""

    delete_temporary_value(_login_failed_key(identity))
    delete_temporary_value(_login_lock_key(identity))


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
