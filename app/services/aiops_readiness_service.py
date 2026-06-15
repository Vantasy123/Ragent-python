"""AIOps 生产就绪校验服务，汇总数据源、工具安全和闭环能力。"""

from __future__ import annotations

from typing import Any

from app.agents.orchestrator import AGENT_REGISTRY
from app.agents.tool_registry import UnifiedToolRegistry
from app.agents.tools import OpsToolkit
from app.core.config import settings
from app.core.text_sanitizer import REDACTED_VALUE, redact_sensitive_payload
from app.services.project_config_service import ProjectConfigService


class AIOpsReadinessService:
    """生成运行运维 Agent 前的只读生产就绪报告。"""

    def __init__(
        self,
        config_service: ProjectConfigService | None = None,
        registry: UnifiedToolRegistry | None = None,
        agent_registry: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.config_service = config_service or ProjectConfigService()
        self.registry = registry or UnifiedToolRegistry(include_ops=True, toolkit=OpsToolkit())
        self.agent_registry = agent_registry or AGENT_REGISTRY

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
            self._multi_agent_topology_check(),
            self._ops_evidence_tools_check(tools),
            self._approval_gate_check(tools),
            self._verification_tool_check(tools),
            self._executor_isolation_check(),
            self._command_governance_check(),
            self._audit_redaction_check(),
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
            "agentTopology": {
                "planner": self._has_agent("planner"),
                "diagnostics": self._has_agent("diagnostics"),
                "knowledge": self._has_agent("knowledge"),
                "executor": self._has_agent("executor"),
                "verification": self._has_agent("verification"),
                "audit": self._has_agent("audit"),
            },
            "safetyControls": {
                "approvalGates": self._check_passed(checks, "approval_gates"),
                "executorIsolation": self._check_passed(checks, "executor_isolation"),
                "commandWhitelist": self._check_passed(checks, "command_governance"),
                "highRiskInterception": self._check_passed(checks, "command_governance"),
                "secretIsolation": self._check_passed(checks, "command_governance") and self._check_passed(checks, "audit_redaction"),
                "auditRedaction": self._check_passed(checks, "audit_redaction"),
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

    def _multi_agent_topology_check(self) -> dict[str, Any]:
        """检查生产闭环所需的核心 Agent 角色是否已注册。"""

        required = {
            "planner": "计划 Agent",
            "diagnostics": "诊断 Agent",
            "knowledge": "知识 Agent",
            "executor": "执行 Agent",
            "verification": "验证 Agent",
            "audit": "审计 Agent",
        }
        missing = [label for key, label in required.items() if not self._has_agent(key)]
        return self._check(
            "multi_agent_topology",
            "多 Agent 拓扑",
            "passed" if not missing else "failed",
            "计划、诊断、知识、执行、验证和审计 Agent 均已注册" if not missing else f"缺少核心 Agent：{', '.join(missing)}",
            "补齐 AGENT_REGISTRY 中的计划、诊断、知识、执行、验证和审计角色，确保职责分离可审计",
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

    def _command_governance_check(self) -> dict[str, Any]:
        """检查命令行工具是否只能通过模板白名单和动态审批策略执行。"""

        tool = self.registry.tools.get("safe_command")
        if not tool:
            return self._check(
                "command_governance",
                "命令白名单/高危拦截",
                "failed",
                "未注册 safe_command，Agent 无法按模板白名单执行受控命令",
                "注册 safe_command，并为读命令、写命令、未知命令和敏感参数配置策略",
            )

        read_risk, read_approval = tool.policy_for({"commandId": "docker_ps"})
        write_risk, write_approval = tool.policy_for({"commandId": "docker_restart", "args": {"service": "ragent-api"}})
        blocked_risk, blocked_approval = tool.policy_for({"command": "rm -rf /"})
        secret_risk, secret_approval = tool.policy_for({"commandId": "docker_logs", "args": {"service": "ragent-api", "apiToken": "secret-token"}})
        passed = (
            read_risk == "read"
            and not read_approval
            and write_risk in {"write", "admin", "danger", "high"}
            and write_approval
            and blocked_risk == "danger"
            and not blocked_approval
            and secret_risk == "danger"
            and not secret_approval
        )
        return self._check(
            "command_governance",
            "命令白名单/高危拦截",
            "passed" if passed else "failed",
            "命令执行已限制为模板白名单，写命令需要审批，未知命令和敏感凭证会被拦截"
            if passed
            else "safe_command 未同时满足读命令免审批、写命令审批、未知命令阻断和敏感参数阻断",
            "检查 safe_command 模板、动态审批策略和敏感参数拦截规则",
        )

    def _audit_redaction_check(self) -> dict[str, Any]:
        """检查审计和 Trace 入库前是否能遮蔽常见凭证。"""

        sample = {
            "apiToken": "secret-token",
            "url": "https://user:pass@example.com/api?token=url-token&safe=1",
            "headers": {"Authorization": "Bearer header-token"},
        }
        redacted = redact_sensitive_payload(sample)
        text = str(redacted)
        leaked = any(secret in text for secret in ("secret-token", "url-token", "header-token", "user:pass"))
        passed = REDACTED_VALUE in text and not leaked
        return self._check(
            "audit_redaction",
            "审计脱敏",
            "passed" if passed else "failed",
            "审计 payload 会在入库前遮蔽 Token、Authorization、URL 凭证等敏感信息"
            if passed
            else "审计脱敏样本仍存在未遮蔽凭证",
            "修正 text_sanitizer 的敏感字段和 URL 脱敏规则，避免凭证进入 Trace、工具结果和复盘报告",
        )

    def _has_tool(self, tools: list[dict[str, Any]], name: str) -> bool:
        """判断工具目录中是否存在指定工具。"""

        return any(item.get("name") == name for item in tools)

    def _has_agent(self, name: str) -> bool:
        """判断核心 Agent 注册表中是否存在指定角色。"""

        item = self.agent_registry.get(name)
        return isinstance(item, dict) and bool(item.get("name")) and bool(item.get("description"))

    def _check_passed(self, checks: list[dict[str, str]], code: str) -> bool:
        """判断指定就绪检查是否通过，供安全控制面汇总使用。"""

        return any(item.get("code") == code and item.get("status") == "passed" for item in checks)

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
