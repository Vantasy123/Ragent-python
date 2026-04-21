from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import User
from services.common import success
from services.dashboard_service import DashboardService
from services.dependencies import require_admin

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
