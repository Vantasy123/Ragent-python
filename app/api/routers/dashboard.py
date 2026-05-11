"""模块导读：本文件位于 app/api/routers/dashboard.py，属于API 路由层。

主要职责：把 HTTP 请求转换成服务层调用，并把结果整理成前端可以直接使用的响应。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.models import User
from app.services.common import success
from app.services.dashboard_service import DashboardService
from app.services.dependencies import require_admin

router = APIRouter(prefix="/admin/dashboard", tags=["dashboard"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """overview 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
    return success(DashboardService(db).overview())


@router.get("/performance")
def performance(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """performance 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
    return success(DashboardService(db).performance())


@router.get("/trends")
def trends(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """trends 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
    return success(DashboardService(db).trends())


