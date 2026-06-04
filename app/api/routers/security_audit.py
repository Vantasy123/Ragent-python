"""安全审计中心接口，负责记录和查询跨模块安全操作。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.time_utils import to_shanghai_iso
from app.domain.models import SecurityAuditLog, User
from app.services.common import page, success
from app.services.dependencies import require_admin

router = APIRouter(prefix="/admin/security-audit", tags=["security-audit"])

ALLOWED_SECURITY_EVENTS = {
    ("export", "export_audit_csv", "audit", "users"),
    ("export", "export_audit_csv", "audit", "settings"),
    ("export", "export_audit_csv", "audit", "ops"),
    ("export", "export_audit_csv", "audit", "events"),
}


class SecurityAuditEventPayload(BaseModel):
    """前端上报的安全审计事件，字段保持通用以覆盖导出、访问和高危查询。"""

    category: str = Field(..., min_length=1, max_length=64)
    action: str = Field(..., min_length=1, max_length=64)
    targetType: str = Field("", max_length=64)
    targetId: str = Field("", max_length=128)
    detail: dict[str, Any] = Field(default_factory=dict)


@router.post("/events")
def record_security_audit_event(payload: SecurityAuditEventPayload, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """记录管理员触发的安全动作，例如导出审计数据。"""

    _validate_security_event(payload)
    row = SecurityAuditLog(
        category=payload.category,
        action=payload.action,
        target_type=payload.targetType,
        target_id=payload.targetId,
        detail=_sanitize_detail(payload.detail),
        operator_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return success(_serialize_security_audit_log(row))


@router.get("/events")
def list_security_audit_events(
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    category: str | None = Query(None),
    action: str | None = Query(None),
    targetType: str | None = Query(None),
    targetId: str | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """分页查询安全审计事件，供安全审计中心查看导出等跨模块动作。"""

    query = db.query(SecurityAuditLog)
    normalized_category = (category or "").strip()
    normalized_action = (action or "").strip()
    normalized_target_type = (targetType or "").strip()
    normalized_target_id = (targetId or "").strip()
    if normalized_category:
        query = query.filter(SecurityAuditLog.category == normalized_category)
    if normalized_action:
        query = query.filter(SecurityAuditLog.action == normalized_action)
    if normalized_target_type:
        query = query.filter(SecurityAuditLog.target_type == normalized_target_type)
    if normalized_target_id:
        query = query.filter(SecurityAuditLog.target_id == normalized_target_id)
    total = query.count()
    rows = (
        query.order_by(SecurityAuditLog.created_at.desc(), SecurityAuditLog.id.desc())
        .offset((pageNo - 1) * pageSize)
        .limit(pageSize)
        .all()
    )
    return success(page([_serialize_security_audit_log(row) for row in rows], total, pageNo, pageSize))


def _serialize_security_audit_log(row: SecurityAuditLog) -> dict[str, Any]:
    """把安全审计 ORM 记录转换成前端字段。"""

    return {
        "id": row.id,
        "category": row.category,
        "action": row.action,
        "targetType": row.target_type,
        "targetId": row.target_id,
        "detail": row.detail or {},
        "operatorId": row.operator_id,
        "createdAt": to_shanghai_iso(row.created_at),
    }


def _validate_security_event(payload: SecurityAuditEventPayload) -> None:
    """只允许前端记录产品内定义过的安全事件，避免客户端写入任意审计噪音。"""

    event_key = (payload.category, payload.action, payload.targetType, payload.targetId)
    if event_key not in ALLOWED_SECURITY_EVENTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的安全审计事件")


def _sanitize_detail(detail: dict[str, Any]) -> dict[str, Any]:
    """导出审计只保存筛选条件和数量，不保留任何凭证或敏感明文。"""

    blocked_parts = ("password", "secret", "token", "credential", "apikey", "accesskey")
    safe: dict[str, Any] = {}
    for key, value in (detail or {}).items():
        normalized = "".join(ch for ch in str(key).lower() if ch.isalnum())
        if any(part in normalized for part in blocked_parts):
            safe[str(key)] = "<redacted>"
            continue
        safe[str(key)] = value
    return safe
