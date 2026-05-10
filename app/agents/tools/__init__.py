"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from app.agents.base import ToolSpec
from app.core.config import settings


class OpsToolkit:
    """项目级运维工具箱。

    设计原则：
    - 只暴露白名单工具，避免 Agent 获得任意 shell 执行能力。
    - 读取类工具可以自动执行，用于诊断容器状态、日志、健康检查。
    - 写操作工具必须在 ToolSpec 中标记 requires_approval=True，由上层审批后执行。
    """

    def __init__(self) -> None:
        # Docker 命令的工作目录由 compose override 注入，通常指向项目部署目录。
        self.compose_dir = Path(getattr(settings, "AGENT_COMPOSE_DIR", ".")).resolve()
        # 通过 compose project 标签定位容器，避免在轻量镜像里强依赖 docker compose 插件。
        self.compose_project = getattr(settings, "AGENT_COMPOSE_PROJECT", "ragent-python")
        # 默认关闭 Docker 执行器；只有显式启用 ops profile 后才允许访问 Docker socket。
        self.executor_enabled = bool(getattr(settings, "AGENT_EXECUTOR_ENABLED", False))
        # 这些内部地址用于 Agent 在容器网络内自检，避免在 API 容器里把 localhost 错当成前端容器。
        self.api_internal_url = "http://127.0.0.1:8000/api/health"
        self.frontend_internal_url = "http://frontend"
        self.proxy_internal_url = "http://frontend/api/health"
        # 工具名到函数的映射是 Agent 可调用能力的唯一入口。
        self._tools = {
            "compose_ps": self.compose_ps,
            "container_logs": self.container_logs,
            "api_health_check": self.api_health_check,
            "frontend_health_check": self.frontend_health_check,
            "nginx_proxy_check": self.nginx_proxy_check,
            "container_inspect": self.container_inspect,
            "log_analyzer": self.log_analyzer,
            "port_check": self.port_check,
            "system_metrics": self.system_metrics,
            "container_stats": self.container_stats,
            "response_time_probe": self.response_time_probe,
            "alert_status": self.alert_status,
            "metric_trend": self.metric_trend,
            "prometheus_query": self.prometheus_query,
            "compose_restart_service": self.compose_restart_service,
        }

    @property
    def tools(self) -> dict[str, Any]:
        """返回工具函数映射，供 BaseAgent 执行步骤时查找。"""

        return self._tools

    def specs(self) -> list[ToolSpec]:
        """返回工具元数据，前端和审批逻辑都依赖这里的风险标记。"""

        return [
            ToolSpec("compose_ps", "查看 Docker Compose 服务状态", {"project": "string"}),
            ToolSpec("container_logs", "读取容器最近日志", {"service": "string", "tail": "integer"}),
            ToolSpec("api_health_check", "检查后端健康接口", {"url": "string"}),
            ToolSpec("frontend_health_check", "检查前端入口", {"url": "string"}),
            ToolSpec("nginx_proxy_check", "检查前端代理到后端是否可达", {"url": "string"}),
            ToolSpec("container_inspect", "查看容器元信息", {"service": "string"}),
            ToolSpec("log_analyzer", "分析容器日志中的错误模式", {"service": "string", "tail": "integer"}),
            ToolSpec("port_check", "检查主机端口连通性", {"host": "string", "port": "integer"}),
            ToolSpec("system_metrics", "读取基础系统指标"),
            ToolSpec("container_stats", "读取容器资源指标", {"service": "string"}),
            ToolSpec("response_time_probe", "探测接口响应时间", {"url": "string", "count": "integer"}),
            ToolSpec("alert_status", "查看当前告警状态"),
            ToolSpec("metric_trend", "查看指标趋势", {"metric": "string", "minutes": "integer"}),
            ToolSpec("prometheus_query", "执行 Prometheus 即时查询", {"query": "string", "time": "number"}),
            ToolSpec(
                "compose_restart_service",
                "重启指定 Compose 服务",
                {"service": "string"},
                risk_level="write",
                requires_approval=True,
            ),
        ]

    def _run_docker(self, args: list[str], timeout: int = 20) -> dict[str, Any]:
        """执行受控 Docker 命令，并统一包装为工具返回结构。"""

        if not self.executor_enabled:
            return {
                "success": False,
                "summary": "Docker 执行器未启用，请使用 ops override 并挂载 Docker socket。",
                "data": {},
                "error": "executor_disabled",
            }
        try:
            # 不拼接 shell 字符串，直接传 argv，降低命令注入风险。
            proc = subprocess.run(
                ["docker", *args],
                cwd=str(self.compose_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            return {
                "success": proc.returncode == 0,
                "summary": (proc.stdout or proc.stderr or "").strip()[:1000],
                "data": {"stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode},
                "error": "" if proc.returncode == 0 else "docker_command_failed",
            }
        except Exception as exc:
            return {"success": False, "summary": str(exc), "data": {}, "error": type(exc).__name__}

    def _resolve_container_id(self, service: str) -> str | None:
        """根据 compose 项目标签解析服务对应容器 ID。"""

        result = self._run_docker(
            [
                "container",
                "ls",
                "-a",
                "-q",
                "--filter",
                f"label=com.docker.compose.project={self.compose_project}",
                "--filter",
                f"label=com.docker.compose.service={service}",
            ]
        )
        if not result.get("success"):
            return None
        container_id = (result.get("data", {}).get("stdout") or "").strip().splitlines()
        return container_id[0] if container_id else None

    def _safe_service(self, service: str | None) -> str:
        """校验服务名，防止 Agent 构造任意 Docker 目标。"""

        if not service or service.startswith("auto-detect"):
            return "ragent-api"
        # 白名单限制了 Agent 可以读写的 Compose 服务，避免误操作宿主机上的其他项目。
        allowed = {
            "ragent-api",
            "ragent-frontend",
            "ragent-mysql",
            "mysql",
            "frontend",
            "api",
            "ops-test-service",
            # 兼容旧环境中的 PostgreSQL 容器名，避免迁移阶段诊断工具失效。
            "ragent-postgres",
            "postgres",
        }
        if service not in allowed:
            raise ValueError(f"服务不在白名单中：{service}")
        return service

    def compose_ps(self, project: str | None = None) -> dict[str, Any]:
        """查看当前 compose 项目的服务状态。"""

        target_project = project or self.compose_project
        return self._run_docker(
            [
                "container",
                "ls",
                "-a",
                "--filter",
                f"label=com.docker.compose.project={target_project}",
                "--format",
                "table {{.Names}}\t{{.Status}}\t{{.Ports}}",
            ]
        )

    def container_logs(self, service: str = "ragent-api", tail: int = 120) -> dict[str, Any]:
        """读取指定服务最近日志，tail 限制避免一次返回过大内容。"""

        safe_service = self._safe_service(service)
        container_id = self._resolve_container_id(safe_service)
        if not container_id:
            return {"success": False, "summary": f"未找到服务对应容器：{safe_service}", "data": {}, "error": "container_not_found"}
        return self._run_docker(["container", "logs", "--tail", str(tail), container_id])

    def container_inspect(self, service: str = "ragent-api") -> dict[str, Any]:
        """获取 compose 服务对应容器 ID，供诊断容器是否存在。"""

        safe_service = self._safe_service(service)
        container_id = self._resolve_container_id(safe_service)
        if not container_id:
            return {"success": False, "summary": f"未找到服务对应容器：{safe_service}", "data": {}, "error": "container_not_found"}
        return self._run_docker(["inspect", container_id])

    def compose_restart_service(self, service: str = "ragent-api") -> dict[str, Any]:
        """重启服务；该工具在 specs 中标记为写操作，必须审批后调用。"""

        safe_service = self._safe_service(service)
        container_id = self._resolve_container_id(safe_service)
        if not container_id:
            return {"success": False, "summary": f"未找到服务对应容器：{safe_service}", "data": {}, "error": "container_not_found"}
        return self._run_docker(["restart", container_id], timeout=60)

    def log_analyzer(self, service: str = "ragent-api", tail: int = 200) -> dict[str, Any]:
        """基于关键词从日志中提取疑似错误行，作为快速诊断摘要。"""

        result = self.container_logs(service, tail)
        text = result.get("data", {}).get("stdout", "") + result.get("data", {}).get("stderr", "")
        keywords = ["error", "exception", "traceback", "502", "connection refused", "failed"]
        hits = [line for line in text.splitlines() if any(word in line.lower() for word in keywords)]
        return {"success": result.get("success", False), "summary": f"发现 {len(hits)} 条疑似错误日志", "data": {"hits": hits[:50]}}

    async def api_health_check(self, url: str = "http://localhost:8000/api/health") -> dict[str, Any]:
        """直连后端健康检查。"""

        # 在 SSE 请求处理中回探本进程接口时，必须异步让出事件循环，否则单 worker 会自锁超时。
        return await self._http_check(url or self.api_internal_url)

    async def frontend_health_check(self, url: str = "http://localhost") -> dict[str, Any]:
        """检查前端页面入口是否可访问。"""

        target = self.frontend_internal_url if not url or "localhost" in url else url
        return await self._http_check(target)

    async def nginx_proxy_check(self, url: str = "http://localhost/api/health") -> dict[str, Any]:
        """检查 Nginx 是否能正确代理到后端 API。"""

        target = self.proxy_internal_url if not url or "localhost" in url else url
        return await self._http_check(target)

    async def _http_check(self, url: str) -> dict[str, Any]:
        """执行 HTTP 探活，并记录状态码、耗时和响应片段。"""

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
            duration_ms = int((time.perf_counter() - started) * 1000)
            return {
                "success": response.status_code < 500,
                "summary": f"HTTP {response.status_code}，耗时 {duration_ms} ms",
                "data": {"statusCode": response.status_code, "durationMs": duration_ms, "text": response.text[:1000]},
            }
        except Exception as exc:
            return {"success": False, "summary": str(exc), "data": {}, "error": type(exc).__name__}

    def port_check(self, host: str = "localhost", port: int | str = 8000, target: str | None = None) -> dict[str, Any]:
        """检查 TCP 端口连通性，支持 target=host:port 的紧凑入参。"""

        if target and ":" in target:
            host, raw_port = target.rsplit(":", 1)
            port = int(raw_port)
        started = time.perf_counter()
        try:
            with socket.create_connection((host, int(port)), timeout=3):
                duration_ms = int((time.perf_counter() - started) * 1000)
                return {"success": True, "summary": f"{host}:{port} 可连接，耗时 {duration_ms} ms", "data": {"durationMs": duration_ms}}
        except Exception as exc:
            return {"success": False, "summary": f"{host}:{port} 不可连接：{exc}", "data": {}, "error": type(exc).__name__}

    async def system_metrics(self) -> dict[str, Any]:
        """读取基础系统指标；Prometheus 不可用时回退到占位快照。"""

        fallback = {
            "success": True,
            "summary": "监控源未配置或不可用，已返回基础占位指标",
            "data": {"cpuPercent": 0, "memoryPercent": 0, "source": "fallback"},
            "error": "monitoring_not_configured" if not self._monitoring_enabled() else "monitoring_query_failed",
        }
        if not self._monitoring_enabled() or not getattr(settings, "PROMETHEUS_URL", ""):
            return fallback

        cpu = await self._prometheus_instant_query(self._metric_query("cpu_percent"))
        memory = await self._prometheus_instant_query(self._metric_query("memory_percent"))
        if not cpu.get("success") and not memory.get("success"):
            fallback["summary"] = "Prometheus 指标查询失败，已返回基础占位指标"
            return fallback

        cpu_value = self._first_prometheus_value(cpu)
        memory_value = self._first_prometheus_value(memory)
        return {
            "success": True,
            "summary": f"CPU {cpu_value:.2f}%，内存 {memory_value:.2f}%",
            "data": {
                "cpuPercent": cpu_value,
                "memoryPercent": memory_value,
                "source": "prometheus",
                "raw": {"cpu": cpu.get("data"), "memory": memory.get("data")},
            },
            "error": "",
        }

    def container_stats(self, service: str = "ragent-api") -> dict[str, Any]:
        """读取 Docker 容器资源快照。"""

        safe_service = self._safe_service(service)
        container_id = self._resolve_container_id(safe_service)
        if not container_id:
            return {"success": False, "summary": f"未找到服务对应容器：{safe_service}", "data": {}, "error": "container_not_found"}
        return self._run_docker(["container", "stats", "--no-stream", "--format", "json", container_id])

    async def response_time_probe(self, url: str = "http://localhost/api/health", count: int = 3) -> dict[str, Any]:
        """连续探测接口响应时间，用简单均值判断是否存在明显慢请求。"""

        target = self.api_internal_url if not url or "localhost" in url else url
        samples = []
        # 顺序探测即可，这里更关心稳定性，不追求并发压测。
        for _ in range(max(1, min(count, 10))):
            result = await self._http_check(target)
            samples.append(result.get("data", {}).get("durationMs", 0))
        avg = sum(samples) / len(samples)
        return {"success": True, "summary": f"平均响应时间 {avg:.0f} ms", "data": {"samples": samples, "avgMs": avg}}

    async def alert_status(self) -> dict[str, Any]:
        """从 Alertmanager 查询当前告警状态。"""

        if not self._monitoring_enabled() or not getattr(settings, "ALERTMANAGER_URL", ""):
            return self._monitoring_not_configured("Alertmanager 未配置，无法查询当前告警")

        url = self._join_url(settings.ALERTMANAGER_URL, "/api/v2/alerts")
        try:
            async with httpx.AsyncClient(timeout=float(settings.MONITORING_TIMEOUT_SECONDS)) as client:
                response = await client.get(url)
                response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return self._monitoring_query_failed(f"Alertmanager 查询失败：{exc}")

        alerts = payload if isinstance(payload, list) else []
        active_alerts = []
        for item in alerts:
            if not isinstance(item, dict):
                continue
            status = item.get("status") if isinstance(item.get("status"), dict) else {}
            if status.get("state") not in {"active", "unprocessed", "suppressed"}:
                continue
            labels = item.get("labels") if isinstance(item.get("labels"), dict) else {}
            annotations = item.get("annotations") if isinstance(item.get("annotations"), dict) else {}
            active_alerts.append(
                {
                    "name": labels.get("alertname", "unknown"),
                    "severity": labels.get("severity", "unknown"),
                    "summary": annotations.get("summary") or annotations.get("description") or "",
                    "startsAt": item.get("startsAt"),
                    "labels": labels,
                }
            )

        if not active_alerts:
            return {"success": True, "summary": "当前没有活跃告警", "data": {"alerts": [], "count": 0}, "error": ""}
        top = active_alerts[0]
        return {
            "success": True,
            "summary": f"当前有 {len(active_alerts)} 条活跃告警，最高优先关注 {top['name']}（{top['severity']}）",
            "data": {"alerts": active_alerts, "count": len(active_alerts)},
            "error": "",
        }

    async def metric_trend(self, metric: str = "cpu_percent", minutes: int = 30) -> dict[str, Any]:
        """从 Prometheus 查询指定指标最近一段时间的趋势。"""

        if not self._monitoring_enabled() or not getattr(settings, "PROMETHEUS_URL", ""):
            return self._monitoring_not_configured("Prometheus 未配置，无法查询指标趋势")

        safe_minutes = max(1, min(int(minutes or 30), 24 * 60))
        query = self._metric_query(metric)
        end = time.time()
        start = end - safe_minutes * 60
        step = max(15, int((safe_minutes * 60) / 30))
        result = await self._prometheus_range_query(query, start, end, step)
        if not result.get("success"):
            return result

        points = self._prometheus_points(result)
        if not points:
            return {
                "success": True,
                "summary": f"{metric} 最近 {safe_minutes} 分钟没有返回时序点",
                "data": {"metric": metric, "query": query, "points": []},
                "error": "",
            }
        values = [point["value"] for point in points]
        return {
            "success": True,
            "summary": f"{metric} 最近 {safe_minutes} 分钟平均 {sum(values) / len(values):.2f}，最大 {max(values):.2f}",
            "data": {"metric": metric, "query": query, "points": points, "min": min(values), "max": max(values), "avg": sum(values) / len(values)},
            "error": "",
        }

    async def prometheus_query(self, query: str = "", time: float | None = None) -> dict[str, Any]:
        """执行 Prometheus 即时查询，供 Planner 针对具体故障补充指标。"""

        if not query:
            return {"success": False, "summary": "PromQL 不能为空", "data": {}, "error": "invalid_promql"}
        if not self._monitoring_enabled() or not getattr(settings, "PROMETHEUS_URL", ""):
            return self._monitoring_not_configured("Prometheus 未配置，无法执行即时查询")
        return await self._prometheus_instant_query(query, time=time)

    def _monitoring_enabled(self) -> bool:
        """统一判断监控查询是否启用。"""

        return bool(getattr(settings, "MONITORING_ENABLED", False))

    def _monitoring_not_configured(self, summary: str) -> dict[str, Any]:
        """返回监控源未配置的统一结构，避免调用方需要捕获异常。"""

        return {"success": False, "summary": summary, "data": {}, "error": "monitoring_not_configured"}

    def _monitoring_query_failed(self, summary: str) -> dict[str, Any]:
        """返回监控查询失败的统一结构。"""

        return {"success": False, "summary": summary, "data": {}, "error": "monitoring_query_failed"}

    def _join_url(self, base: str, path: str) -> str:
        """拼接监控服务地址，兼容环境变量中是否带尾部斜杠。"""

        return f"{base.rstrip('/')}/{path.lstrip('/')}"

    def _metric_query(self, metric: str) -> str:
        """将常用指标别名转换为 PromQL，未识别时按原始 PromQL 处理。"""

        aliases = {
            "cpu": "100 * (1 - avg(rate(node_cpu_seconds_total{mode=\"idle\"}[5m])))",
            "cpu_percent": "100 * (1 - avg(rate(node_cpu_seconds_total{mode=\"idle\"}[5m])))",
            "memory": "100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))",
            "memory_percent": "100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))",
            "request_rate": "sum(rate(http_requests_total[5m]))",
            "error_rate": "sum(rate(http_requests_total{status=~\"5..\"}[5m]))",
            "latency_p95": "histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))",
        }
        return aliases.get(str(metric or "").strip(), str(metric or "").strip())

    async def _prometheus_instant_query(self, query: str, time: float | None = None) -> dict[str, Any]:
        """调用 Prometheus 即时查询接口。"""

        url = self._join_url(settings.PROMETHEUS_URL, "/api/v1/query")
        params: dict[str, Any] = {"query": query}
        if time is not None:
            params["time"] = time
        try:
            async with httpx.AsyncClient(timeout=float(settings.MONITORING_TIMEOUT_SECONDS)) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return self._monitoring_query_failed(f"Prometheus 查询失败：{exc}")
        if payload.get("status") != "success":
            return self._monitoring_query_failed(str(payload.get("error") or "Prometheus 返回失败状态"))
        result = payload.get("data", {}).get("result", [])
        return {
            "success": True,
            "summary": f"Prometheus 查询成功，返回 {len(result)} 组结果",
            "data": {"query": query, "result": result, "resultType": payload.get("data", {}).get("resultType")},
            "error": "",
        }

    async def _prometheus_range_query(self, query: str, start: float, end: float, step: int) -> dict[str, Any]:
        """调用 Prometheus 区间查询接口。"""

        url = self._join_url(settings.PROMETHEUS_URL, "/api/v1/query_range")
        try:
            async with httpx.AsyncClient(timeout=float(settings.MONITORING_TIMEOUT_SECONDS)) as client:
                response = await client.get(url, params={"query": query, "start": start, "end": end, "step": step})
                response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return self._monitoring_query_failed(f"Prometheus 趋势查询失败：{exc}")
        if payload.get("status") != "success":
            return self._monitoring_query_failed(str(payload.get("error") or "Prometheus 返回失败状态"))
        result = payload.get("data", {}).get("result", [])
        return {
            "success": True,
            "summary": f"Prometheus 趋势查询成功，返回 {len(result)} 组序列",
            "data": {"query": query, "result": result, "resultType": payload.get("data", {}).get("resultType")},
            "error": "",
        }

    def _first_prometheus_value(self, result: dict[str, Any]) -> float:
        """从 Prometheus 即时查询结果中提取第一个数值。"""

        rows = result.get("data", {}).get("result") or []
        if not rows:
            return 0.0
        value = rows[0].get("value") if isinstance(rows[0], dict) else None
        if not isinstance(value, list) or len(value) < 2:
            return 0.0
        try:
            return float(value[1])
        except (TypeError, ValueError):
            return 0.0

    def _prometheus_points(self, result: dict[str, Any]) -> list[dict[str, float]]:
        """把 Prometheus matrix 结果压平成前端和报告易消费的点位。"""

        series = result.get("data", {}).get("result") or []
        points: list[dict[str, float]] = []
        for item in series[:3]:
            if not isinstance(item, dict):
                continue
            for raw_time, raw_value in item.get("values") or []:
                try:
                    points.append({"timestamp": float(raw_time), "value": float(raw_value)})
                except (TypeError, ValueError):
                    continue
        return points[-120:]


def get_toolkit() -> OpsToolkit:
    """工厂函数，便于后续按请求注入不同工具配置。"""

    return OpsToolkit()
