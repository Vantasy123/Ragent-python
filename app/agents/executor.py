"""模块导读：本文件位于 app/agents/executor.py，属于Agent 编排层。

主要职责：描述智能体、工具调用、计划执行、审批边界和流式事件的运行方式。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

from app.agents.base import AgentRole, AgentStep, BaseAgent, ToolSpec
from app.agents.tools import OpsToolkit


class ExecutorAgent(BaseAgent):
    """执行 Agent，负责生成需要审批的恢复动作。"""

    role = AgentRole.EXECUTOR
    name = "executor"
    description = "执行重启等运维动作，默认只生成审批请求。"

    def __init__(self, toolkit: OpsToolkit | None = None) -> None:
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
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
