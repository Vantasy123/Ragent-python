"""开源部署配置 API，支撑初始化向导和业务服务器接入页面。"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.models import SecurityAuditLog, User
from app.services.common import success
from app.services.dependencies import require_admin
from app.services.project_config_service import ProjectConfigService

router = APIRouter(prefix="/admin/project-config", tags=["project-config"])


class ServerConfigPayload(BaseModel):
    """业务服务器配置项。"""

    id: str = ""
    name: str
    env: str = ""
    enabled: bool = True
    base_url: str = ""
    health_url: str = ""
    metrics_url: str = ""
    owner: str = ""
    tags: list[str] = Field(default_factory=list)


class ServersPayload(BaseModel):
    """业务服务器配置保存请求。"""

    servers: list[ServerConfigPayload] = Field(default_factory=list)


class ProbeTestPayload(BaseModel):
    """HTTP 探测测试请求。"""

    name: str = "临时探测"
    url: str


@router.get("/status")
def status(_: User = Depends(require_admin)):
    """返回开源化初始化状态和下一步提示。"""

    return success(ProjectConfigService().status())


@router.get("/servers")
def list_servers(_: User = Depends(require_admin)):
    """读取全部业务服务器配置。"""

    service = ProjectConfigService()
    return success({"items": service.all_servers(), "status": service.status()})


@router.put("/servers")
def save_servers(payload: ServersPayload, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """保存业务服务器配置到 config/servers.yml。"""

    service = ProjectConfigService()
    rows = [item.model_dump() for item in payload.servers]
    try:
        result = service.save_servers(rows)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _record_project_config_audit(
        db,
        user,
        "update_servers_config",
        "servers",
        {
            "total": len(rows),
            "enabled": sum(1 for item in rows if item.get("enabled", True)),
            "serverIds": [item.get("id") for item in rows if item.get("id")],
            "serverNames": [item.get("name") for item in rows if item.get("name")],
        },
    )
    return success(result, message="servers config saved")


@router.post("/probe-test")
async def probe_test(payload: ProbeTestPayload, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """按用户输入的 URL 执行一次 HTTP 探测，不写入配置文件。"""

    try:
        url = ProjectConfigService().validate_probe_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            duration_ms = int((time.time() - start_time) * 1000)
            result = {
                "status": "up" if resp.status_code < 400 else "down",
                "statusCode": resp.status_code,
                "durationMs": duration_ms,
                "url": url,
                "name": payload.name,
            }
    except Exception as exc:
        duration_ms = int((time.time() - start_time) * 1000)
        result = {
            "status": "down",
            "statusCode": None,
            "error": str(exc),
            "durationMs": duration_ms,
            "url": url,
            "name": payload.name,
        }

    _record_project_config_audit(
        db,
        user,
        "probe_test",
        "manual",
        {
            "name": payload.name,
            "url": _audit_url(url),
            "status": result.get("status"),
            "statusCode": result.get("statusCode"),
            "durationMs": result.get("durationMs"),
        },
    )
    return success(result)


def _record_project_config_audit(
    db: Session,
    user: User,
    action: str,
    target_id: str,
    detail: dict[str, Any],
) -> None:
    """记录接入配置变更审计，只保存可追溯摘要，不落敏感配置明文。"""

    row = SecurityAuditLog(
        category="config",
        action=action,
        target_type="project_config",
        target_id=target_id,
        detail=detail,
        operator_id=user.id,
    )
    db.add(row)
    db.commit()


def _audit_url(url: str) -> str:
    """审计里只保留 URL 定位信息，移除账号、查询参数和片段。"""

    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = f"{hostname}:{parsed.port}" if parsed.port else hostname
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
