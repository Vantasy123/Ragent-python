"""后台运维监控 API，供 Antigravity 前端看板直接对接。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.models import User
from app.services.common import success
from app.services.dependencies import require_admin
from app.services.monitoring_service import MonitoringService
from app.services.trace_analysis_service import TraceAnalysisService

router = APIRouter(prefix="/admin/monitoring", tags=["monitoring"])


class PrometheusQueryPayload(BaseModel):
    """Prometheus 即时查询请求体。"""

    query: str
    time: float | None = None


@router.get("/overview")
async def overview(_: User = Depends(require_admin)):
    """返回运维监控总览，包括核心指标、服务探测、告警和采集目标。"""

    return success(await MonitoringService().overview())


@router.get("/targets")
async def targets(_: User = Depends(require_admin)):
    """返回 Prometheus 当前采集目标状态。"""

    return success(await MonitoringService().targets())


@router.get("/alerts")
async def alerts(_: User = Depends(require_admin)):
    """返回 Alertmanager 当前活跃告警。"""

    return success(await MonitoringService().alerts())


@router.get("/alert-correlations")
async def alert_correlations(_: User = Depends(require_admin)):
    """返回活跃告警的降噪聚合、影响面和 RCA 初筛线索。"""

    return success(await MonitoringService().alert_correlations())


@router.get("/kubernetes-events")
async def kubernetes_events(_: User = Depends(require_admin)):
    """返回 Kubernetes Pod、工作负载和节点事件分析结果。"""

    return success(await MonitoringService().kubernetes_events())


@router.get("/trace-analysis")
async def trace_analysis(
    limit: int = Query(20, ge=1, le=100),
    slowThresholdMs: int = Query(1000, ge=1, le=600000),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """返回最近 Trace 调用链中的慢 span、失败 span 和耗时热点。"""

    return success(TraceAnalysisService(db).analyze_recent(limit=limit, slow_threshold_ms=slowThresholdMs))


@router.get("/database-middleware")
async def database_middleware(_: User = Depends(require_admin)):
    """返回 Redis、MySQL、PostgreSQL 等数据库和中间件健康分析结果。"""

    return success(await MonitoringService().database_middleware_health())


@router.get("/change-correlations")
async def change_correlations(_: User = Depends(require_admin)):
    """返回活跃告警中的发布、提交、镜像和流水线变更关联线索。"""

    return success(await MonitoringService().change_correlations())


@router.get("/service-topology")
async def service_topology(_: User = Depends(require_admin)):
    """返回服务拓扑、依赖边和故障影响传播路径。"""

    return success(await MonitoringService().service_topology())


@router.post("/query")
async def query(payload: PrometheusQueryPayload, _: User = Depends(require_admin)):
    """执行受控 PromQL 即时查询，仅管理员可用。"""

    return success(await MonitoringService().prometheus_instant_query(payload.query, query_time=payload.time))


@router.get("/series/{metric}")
async def series(metric: str, minutes: int = Query(30, ge=1, le=1440), _: User = Depends(require_admin)):
    """返回指定指标最近一段时间的序列数据。"""

    return success(await MonitoringService().metric_series(metric, minutes))


@router.get("/anomalies/{metric}")
async def anomalies(metric: str, minutes: int = Query(30, ge=1, le=1440), _: User = Depends(require_admin)):
    """返回指定指标的高水位、突增和波动异常检测结果。"""

    return success(await MonitoringService().metric_anomalies(metric, minutes))


@router.get("/probes")
async def probes(_: User = Depends(require_admin)):
    """返回后端、前端代理和运维测试服务的 HTTP 探测结果。"""

    return success(await MonitoringService().probes())
