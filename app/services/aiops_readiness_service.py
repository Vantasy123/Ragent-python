"""AIOps 生产就绪校验服务，汇总数据源、工具安全和闭环能力。"""

from __future__ import annotations

from typing import Any

from app.agents.tool_registry import UnifiedToolRegistry
from app.agents.tools import OpsToolkit
from app.core.config import settings
from app.services.project_config_service import ProjectConfigService


class AIOpsReadinessService:
    """生成运行运维 Agent 前的只读生产就绪报告。"""

    def __init__(
        self,
        config_service: ProjectConfigService | None = None,
        registry: UnifiedToolRegistry | None = None,
    ) -> None:
        self.config_service = config_service or ProjectConfigService()
        self.registry = registry or UnifiedToolRegistry(include_ops=True, toolkit=OpsToolkit())

    def build(self) -> dict[str, Any]:
        """汇总企业生产环境运行 AIOps Agent 所需的关键门禁。"""

        project_status = self.config_service.status()
        monitoring = self.config_service.monitoring()
        servers = self.config_service.servers()
        cloud_resources = self.config_service.cloud_resources()
        tools = self.registry.list_tools("admin")
        checks = [
            self._config_file_check(project_status),
            self._monitoring_check(monitoring),
            self._service_inventory_check(servers),
            self._cloud_resource_check(cloud_resources),
            self._ops_evidence_tools_check(tools),
            self._approval_gate_check(tools),
            self._verification_tool_check(tools),
            self._executor_isolation_check(),
        ]
        failed = [item for item in checks if item["status"] == "failed"]
        warnings = [item for item in checks if item["status"] == "warning"]
        score = round(len([item for item in checks if item["status"] == "passed"]) / len(checks), 4) if checks else 0
        status = "ready" if not failed and not warnings else "degraded" if not failed else "blocked"
        return {
            "status": status,
            "score": score,
            "summary": self._summary(status, checks),
            "checks": checks,
            "dataSources": {
                "metrics": bool(monitoring.get("enabled") and monitoring.get("prometheus_url")),
                "alerts": bool(monitoring.get("enabled") and monitoring.get("alertmanager_url")),
                "logs": self._has_tool(tools, "container_logs"),
                "traces": self._has_tool(tools, "trace_analysis"),
                "events": self._has_tool(tools, "kubernetes_events"),
                "cmdb": bool(servers),
                "cloud": bool(cloud_resources),
                "release": self._has_tool(tools, "release_evidence"),
                "databaseMiddleware": self._has_tool(tools, "database_middleware_health"),
            },
            "nextSteps": self._next_steps(checks),
        }

    def _config_file_check(self, project_status: dict[str, Any]) -> dict[str, Any]:
        """检查基础接入配置文件是否已创建。"""

        passed = bool(project_status.get("serversConfigExists") and project_status.get("monitoringConfigExists"))
        return self._check(
            "config_files",
            "接入配置文件",
            "passed" if passed else "warning",
            "业务服务器和监控配置文件已存在" if passed else "缺少 servers.yml 或 monitoring.yml，生产接入信息不完整",
            "复制 example 配置并补齐业务服务、监控和云资源清单",
        )

    def _monitoring_check(self, monitoring: dict[str, Any]) -> dict[str, Any]:
        """检查 Metrics 和 Alertmanager 配置是否完整。"""

        enabled = bool(monitoring.get("enabled"))
        prometheus = bool(monitoring.get("prometheus_url"))
        alertmanager = bool(monitoring.get("alertmanager_url"))
        passed = enabled and prometheus and alertmanager
        status = "passed" if passed else "failed" if enabled and not (prometheus or alertmanager) else "warning"
        return self._check(
            "metrics_alerts",
            "Metrics/Alerts 接入",
            status,
            "Prometheus 与 Alertmanager 已配置" if passed else "Metrics 或 Alertmanager 接入不完整",
            "配置 monitoring.enabled、prometheus_url 和 alertmanager_url",
        )

    def _service_inventory_check(self, servers: list[dict[str, Any]]) -> dict[str, Any]:
        """检查轻量 CMDB 服务清单。"""

        passed = bool(servers)
        return self._check(
            "service_inventory",
            "服务清单/CMDB",
            "passed" if passed else "warning",
            f"已配置 {len(servers)} 个启用服务" if passed else "未配置启用服务，影响面和拓扑分析会缺少业务上下文",
            "在 servers.yml 中维护服务、owner、健康检查和依赖关系",
        )

    def _cloud_resource_check(self, resources: list[dict[str, Any]]) -> dict[str, Any]:
        """检查云资源清单。"""

        passed = bool(resources)
        return self._check(
            "cloud_resources",
            "云资源清单",
            "passed" if passed else "warning",
            f"已配置 {len(resources)} 个云资源" if passed else "未配置云资源清单，云平台影响面分析会降级",
            "在 monitoring.yml 中维护 cloud_resources，至少包含 provider、region、resource_id、service",
        )

    def _ops_evidence_tools_check(self, tools: list[dict[str, Any]]) -> dict[str, Any]:
        """检查 RCA 所需只读证据工具是否齐全。"""

        required = {
            "alert_correlations",
            "knowledge_search",
            "kubernetes_events",
            "trace_analysis",
            "database_middleware_health",
            "cloud_resource_evidence",
            "service_topology",
            "release_evidence",
            "change_correlations",
            "metric_anomalies",
        }
        available = {str(item.get("name")) for item in tools}
        missing = sorted(required - available)
        return self._check(
            "evidence_tools",
            "RCA 证据工具",
            "passed" if not missing else "failed",
            "告警、知识库、Kubernetes、Trace、数据库中间件、云资源、拓扑和变更证据工具已注册"
            if not missing
            else f"缺少 {len(missing)} 个 RCA 证据工具：{', '.join(missing)}",
            "补齐只读证据工具注册，确保 Agent 可解释地完成 RCA",
        )

    def _approval_gate_check(self, tools: list[dict[str, Any]]) -> dict[str, Any]:
        """检查写操作是否强制审批。"""

        write_tools = [item for item in tools if str(item.get("riskLevel") or item.get("risk_level")) in {"write", "admin", "danger"}]
        bypass = [item for item in write_tools if not bool(item.get("requiresApproval"))]
        return self._check(
            "approval_gates",
            "高危操作审批门禁",
            "passed" if not bypass else "failed",
            "所有写操作均需审批" if not bypass else f"{len(bypass)} 个写操作缺少审批门禁",
            "为写操作设置 requiresApproval，并在审批接口复核当前工具策略",
        )

    def _verification_tool_check(self, tools: list[dict[str, Any]]) -> dict[str, Any]:
        """检查审批后验证所需只读工具。"""

        required = {"api_health_check", "nginx_proxy_check", "frontend_health_check", "metric_trend"}
        available = {str(item.get("name")) for item in tools}
        missing = sorted(required - available)
        return self._check(
            "verification_tools",
            "执行后验证工具",
            "passed" if not missing else "failed",
            "审批后验证所需健康检查和指标趋势工具已注册" if not missing else f"缺少验证工具：{', '.join(missing)}",
            "补齐只读验证工具，避免写操作执行后无法判断修复效果",
        )

    def _executor_isolation_check(self) -> dict[str, Any]:
        """检查执行器是否默认隔离，避免开箱即拥有 Docker 写权限。"""

        enabled = bool(getattr(settings, "AGENT_EXECUTOR_ENABLED", False))
        return self._check(
            "executor_isolation",
            "执行器隔离",
            "passed" if not enabled else "warning",
            "Docker 执行器默认关闭，需显式启用后才能执行生产写操作" if not enabled else "Docker 执行器已启用，请确认运行环境和审批流程",
            "生产启用执行器前确认 Docker socket 权限、服务白名单、审批人和回滚预案",
        )

    def _has_tool(self, tools: list[dict[str, Any]], name: str) -> bool:
        """判断工具目录中是否存在指定工具。"""

        return any(item.get("name") == name for item in tools)

    def _check(self, code: str, name: str, status: str, message: str, remediation: str) -> dict[str, str]:
        """构造统一就绪检查项。"""

        return {"code": code, "name": name, "status": status, "message": message, "remediation": remediation}

    def _next_steps(self, checks: list[dict[str, str]]) -> list[str]:
        """从未通过的检查生成下一步动作。"""

        return [item["remediation"] for item in checks if item["status"] != "passed"]

    def _summary(self, status: str, checks: list[dict[str, str]]) -> str:
        """生成一行面向前端的就绪摘要。"""

        passed = len([item for item in checks if item["status"] == "passed"])
        total = len(checks)
        label = {"ready": "生产就绪", "degraded": "可诊断但有降级项", "blocked": "不建议进入生产自动化"}.get(status, status)
        return f"{label}：{passed}/{total} 项检查通过"
