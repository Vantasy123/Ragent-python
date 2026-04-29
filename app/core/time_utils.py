"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo


# 项目统一使用东八区作为“用户可见时间”，但数据库历史数据仍兼容旧的 UTC 写入方式。
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def utc_now_naive() -> datetime:
    """返回数据库写入使用的 UTC 无时区时间。

    说明：
    - 当前 MySQL 表结构大多是 `DateTime`，没有显式时区列。
    - 为避免把历史 UTC 记录和新写入记录混成两套口径，数据库层继续写 UTC naive。
    - 对外返回和统计口径再统一转换到东八区。
    """

    return datetime.now(UTC).replace(tzinfo=None)


def shanghai_now() -> datetime:
    """返回带时区信息的东八区当前时间。"""

    return datetime.now(SHANGHAI_TZ)


def as_shanghai(dt: datetime | None) -> datetime | None:
    """把数据库中的时间统一转换成东八区时间。

    兼容策略：
    - 无时区时间：默认按“历史 UTC 写入”解释，再转东八区。
    - 有时区时间：直接转东八区。
    """

    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC).astimezone(SHANGHAI_TZ)
    return dt.astimezone(SHANGHAI_TZ)


def to_shanghai_iso(dt: datetime | None) -> str | None:
    """把时间转换成带 `+08:00` 的 ISO 字符串，供前端直接展示。"""

    local_dt = as_shanghai(dt)
    return local_dt.isoformat() if local_dt else None


def shanghai_day_utc_range(reference: datetime, days_ago: int = 0) -> tuple[datetime, datetime, str]:
    """根据东八区自然日，返回对应的 UTC 查询区间。

    返回值：
    - start_utc_naive
    - end_utc_naive
    - 东八区日期字符串，供仪表盘直接展示
    """

    local_reference = as_shanghai(reference) or shanghai_now()
    day_start_local = (local_reference - timedelta(days=days_ago)).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end_local = day_start_local + timedelta(days=1)
    start_utc = day_start_local.astimezone(UTC).replace(tzinfo=None)
    end_utc = day_end_local.astimezone(UTC).replace(tzinfo=None)
    return start_utc, end_utc, day_start_local.strftime("%Y-%m-%d")


def shanghai_time_id(prefix: str) -> str:
    """生成带东八区时间语义的业务标识。

    这里不替代主键 UUID，只用于知识库集合名之类“用户可读且需要时间语义”的字段。
    """

    return f"{prefix}_{shanghai_now().strftime('%Y%m%d%H%M%S')}"
