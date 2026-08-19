"""智能求职 Agent 网申自动填表与 Bridge 映射 API 路由（NowClaw 对齐）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.models import User
from app.services.dependencies import get_current_user
from app.services.job_auto_fill_service import JobAutoFillService

router = APIRouter(prefix="/jobs/autofill", tags=["Job AutoFill"])


class GeneratePayloadRequest(BaseModel):
    resume_id: str
    platform_name: str = "nowcoder"
    custom_overrides: Optional[Dict[str, Any]] = None


class SaveMappingRequest(BaseModel):
    platform_name: str
    template_name: str
    field_mappings: Dict[str, Any]
    default_values: Dict[str, Any]


@router.get("/mappings")
def list_mappings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobAutoFillService(db)
    mappings = service.get_mappings(user_id=current_user.id)
    if not mappings:
        # 初始化默认映射
        default_map = service.get_or_create_default_mapping("nowcoder")
        mappings = [default_map]
    return {
        "items": [
            {
                "id": m.id,
                "platformName": m.platform_name,
                "templateName": m.template_name,
                "fieldMappings": m.field_mappings,
                "defaultValues": m.default_values,
                "enabled": m.enabled,
                "createdAt": m.created_at.isoformat() if m.created_at else None,
            }
            for m in mappings
        ]
    }


@router.post("/payload")
def generate_payload(
    req: GeneratePayloadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobAutoFillService(db)
    payload = service.generate_form_fill_payload(
        resume_id=req.resume_id,
        platform_name=req.platform_name,
        custom_overrides=req.custom_overrides
    )
    return payload


@router.post("/mappings")
def save_mapping(
    req: SaveMappingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = JobAutoFillService(db)
    mapping = service.save_mapping_template(
        platform_name=req.platform_name,
        template_name=req.template_name,
        field_mappings=req.field_mappings,
        default_values=req.default_values,
        user_id=current_user.id
    )
    return {
        "id": mapping.id,
        "platformName": mapping.platform_name,
        "templateName": mapping.template_name,
        "message": "映射模板保存成功"
    }
