from __future__ import annotations

from typing import Any


def success(data: Any = None, message: str = "success") -> dict:
    return {"code": 200, "message": message, "data": data}


def page(items: list[Any], total: int, page_no: int, page_size: int) -> dict:
    return {
        "items": items,
        "total": total,
        "pageNo": page_no,
        "pageSize": page_size,
    }
