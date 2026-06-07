"""模块导读：本文件位于 app/services/security.py，属于服务层。

主要职责：承接路由层请求，组织数据库、缓存、Trace、Agent 和外部组件完成业务流程。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any
from urllib.parse import urlparse

from app.core.config import settings


WEAK_JWT_SECRETS = {
    "",
    "ragent-python-secret",
    "please-change-this-secret",
    "replace-with-at-least-32-random-characters",
}
WEAK_ADMIN_PASSWORDS = {
    "",
    "admin",
    "admin123",
    "password",
    "123456",
    "replace-with-a-strong-admin-password",
}
MIN_PRODUCTION_JWT_SECRET_LENGTH = 32
MIN_PRODUCTION_ADMIN_PASSWORD_LENGTH = 12
SUPPORTED_JWT_ALGORITHM = "HS256"
SUPPORTED_JWT_TYPE = "JWT"
DEVELOPMENT_CORS_HOSTS = {"localhost", "127.0.0.1", "::1", "frontend"}


def is_production_environment() -> bool:
    """判断当前是否属于生产环境，用于启用更严格的安全门禁。"""

    environment = str(settings.ENVIRONMENT or "").strip().lower()
    debug_enabled = str(settings.DEBUG or "").strip().lower() in {"1", "true", "yes", "on"}
    return environment in {"prod", "production"} and not debug_enabled


def validate_production_security_settings() -> None:
    """生产环境启动前检查关键凭证，避免弱默认配置被带到线上。"""

    if not is_production_environment():
        return

    problems: list[str] = []
    jwt_secret = str(settings.JWT_SECRET or "")
    admin_password = str(settings.DEFAULT_ADMIN_PASSWORD or "")
    allowed_origins = list(settings.ALLOWED_ORIGINS or [])

    if jwt_secret in WEAK_JWT_SECRETS:
        problems.append("JWT_SECRET 仍使用默认值或占位值")
    if len(jwt_secret) < MIN_PRODUCTION_JWT_SECRET_LENGTH:
        problems.append(f"JWT_SECRET 长度必须至少 {MIN_PRODUCTION_JWT_SECRET_LENGTH} 个字符")
    if admin_password in WEAK_ADMIN_PASSWORDS:
        problems.append("DEFAULT_ADMIN_PASSWORD 仍使用默认弱密码")
    if len(admin_password) < MIN_PRODUCTION_ADMIN_PASSWORD_LENGTH:
        problems.append(f"DEFAULT_ADMIN_PASSWORD 长度必须至少 {MIN_PRODUCTION_ADMIN_PASSWORD_LENGTH} 个字符")
    cors_problems = _production_cors_problems(allowed_origins)
    if cors_problems:
        problems.append("ALLOWED_ORIGINS 生产环境不合规：" + "，".join(cors_problems))

    if problems:
        raise RuntimeError("生产安全配置不合规：" + "；".join(problems))


def _production_cors_problems(allowed_origins: list[str]) -> list[str]:
    """检查生产 CORS 来源，避免把本地开发来源或通配符带到线上。"""

    problems: list[str] = []
    for origin in allowed_origins:
        normalized = str(origin or "").strip()
        if not normalized:
            continue
        if normalized == "*":
            problems.append("不能使用通配符 *")
            continue
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            problems.append(f"{normalized} 不是合法 HTTP(S) 来源")
            continue
        hostname = (parsed.hostname or "").lower()
        if hostname in DEVELOPMENT_CORS_HOSTS:
            problems.append(f"{normalized} 是开发或容器内部来源")
            continue
        if parsed.scheme != "https":
            problems.append(f"{normalized} 必须使用 HTTPS")
    return problems


def hash_password(password: str, salt: str | None = None) -> str:
    """hash_password 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    salt = salt or base64.urlsafe_b64encode(os.urandom(16)).decode("utf-8")
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${base64.urlsafe_b64encode(digest).decode('utf-8')}"


def verify_password(password: str, password_hash: str) -> bool:
    """verify_password 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    salt, expected = password_hash.split("$", 1)
    candidate = hash_password(password, salt)
    return hmac.compare_digest(candidate, f"{salt}${expected}")


def _b64url_encode(data: bytes) -> str:
    """_b64url_encode 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _b64url_decode(data: str) -> bytes:
    """_b64url_decode 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(payload: dict[str, Any], expires_in_minutes: int | None = None) -> str:
    """create_token 函数：创建新的业务记录，负责组织入库字段并返回创建后的结果。"""
    header = {"alg": SUPPORTED_JWT_ALGORITHM, "typ": SUPPORTED_JWT_TYPE}
    now = int(time.time())
    payload = payload.copy()
    payload["iat"] = now
    payload["exp"] = now + 60 * (expires_in_minutes or settings.JWT_EXPIRE_MINUTES)
    payload["jti"] = payload.get("jti") or str(uuid.uuid4())
    header_segment = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_segment = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        settings.JWT_SECRET.encode("utf-8"),
        f"{header_segment}.{payload_segment}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{header_segment}.{payload_segment}.{_b64url_encode(signature)}"


def decode_token(token: str) -> dict[str, Any]:
    """decode_token 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    segments = token.split(".")
    if len(segments) != 3 or any(not segment for segment in segments):
        raise ValueError("Malformed token")

    header_segment, payload_segment, signature_segment = segments
    header = _decode_json_object(header_segment, "header")
    if header.get("alg") != SUPPORTED_JWT_ALGORITHM:
        raise ValueError("Unsupported token algorithm")
    if header.get("typ") != SUPPORTED_JWT_TYPE:
        raise ValueError("Unsupported token type")

    expected_signature = hmac.new(
        settings.JWT_SECRET.encode("utf-8"),
        f"{header_segment}.{payload_segment}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    try:
        actual_signature = _b64url_decode(signature_segment)
    except Exception as exc:
        raise ValueError("Invalid token signature") from exc
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise ValueError("Invalid token signature")

    payload = _decode_json_object(payload_segment, "payload")
    exp = payload.get("exp")
    if not isinstance(exp, int):
        raise ValueError("Token missing exp")
    if not payload.get("jti"):
        raise ValueError("Token missing jti")
    if exp < int(time.time()):
        raise ValueError("Token expired")
    return payload


def _decode_json_object(segment: str, name: str) -> dict[str, Any]:
    """解码 JWT JSON 片段，并确保结果是对象而不是数组或标量。"""

    try:
        value = json.loads(_b64url_decode(segment))
    except Exception as exc:
        raise ValueError(f"Invalid token {name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Invalid token {name}")
    return value


