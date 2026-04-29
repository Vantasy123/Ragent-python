"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

from typing import Any


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
