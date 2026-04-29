"""运行时状态服务：Redis 优先，本地内存降级。"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import Iterator

from app.core.config import settings
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

_local_stop_tasks: set[str] = set()
_local_counters: dict[str, tuple[int, float]] = {}
_local_lock = threading.Lock()


def _now() -> float:
    return time.time()


def _cleanup_local_counter(key: str) -> None:
    """清理过期的本地计数器，避免降级模式长期占用内存。"""

    value = _local_counters.get(key)
    if value and value[1] <= _now():
        _local_counters.pop(key, None)


class StopTaskStore:
    """聊天停止状态存储，兼容原来的 set.add/discard/in 语义。"""

    def add(self, task_id: str) -> None:
        """标记任务需要停止。"""

        if not task_id:
            return
        redis = get_redis_client()
        if redis.set(f"chat:stop:{task_id}", "1", ex=settings.CHAT_STOP_TTL_SECONDS):
            return
        _local_stop_tasks.add(task_id)

    def discard(self, task_id: str) -> None:
        """清理停止标记。"""

        if not task_id:
            return
        redis = get_redis_client()
        redis.delete(f"chat:stop:{task_id}")
        _local_stop_tasks.discard(task_id)

    def __contains__(self, task_id: object) -> bool:
        """支持 `task_id in STOP_TASKS` 的旧调用方式。"""

        if not isinstance(task_id, str) or not task_id:
            return False
        redis = get_redis_client()
        if redis.exists(f"chat:stop:{task_id}"):
            return True
        return task_id in _local_stop_tasks


STOP_TASKS = StopTaskStore()


def mark_token_revoked(jti: str, ttl_seconds: int) -> None:
    """把 JWT 撤销状态写入 Redis；失败时由 MySQL 撤销表兜底。"""

    if not jti or ttl_seconds <= 0:
        return
    redis = get_redis_client()
    redis.set(f"auth:revoked:{jti}", "1", ex=min(ttl_seconds, settings.JWT_REVOKED_TTL_SECONDS))


def is_token_revoked_cached(jti: str) -> bool:
    """优先从 Redis 判断 JWT 是否已撤销。"""

    if not jti:
        return False
    return get_redis_client().exists(f"auth:revoked:{jti}")


def remember_token_revoked(jti: str, ttl_seconds: int) -> None:
    """MySQL 命中撤销记录后回填 Redis，降低后续鉴权查表成本。"""

    mark_token_revoked(jti, ttl_seconds)


def allow_fixed_window(key: str, limit: int, window_seconds: int) -> bool:
    """固定窗口限流；Redis 不可用时使用进程内计数器降级。"""

    if limit <= 0:
        return True
    redis_key = f"rate:{key}"
    redis = get_redis_client()
    value = redis.incr_with_ttl(redis_key, window_seconds)
    if value is not None:
        return value <= limit

    with _local_lock:
        _cleanup_local_counter(redis_key)
        count, _ = _local_counters.get(redis_key, (0, _now() + window_seconds))
        if count >= limit:
            return False
        _local_counters[redis_key] = (count + 1, _now() + window_seconds)
        return True


def acquire_counter(key: str, limit: int, ttl_seconds: int) -> bool:
    """获取并发计数名额；超过上限返回 False。"""

    if limit <= 0:
        return True
    redis_key = f"concurrency:{key}"
    redis = get_redis_client()
    value = redis.incr_with_ttl(redis_key, ttl_seconds)
    if value is not None:
        if value <= limit:
            return True
        redis.decr(redis_key)
        return False

    with _local_lock:
        _cleanup_local_counter(redis_key)
        count, _ = _local_counters.get(redis_key, (0, _now() + ttl_seconds))
        if count >= limit:
            return False
        _local_counters[redis_key] = (count + 1, _now() + ttl_seconds)
        return True


def release_counter(key: str) -> None:
    """释放并发计数名额。"""

    redis_key = f"concurrency:{key}"
    redis = get_redis_client()
    value = redis.decr(redis_key)
    if value is not None:
        if value < 0:
            redis.delete(redis_key)
        return

    with _local_lock:
        _cleanup_local_counter(redis_key)
        count, expires_at = _local_counters.get(redis_key, (0, _now()))
        if count <= 1:
            _local_counters.pop(redis_key, None)
        else:
            _local_counters[redis_key] = (count - 1, expires_at)


@contextmanager
def concurrency_slot(key: str, limit: int, ttl_seconds: int) -> Iterator[bool]:
    """上下文管理器形式的并发名额，确保异常时也能释放。"""

    acquired = acquire_counter(key, limit, ttl_seconds)
    try:
        yield acquired
    finally:
        if acquired:
            release_counter(key)
