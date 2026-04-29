"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

from app.agents.base import AgentRole, AgentStep, BaseAgent, ToolSpec
from app.agents.tools import OpsToolkit


class ExecutorAgent(BaseAgent):
    """执行 Agent，负责生成需要审批的恢复动作。"""

    role = AgentRole.EXECUTOR
    name = "executor"
    description = "执行重启等运维动作，默认只生成审批请求。"

    def __init__(self, toolkit: OpsToolkit | None = None) -> None:
        self.toolkit = toolkit or OpsToolkit()
        super().__init__(self.toolkit.tools)

    def tool_specs(self) -> list[ToolSpec]:
        """当前只开放服务重启工具，且该工具必须审批。"""

        return [spec for spec in self.toolkit.specs() if spec.name == "compose_restart_service"]

    def _deterministic_plan(self, task: str, context: dict | None = None) -> list[AgentStep]:
        """根据用户描述选择要重启的服务。"""

        text = task.lower()
        service = "ragent-api"
        if "前端" in task or "frontend" in text or "nginx" in text:
            service = "ragent-frontend"
        return [
            AgentStep(
                title=f"申请重启服务 {service}",
                tool_name="compose_restart_service",
                args={"service": service},
                assigned_agent=self.name,
                reasoning="重启属于危险动作，必须等待管理员审批。",
            )
        ]
