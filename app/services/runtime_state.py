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

_local_counters: dict[str, tuple[int, float]] = {}
_local_values: dict[str, tuple[str, float]] = {}
_local_lock = threading.Lock()


def _now() -> float:
    """_now 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    return time.time()


def _cleanup_local_counter(key: str) -> None:
    """清理过期的本地计数器，避免降级模式长期占用内存。"""

    value = _local_counters.get(key)
    if value and value[1] <= _now():
        _local_counters.pop(key, None)


def _cleanup_local_value(key: str) -> None:
    """清理过期的本地临时值，避免 Redis 不可用时内存无限增长。"""

    value = _local_values.get(key)
    if value and value[1] <= _now():
        _local_values.pop(key, None)


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


def set_temporary_value(key: str, value: str, ttl_seconds: int) -> None:
    """写入带过期时间的运行时值；Redis 不可用时降级到进程内存。"""

    if not key or ttl_seconds <= 0:
        return
    redis = get_redis_client()
    if redis.set(key, value, ex=ttl_seconds):
        return
    with _local_lock:
        _local_values[key] = (value, _now() + ttl_seconds)


def get_temporary_value(key: str) -> str | None:
    """读取带过期时间的运行时值；过期或不存在时返回 None。"""

    if not key:
        return None
    redis = get_redis_client()
    value = redis.get(key)
    if value is not None:
        return value
    with _local_lock:
        _cleanup_local_value(key)
        local = _local_values.get(key)
        return local[0] if local else None


def delete_temporary_value(key: str) -> None:
    """删除运行时临时值，同时清理 Redis 和本地降级存储。"""

    if not key:
        return
    get_redis_client().delete(key)
    with _local_lock:
        _local_values.pop(key, None)
        _local_counters.pop(key, None)


def increment_temporary_counter(key: str, ttl_seconds: int) -> int:
    """自增带 TTL 的运行时计数器，适合失败次数和短期风控计数。"""

    if not key or ttl_seconds <= 0:
        return 0
    redis = get_redis_client()
    value = redis.incr_with_ttl(key, ttl_seconds)
    if value is not None:
        return value
    with _local_lock:
        _cleanup_local_counter(key)
        count, _ = _local_counters.get(key, (0, _now() + ttl_seconds))
        count += 1
        _local_counters[key] = (count, _now() + ttl_seconds)
        return count


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
