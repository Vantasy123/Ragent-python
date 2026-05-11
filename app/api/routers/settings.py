"""模块导读：本文件位于 app/api/routers/settings.py，属于API 路由层。

主要职责：把 HTTP 请求转换成服务层调用，并把结果整理成前端可以直接使用的响应。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.models import User
from app.services.common import success
from app.services.dependencies import require_admin
from app.services.settings_service import build_settings_payload, update_settings

router = APIRouter(tags=["settings"])


@router.get("/rag/settings")
def rag_settings(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    """rag_settings 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    return success(build_settings_payload(db))


@router.put("/rag/settings")
def update_rag_settings(
    payload: dict[str, Any],
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """update_rag_settings 函数：更新已有业务记录，只修改调用方明确传入的字段。"""
    return success(update_settings(db, user, payload), message="settings updated")


