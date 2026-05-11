"""模块导读：本文件位于 app/services/common.py，属于服务层。

主要职责：承接路由层请求，组织数据库、缓存、Trace、Agent 和外部组件完成业务流程。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

from typing import Any


def success(data: Any = None, message: str = "success") -> dict:
    """success 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    return {"code": 200, "message": message, "data": data}


def page(items: list[Any], total: int, page_no: int, page_size: int) -> dict:
    """page 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    return {
        "items": items,
        "total": total,
        "pageNo": page_no,
        "pageSize": page_size,
    }


