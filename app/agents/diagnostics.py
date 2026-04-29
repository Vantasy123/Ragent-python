"""诊断 Agent，负责容器、代理、健康检查和日志类排障。"""

from __future__ import annotations

from app.agents.base import AgentRole, AgentStep, BaseAgent, ToolSpec
from app.agents.tools import OpsToolkit


class DiagnosticsAgent(BaseAgent):
    """诊断 Agent，负责定位容器、代理、健康检查和日志类故障。"""

    role = AgentRole.DIAGNOSTICS
    name = "diagnostics"
    description = "诊断后端 502、容器异常、健康检查失败和日志报错。"

    def __init__(self, toolkit: OpsToolkit | None = None) -> None:
        # 多个子 Agent 共用同一个 toolkit，确保工具配置和安全边界一致。
        self.toolkit = toolkit or OpsToolkit()
        super().__init__(self.toolkit.tools)

    def tool_specs(self) -> list[ToolSpec]:
        """诊断 Agent 只使用只读诊断工具。"""

        return [spec for spec in self.toolkit.specs() if spec.name in {
            "compose_ps",
            "api_health_check",
            "frontend_health_check",
            "nginx_proxy_check",
            "container_logs",
            "log_analyzer",
            "port_check",
        }]

    def _deterministic_plan(self, task: str, context: dict | None = None) -> list[AgentStep]:
        """根据问题关键词生成稳定诊断步骤。"""

        text = task.lower()
        steps = [
            AgentStep("检查 Compose 服务状态", "compose_ps", assigned_agent=self.name),
            AgentStep("检查后端健康接口", "api_health_check", assigned_agent=self.name),
            AgentStep("检查前端 Nginx 代理", "nginx_proxy_check", assigned_agent=self.name),
        ]
        if "前端" in task or "frontend" in text or "页面" in task:
            steps.append(AgentStep("检查前端入口", "frontend_health_check", assigned_agent=self.name))
        if any(key in text for key in ["502", "error", "exception", "日志", "报错"]):
            steps.append(AgentStep("分析后端日志", "log_analyzer", {"service": "ragent-api", "tail": 200}, self.name))
        else:
            steps.append(AgentStep("读取后端最近日志", "container_logs", {"service": "ragent-api", "tail": 120}, self.name))
        if any(key in text for key in ["端口", "connection refused", "连接拒绝"]):
            steps.append(AgentStep("检查后端端口连通性", "port_check", {"host": "localhost", "port": 8000}, self.name))
        return steps
