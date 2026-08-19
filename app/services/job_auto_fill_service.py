"""智能求职 Agent 网申自动填表与表单映射服务（对齐 NowClaw Bridge 架构）：负责字段映射、Payload 拼装与网申自动化。"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.domain.models import ApplicationFormMapping, ResumeProfile
from app.infrastructure.model_router import ModelRouter

logger = logging.getLogger(__name__)

DEFAULT_NOWCODER_MAPPING = {
    "basic.name": "basic_info.name",
    "basic.gender": "basic_info.gender",
    "basic.mobile": "basic_info.phone",
    "basic.email": "basic_info.email",
    "basic.currentCity": "basic_info.current_city",
    "basic.targetCity": "basic_info.target_city",
    "basic.education": "basic_info.education_level",
    "basic.targetRole": "basic_info.target_role",
    "basic.salary": "basic_info.expected_salary",
    "basic.summary": "basic_info.summary",
    "educations": "educations",
    "works": "work_experiences",
    "projects": "project_experiences",
    "skills": "skills",
    "certificates": "certificates"
}


class JobAutoFillService:
    def __init__(self, db: Session, model_router: Optional[ModelRouter] = None):
        self.db = db
        self.model_router = model_router or ModelRouter()

    def get_mappings(self, user_id: Optional[str] = None) -> List[ApplicationFormMapping]:
        query = self.db.query(ApplicationFormMapping).filter(ApplicationFormMapping.enabled == True)
        if user_id:
            query = query.filter((ApplicationFormMapping.user_id == user_id) | (ApplicationFormMapping.user_id == None))
        return query.all()

    def get_or_create_default_mapping(self, platform_name: str = "nowcoder") -> ApplicationFormMapping:
        mapping = self.db.query(ApplicationFormMapping).filter(
            ApplicationFormMapping.platform_name == platform_name
        ).first()
        if not mapping:
            mapping = ApplicationFormMapping(
                platform_name=platform_name,
                template_name=f"{platform_name.capitalize()} 网申标准映射模板",
                field_mappings=DEFAULT_NOWCODER_MAPPING,
                default_values={
                    "available_time": "随时到岗",
                    "political_status": "群众",
                    "marital_status": "未婚"
                },
                enabled=True
            )
            self.db.add(mapping)
            self.db.commit()
            self.db.refresh(mapping)
        return mapping

    def generate_form_fill_payload(
        self,
        resume_id: str,
        platform_name: str = "nowcoder",
        custom_overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """将结构化简历数据根据平台字段映射规则拼装为网申自动填表所需的标准 JSON 数据。"""
        resume = self.db.query(ResumeProfile).filter(ResumeProfile.id == resume_id).first()
        if not resume:
            raise ValueError(f"Resume {resume_id} not found")

        mapping = self.get_or_create_default_mapping(platform_name)
        data = resume.parsed_data or {}
        basic = data.get("basic_info", {})

        payload = {
            "platform": platform_name,
            "version": "1.0.0",
            "resume_id": resume.id,
            "profile_name": resume.name,
            "form_fields": {
                "name": basic.get("name", ""),
                "gender": basic.get("gender", ""),
                "phone": basic.get("phone", ""),
                "email": basic.get("email", ""),
                "current_city": basic.get("current_city", ""),
                "target_city": basic.get("target_city", ""),
                "education_level": basic.get("education_level", ""),
                "target_role": basic.get("target_role", ""),
                "expected_salary": basic.get("expected_salary", ""),
                "self_summary": basic.get("summary", ""),
                "educations": data.get("educations", []),
                "work_experiences": data.get("work_experiences", []),
                "project_experiences": data.get("project_experiences", []),
                "skills": data.get("skills", []),
                "certificates": data.get("certificates", []),
                "highlights": data.get("highlights", [])
            },
            "default_options": mapping.default_values or {},
            "bridge_contract": {
                "topics": ["fill.state", "fill.submit"],
                "target_origin": f"https://www.{platform_name}.com"
            }
        }

        if custom_overrides:
            payload["form_fields"].update(custom_overrides)

        return payload

    def save_mapping_template(
        self,
        platform_name: str,
        template_name: str,
        field_mappings: Dict[str, Any],
        default_values: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> ApplicationFormMapping:
        mapping = ApplicationFormMapping(
            user_id=user_id,
            platform_name=platform_name,
            template_name=template_name,
            field_mappings=field_mappings,
            default_values=default_values,
            enabled=True
        )
        self.db.add(mapping)
        self.db.commit()
        self.db.refresh(mapping)
        return mapping
