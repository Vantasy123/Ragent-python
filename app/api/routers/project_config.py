"""开源部署配置 API，支撑初始化向导和业务服务器接入页面。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.domain.models import User
from app.services.common import success
from app.services.dependencies import require_admin
from app.services.monitoring_service import MonitoringService
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


class MonitoringPayload(BaseModel):
    """监控配置保存请求。"""

    monitoring: dict[str, Any] = Field(default_factory=dict)
    probes: list[dict[str, Any]] = Field(default_factory=list)


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
def save_servers(payload: ServersPayload, _: User = Depends(require_admin)):
    """保存业务服务器配置到 config/servers.yml。"""

    service = ProjectConfigService()
    rows = [item.model_dump() for item in payload.servers]
    try:
        return success(service.save_servers(rows), message="servers config saved")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/monitoring")
def get_monitoring(_: User = Depends(require_admin)):
    """读取监控配置和额外探测目标。"""

    service = ProjectConfigService()
    return success({"monitoring": service.monitoring(), "status": service.status()})


@router.put("/monitoring")
def save_monitoring(payload: MonitoringPayload, _: User = Depends(require_admin)):
    """保存监控配置到 config/monitoring.yml。"""

    service = ProjectConfigService()
    try:
        return success(service.save_monitoring(payload.monitoring, payload.probes), message="monitoring config saved")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/probe-test")
async def probe_test(payload: ProbeTestPayload, _: User = Depends(require_admin)):
    """按用户输入的 URL 执行一次 HTTP 探测，不写入配置文件。"""

    try:
        url = ProjectConfigService().validate_probe_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = await MonitoringService().http_probe("manual", payload.name, url, {"source": "manual"})
    return success(result)
