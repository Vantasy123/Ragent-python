"""Redis 客户端封装，提供可降级的基础操作。"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """对 redis-py 做一层安全封装，避免 Redis 异常影响主流程。"""

    def __init__(self) -> None:
        self.enabled = bool(settings.REDIS_ENABLED)
        self._client: Any | None = None
        self._available: bool | None = None

    @property
    def client(self) -> Any | None:
        """懒加载 Redis 连接；依赖缺失或连接失败时返回 None。"""

        if not self.enabled:
            return None
        if self._available is False:
            return None
        if self._client is not None:
            return self._client
        try:
            import redis

            self._client = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=settings.REDIS_SOCKET_TIMEOUT,
            )
            return self._client
        except Exception as exc:  # pragma: no cover - 依赖或配置缺失时走降级。
            self._available = False
            logger.warning("Redis 初始化失败，已降级为本地状态：%s", exc)
            return None

    def key(self, name: str) -> str:
        """统一 key 前缀，避免多个项目共享 Redis 时互相污染。"""

        return f"{settings.REDIS_KEY_PREFIX}:{name}"

    def ping(self) -> bool:
        """检查 Redis 是否可用，失败时只记录警告并降级。"""

        client = self.client
        if client is None:
            return False
        try:
            client.ping()
            self._available = True
            return True
        except Exception as exc:
            self._available = False
            logger.warning("Redis 不可用，当前请求走降级逻辑：%s", exc)
            return False

    def is_available(self) -> bool:
        """返回 Redis 可用性；首次调用会主动 ping。"""

        if self._available is None:
            return self.ping()
        return self._available

    def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> bool:
        """写入字符串值，失败返回 False。"""

        client = self.client
        if client is None:
            return False
        try:
            return bool(client.set(self.key(key), value, ex=ex, nx=nx))
        except Exception as exc:
            self._available = False
            logger.warning("Redis SET 失败：%s", exc)
            return False

    def get(self, key: str) -> str | None:
        """读取字符串值，失败返回 None。"""

        client = self.client
        if client is None:
            return None
        try:
            return client.get(self.key(key))
        except Exception as exc:
            self._available = False
            logger.warning("Redis GET 失败：%s", exc)
            return None

    def delete(self, key: str) -> bool:
        """删除 key，失败返回 False。"""

        client = self.client
        if client is None:
            return False
        try:
            return bool(client.delete(self.key(key)))
        except Exception as exc:
            self._available = False
            logger.warning("Redis DEL 失败：%s", exc)
            return False

    def expire(self, key: str, ttl_seconds: int) -> bool:
        """设置 key 过期时间，失败返回 False。"""

        client = self.client
        if client is None:
            return False
        try:
            return bool(client.expire(self.key(key), ttl_seconds))
        except Exception as exc:
            self._available = False
            logger.warning("Redis EXPIRE 失败：%s", exc)
            return False

    def exists(self, key: str) -> bool:
        """检查 key 是否存在。"""

        client = self.client
        if client is None:
            return False
        try:
            return bool(client.exists(self.key(key)))
        except Exception as exc:
            self._available = False
            logger.warning("Redis EXISTS 失败：%s", exc)
            return False

    def incr_with_ttl(self, key: str, ttl_seconds: int) -> int | None:
        """原子自增并设置 TTL，常用于限流和并发计数。"""

        client = self.client
        if client is None:
            return None
        redis_key = self.key(key)
        try:
            pipe = client.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, ttl_seconds)
            value, _ = pipe.execute()
            return int(value)
        except Exception as exc:
            self._available = False
            logger.warning("Redis INCR 失败：%s", exc)
            return None

    def decr(self, key: str) -> int | None:
        """原子递减，常用于释放并发计数。"""

        client = self.client
        if client is None:
            return None
        try:
            return int(client.decr(self.key(key)))
        except Exception as exc:
            self._available = False
            logger.warning("Redis DECR 失败：%s", exc)
            return None

    def rpush(self, key: str, *values: str) -> int | None:
        """向列表右侧追加元素，失败返回 None。"""

        if not values:
            return 0
        client = self.client
        if client is None:
            return None
        try:
            return int(client.rpush(self.key(key), *values))
        except Exception as exc:
            self._available = False
            logger.warning("Redis RPUSH 失败：%s", exc)
            return None

    def lrange(self, key: str, start: int, end: int) -> list[str] | None:
        """读取列表范围，失败返回 None。"""

        client = self.client
        if client is None:
            return None
        try:
            return list(client.lrange(self.key(key), start, end))
        except Exception as exc:
            self._available = False
            logger.warning("Redis LRANGE 失败：%s", exc)
            return None

    def ltrim(self, key: str, start: int, end: int) -> bool:
        """裁剪列表范围，失败返回 False。"""

        client = self.client
        if client is None:
            return False
        try:
            return bool(client.ltrim(self.key(key), start, end))
        except Exception as exc:
            self._available = False
            logger.warning("Redis LTRIM 失败：%s", exc)
            return False

    def replace_list(self, key: str, values: list[str], ttl_seconds: int | None = None) -> bool:
        """用一组值重建列表，适合 Redis miss 后从 MySQL 回填。"""

        client = self.client
        if client is None:
            return False
        redis_key = self.key(key)
        try:
            pipe = client.pipeline()
            pipe.delete(redis_key)
            if values:
                pipe.rpush(redis_key, *values)
            if ttl_seconds:
                pipe.expire(redis_key, ttl_seconds)
            pipe.execute()
            return True
        except Exception as exc:
            self._available = False
            logger.warning("Redis list 重建失败：%s", exc)
            return False


@lru_cache
def get_redis_client() -> RedisClient:
    """返回进程内共享 Redis 封装实例。"""

    return RedisClient()
