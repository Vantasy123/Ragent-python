"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

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
    return success(DashboardService(db).overview())


@router.get("/performance")
def performance(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return success(DashboardService(db).performance())


@router.get("/trends")
def trends(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return success(DashboardService(db).trends())


