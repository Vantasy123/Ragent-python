from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import User
from services.common import success
from services.dependencies import require_admin
from services.settings_service import build_settings_payload, update_settings

router = APIRouter(tags=["settings"])


@router.get("/rag/settings")
def rag_settings(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return success(build_settings_payload(db))


@router.put("/rag/settings")
def update_rag_settings(
    payload: dict[str, Any],
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return success(update_settings(db, user, payload), message="settings updated")
