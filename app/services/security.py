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

from app.core.config import settings


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
    header = {"alg": "HS256", "typ": "JWT"}
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
    header_segment, payload_segment, signature_segment = token.split(".", 2)
    expected_signature = hmac.new(
        settings.JWT_SECRET.encode("utf-8"),
        f"{header_segment}.{payload_segment}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected_signature, _b64url_decode(signature_segment)):
        raise ValueError("Invalid token signature")
    payload = json.loads(_b64url_decode(payload_segment))
    if payload.get("exp", 0) < int(time.time()):
        raise ValueError("Token expired")
    return payload


