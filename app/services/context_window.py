"""对话上下文滑动窗口缓存。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from app.core.config import settings
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)


def _window_key(conversation_id: str) -> str:
    """生成对话上下文窗口的 Redis key。"""

    return f"chat:window:{conversation_id}"


def _normalize_message(role: str, content: str, created_at: Any | None = None) -> dict[str, str]:
    """只保留模型上下文需要的最小字段，避免缓存 Trace 或工具大对象。"""

    if isinstance(created_at, datetime):
        created = created_at.isoformat()
    elif created_at is None:
        created = ""
    else:
        created = str(created_at)
    return {"role": role, "content": content or "", "createdAt": created}


def _dumps(message: dict[str, str]) -> str:
    """序列化单条上下文消息。"""

    return json.dumps(message, ensure_ascii=False, separators=(",", ":"))


def _loads(raw: str) -> dict[str, str] | None:
    """解析 Redis 中的上下文消息，异常数据直接丢弃。"""

    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    role = str(data.get("role") or "")
    content = str(data.get("content") or "")
    if role not in {"user", "assistant", "system"}:
        return None
    return {"role": role, "content": content, "createdAt": str(data.get("createdAt") or "")}


class ChatContextWindow:
    """Redis 中的短期对话上下文滑动窗口。"""

    def __init__(self) -> None:
        self.redis = get_redis_client()

    def append_message(self, conversation_id: str, role: str, content: str, keep: int, created_at: Any | None = None) -> None:
        """追加消息并裁剪窗口；失败时静默降级到 MySQL 历史读取。"""

        if not conversation_id or not content:
            return
        key = _window_key(conversation_id)
        payload = _dumps(_normalize_message(role, content, created_at))
        if self.redis.rpush(key, payload) is None:
            return
        self.redis.ltrim(key, -max(keep, 1), -1)
        self.redis.expire(key, settings.CHAT_CONTEXT_TTL_SECONDS)

    def get_window(self, conversation_id: str, keep: int) -> list[dict[str, str]]:
        """读取最近窗口，Redis 不可用或 miss 时返回空列表。"""

        if not conversation_id:
            return []
        rows = self.redis.lrange(_window_key(conversation_id), -max(keep, 1), -1)
        if not rows:
            return []
        messages = [_loads(row) for row in rows]
        return [{"role": item["role"], "content": item["content"]} for item in messages if item]

    def rebuild_window(self, conversation_id: str, messages: list[Any], keep: int) -> None:
        """用 MySQL 最近消息回填 Redis 窗口。"""

        if not conversation_id:
            return
        latest = messages[-max(keep, 1) :]
        payloads = [
            _dumps(_normalize_message(item.role, item.content, getattr(item, "created_at", None)))
            for item in latest
            if getattr(item, "role", "") and getattr(item, "content", "")
        ]
        self.redis.replace_list(_window_key(conversation_id), payloads, settings.CHAT_CONTEXT_TTL_SECONDS)

    def clear_window(self, conversation_id: str) -> None:
        """删除对话上下文窗口。"""

        if not conversation_id:
            return
        self.redis.delete(_window_key(conversation_id))


context_window = ChatContextWindow()
