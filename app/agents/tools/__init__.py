"""模块导读：本文件位于 app/agents/tools/__init__.py，属于Agent 编排层。

主要职责：描述智能体、工具调用、计划执行、审批边界和流式事件的运行方式。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

import shlex
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

from app.agents.base import ToolSpec
from app.core.config import settings
from app.services.monitoring_service import MonitoringService


@dataclass(frozen=True)
class SafeCommandTemplate:
    """命令模板元数据，禁止 Agent 直接执行任意 shell 字符串。"""

    command_id: str
    description: str
    risk_level: str
    requires_approval: bool
    build_args: Callable[["OpsToolkit", dict[str, Any]], list[str]]
    timeout: int = 20


class OpsToolkit:
    """项目级运维工具箱。

    设计原则：
    - 只暴露白名单工具，避免 Agent 获得任意 shell 执行能力。
    - 读取类工具可以自动执行，用于诊断容器状态、日志、健康检查。
    - 写操作工具必须在 ToolSpec 中标记 requires_approval=True，由上层审批后执行。
    """

    def __init__(self) -> None:
        # Docker 命令的工作目录由 compose override 注入，通常指向项目部署目录。
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
        self.compose_dir = Path(getattr(settings, "AGENT_COMPOSE_DIR", ".")).resolve()
        # 通过 compose project 标签定位容器，避免在轻量镜像里强依赖 docker compose 插件。
        self.compose_project = getattr(settings, "AGENT_COMPOSE_PROJECT", "ragent-python")
        # 默认关闭 Docker 执行器；只有显式启用 ops profile 后才允许访问 Docker socket。
        self.executor_enabled = bool(getattr(settings, "AGENT_EXECUTOR_ENABLED", False))
        # 这些内部地址用于 Agent 在容器网络内自检，避免在 API 容器里把 localhost 错当成前端容器。
        self.api_internal_url = "http://127.0.0.1:8000/api/health"
        self.frontend_internal_url = "http://frontend"
        self.proxy_internal_url = "http://frontend/api/health"
        # 监控查询统一走服务层，保证 API 看板和 Ops Agent 的指标口径一致。
        self.monitoring_service = MonitoringService()
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
            "safe_command": self.safe_command,
            "compose_restart_service": self.compose_restart_service,
        }
        self.safe_command_templates = self._build_safe_command_templates()

    @property
    def tools(self) -> dict[str, Any]:
        """返回工具函数映射，统一由 UnifiedToolRegistry 包装调用。"""

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
                "safe_command",
                "执行命令模板白名单；支持 docker_ps、docker_logs、docker_inspect、docker_stats、docker_restart，docker_restart 需要审批。",
                {"commandId": "string", "args": "object", "command": "string"},
                risk_level="dynamic",
            ),
            ToolSpec(
                "compose_restart_service",
                "重启指定 Compose 服务",
                {"service": "string"},
                risk_level="write",
                requires_approval=True,
            ),
        ]

    def approval_policy(self, tool_name: str) -> Callable[[dict[str, Any]], tuple[str, bool]] | None:
        """返回工具的动态审批策略；普通工具沿用 ToolSpec 静态配置。"""

        if tool_name != "safe_command":
            return None
        return self.safe_command_policy

    def safe_command_policy(self, args: dict[str, Any]) -> tuple[str, bool]:
        """根据 commandId 或命令文本判断 safe_command 的实际风险等级。"""

        resolved = self._resolve_safe_command(args)
        if not resolved.get("success"):
            return "danger", False
        template = resolved["template"]
        return template.risk_level, template.requires_approval

    def safe_command(
        self,
        commandId: str = "",
        command_id: str = "",
        args: dict[str, Any] | None = None,
        command: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """执行命令模板白名单，不执行 LLM 原始 shell。"""

        payload = {"commandId": commandId or command_id, "args": args or {}, "command": command, **kwargs}
        resolved = self._resolve_safe_command(payload)
        if not resolved.get("success"):
            return {
                "success": False,
                "summary": resolved["error"],
                "data": {"command": command, "commandId": commandId or command_id},
                "error": "command_not_allowed",
                "riskLevel": "danger",
                "requiresApproval": False,
            }
        template: SafeCommandTemplate = resolved["template"]
        safe_args: dict[str, Any] = resolved["args"]
        try:
            docker_args = template.build_args(self, safe_args)
        except Exception as exc:
            return {
                "success": False,
                "summary": str(exc),
                "data": {"commandId": template.command_id},
                "error": type(exc).__name__,
                "riskLevel": template.risk_level,
                "requiresApproval": template.requires_approval,
            }
        result = self._run_docker(docker_args, timeout=template.timeout)
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        result["data"] = {
            **data,
            "commandId": template.command_id,
            "commandPreview": "docker " + " ".join(docker_args),
            "riskLevel": template.risk_level,
        }
        result["riskLevel"] = template.risk_level
        result["requiresApproval"] = template.requires_approval
        return result

    def _build_safe_command_templates(self) -> dict[str, SafeCommandTemplate]:
        """构造允许执行的命令模板；新增命令必须显式写入这里。"""

        return {
            "docker_ps": SafeCommandTemplate(
                "docker_ps",
                "查看当前 Compose 项目容器状态",
                "read",
                False,
                lambda toolkit, payload: [
                    "container",
                    "ls",
                    "-a",
                    "--filter",
                    f"label=com.docker.compose.project={payload.get('project') or toolkit.compose_project}",
                    "--format",
                    "table {{.Names}}\t{{.Status}}\t{{.Ports}}",
                ],
            ),
            "docker_logs": SafeCommandTemplate(
                "docker_logs",
                "读取白名单服务最近日志",
                "read",
                False,
                lambda toolkit, payload: toolkit._docker_logs_args(payload),
            ),
            "docker_inspect": SafeCommandTemplate(
                "docker_inspect",
                "查看白名单服务容器元信息",
                "read",
                False,
                lambda toolkit, payload: toolkit._docker_container_args(payload, ["inspect"]),
            ),
            "docker_stats": SafeCommandTemplate(
                "docker_stats",
                "读取白名单服务容器资源快照",
                "read",
                False,
                lambda toolkit, payload: toolkit._docker_container_args(payload, ["container", "stats", "--no-stream", "--format", "json"]),
            ),
            "docker_restart": SafeCommandTemplate(
                "docker_restart",
                "重启白名单服务容器",
                "write",
                True,
                lambda toolkit, payload: toolkit._docker_container_args(payload, ["restart"]),
                timeout=60,
            ),
        }

    def _resolve_safe_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        """把 commandId 或命令文本解析为白名单模板和参数。"""

        raw_args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
        args = {**raw_args}
        for key, value in payload.items():
            if key in {"args", "command", "commandId", "command_id"}:
                continue
            if value is not None and value != "":
                args[key] = value
        command_id = str(payload.get("commandId") or payload.get("command_id") or "").strip()
        if not command_id and payload.get("command"):
            parsed = self._parse_safe_command_text(str(payload.get("command") or ""))
            if not parsed.get("success"):
                return parsed
            command_id = parsed["commandId"]
            args.update(parsed.get("args") or {})
        template = self.safe_command_templates.get(command_id)
        if not template:
            return {"success": False, "error": f"命令不在白名单中：{command_id or payload.get('command') or '空命令'}"}
        try:
            self._validate_safe_command_args(command_id, args)
        except Exception as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "template": template, "args": args}

    def _parse_safe_command_text(self, command: str) -> dict[str, Any]:
        """只把少量 Docker 命令文本映射到模板，不透传原始命令。"""

        text = command.strip()
        if not text:
            return {"success": False, "error": "命令不能为空"}
        blocked = [";", "&&", "||", "|", ">", "<", "`", "$("]
        if any(token in text for token in blocked):
            return {"success": False, "error": "命令包含不允许的 shell 控制符"}
        try:
            parts = shlex.split(text)
        except ValueError as exc:
            return {"success": False, "error": f"命令解析失败：{exc}"}
        if not parts or parts[0] != "docker":
            return {"success": False, "error": "只允许 docker 白名单命令"}
        normalized = parts[1:]
        if normalized[:2] == ["container", "ls"] or normalized[:1] == ["ps"]:
            return {"success": True, "commandId": "docker_ps", "args": {}}
        if normalized[:2] == ["container", "logs"] or normalized[:1] == ["logs"]:
            tail = 120
            service = ""
            tokens = normalized[2:] if normalized[:2] == ["container", "logs"] else normalized[1:]
            index = 0
            while index < len(tokens):
                token = tokens[index]
                if token == "--tail" and index + 1 < len(tokens):
                    try:
                        tail = int(tokens[index + 1])
                    except ValueError:
                        return {"success": False, "error": "日志 tail 必须是整数"}
                    index += 2
                    continue
                if not token.startswith("-"):
                    service = token
                index += 1
            return {"success": True, "commandId": "docker_logs", "args": {"service": service, "tail": tail}}
        if normalized[:1] == ["inspect"] and len(normalized) >= 2:
            return {"success": True, "commandId": "docker_inspect", "args": {"service": normalized[-1]}}
        if normalized[:3] == ["container", "stats", "--no-stream"] or normalized[:2] == ["stats", "--no-stream"]:
            return {"success": True, "commandId": "docker_stats", "args": {"service": normalized[-1]}}
        if normalized[:1] == ["restart"] and len(normalized) >= 2:
            return {"success": True, "commandId": "docker_restart", "args": {"service": normalized[-1]}}
        return {"success": False, "error": "命令未匹配任何白名单模板"}

    def _validate_safe_command_args(self, command_id: str, args: dict[str, Any]) -> None:
        """校验模板参数，避免命令模板被异常参数污染。"""

        if command_id in {"docker_logs", "docker_inspect", "docker_stats", "docker_restart"}:
            self._safe_service(str(args.get("service") or "ragent-api"))
        if command_id == "docker_logs":
            tail = int(args.get("tail") or 120)
            if tail <= 0 or tail > 1000:
                raise ValueError("日志 tail 必须在 1 到 1000 之间")

    def _docker_logs_args(self, payload: dict[str, Any]) -> list[str]:
        """构造 docker logs 参数，容器 ID 由白名单服务名解析而来。"""

        safe_service = self._safe_service(str(payload.get("service") or "ragent-api"))
        container_id = self._resolve_container_id(safe_service)
        if not container_id:
            raise ValueError(f"未找到服务对应容器：{safe_service}")
        tail = max(1, min(int(payload.get("tail") or 120), 1000))
        return ["container", "logs", "--tail", str(tail), container_id]

    def _docker_container_args(self, payload: dict[str, Any], prefix: list[str]) -> list[str]:
        """构造需要容器 ID 的 Docker 命令参数。"""

        safe_service = self._safe_service(str(payload.get("service") or "ragent-api"))
        container_id = self._resolve_container_id(safe_service)
        if not container_id:
            raise ValueError(f"未找到服务对应容器：{safe_service}")
        return [*prefix, container_id]

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
        aliases = {
            "api": "ragent-api",
            "backend": "ragent-api",
            "后端": "ragent-api",
            "服务端": "ragent-api",
            "frontend": "ragent-frontend",
            "front": "ragent-frontend",
            "nginx": "ragent-frontend",
            "前端": "ragent-frontend",
        }
        service = aliases.get(str(service).lower(), service)
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

        return await self.monitoring_service.tool_system_metrics()

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

        return await self.monitoring_service.tool_alert_status()

    async def metric_trend(self, metric: str = "cpu_percent", minutes: int = 30) -> dict[str, Any]:
        """从 Prometheus 查询指定指标最近一段时间的趋势。"""

        return await self.monitoring_service.tool_metric_trend(metric, minutes)

    async def prometheus_query(self, query: str = "", time: float | None = None) -> dict[str, Any]:
        """执行 Prometheus 即时查询，供 Planner 针对具体故障补充指标。"""

        return await self.monitoring_service.tool_prometheus_query(query, time=time)

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
