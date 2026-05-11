"""模块导读：本文件位于 app/core/text_sanitizer.py，属于核心基础设施。

主要职责：提供配置、数据库连接、Redis、时间、文本清洗等通用能力。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

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
