"""模块导读：本文件位于 app/core/text_sanitizer.py，属于核心基础设施。

主要职责：提供配置、数据库连接、Redis、时间、文本清洗等通用能力。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


REDACTED_VALUE = "<redacted>"
SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "apikey",
    "apiKey",
    "accesskey",
    "authorization",
    "credential",
    "privatekey",
    "refresh",
)
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|authorization)\s*=\s*([^&\s]+)"
)
AUTH_HEADER_RE = re.compile(r"(?i)\b(authorization\s*:\s*(?:bearer|basic)\s+)[^\s,;]+")
URL_RE = re.compile(r"https?://[^\s,;'\"\)]+")


def sanitize_text(value: str | None) -> str:
    """清理数据库文本字段中的 NUL 字节和非法控制字符。"""

    if not value:
        return ""
    cleaned = str(value).replace("\x00", "")
    return "".join(ch for ch in cleaned if ch in "\n\r\t" or ord(ch) >= 32)


def sanitize_payload(value: Any) -> Any:
    """递归清理即将写入 JSON/metadata 的文本内容。"""

    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, dict):
        return {sanitize_text(str(key)): sanitize_payload(item) for key, item in value.items()}
    return value


def redact_sensitive_payload(value: Any) -> Any:
    """递归清理并遮蔽即将进入审计、Trace 或工具记录的敏感字段。"""

    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, list):
        return [redact_sensitive_payload(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive_payload(item) for item in value]
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            safe_key = sanitize_text(str(key))
            if _is_sensitive_key(safe_key):
                safe[safe_key] = REDACTED_VALUE
            else:
                safe[safe_key] = redact_sensitive_payload(item)
        return safe
    return value


def redact_sensitive_text(value: str | None) -> str:
    """遮蔽文本中的常见凭证片段，保留足够上下文用于排障。"""

    cleaned = sanitize_text(value)
    if not cleaned:
        return ""
    redacted = AUTH_HEADER_RE.sub(lambda match: f"{match.group(1)}{REDACTED_VALUE}", cleaned)
    redacted = SENSITIVE_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}={REDACTED_VALUE}", redacted)
    redacted = URL_RE.sub(lambda match: _redact_url(match.group(0)), redacted)
    return _redact_url(redacted)


def _is_sensitive_key(key: str) -> bool:
    """按归一化后的键名判断是否属于敏感字段。"""

    normalized = "".join(ch for ch in key.lower() if ch.isalnum())
    return any(part.lower() in normalized for part in SENSITIVE_KEY_PARTS)


def _redact_url(value: str) -> str:
    """遮蔽 URL 中的用户名、密码和敏感查询参数。"""

    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if not parsed.scheme or not parsed.netloc:
        return value

    netloc = parsed.netloc
    if "@" in netloc:
        host = netloc.rsplit("@", 1)[1]
        netloc = f"{REDACTED_VALUE}@{host}"

    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    if query_items:
        query_items = [
            (key, REDACTED_VALUE if _is_sensitive_key(key) else item)
            for key, item in query_items
        ]
    return urlunsplit((parsed.scheme, netloc, parsed.path, urlencode(query_items), parsed.fragment))
