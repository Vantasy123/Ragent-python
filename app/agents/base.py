"""Agent 基础类型与执行骨架，定义步骤、工具元数据和事件流协议。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator


class AgentRole(str, Enum):
    """多 Agent 协作中的固定角色。"""

    ORCHESTRATOR = "orchestrator"
    DIAGNOSTICS = "diagnostics"
    MONITOR = "monitor"
    EXECUTOR = "executor"
    KNOWLEDGE = "knowledge"


class StepStatus(str, Enum):
    """Agent 步骤状态，前端时间线和数据库持久化都使用这些值。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class ToolSpec:
    """工具元数据。

    requires_approval 是安全边界的关键字段：
    - False：只读工具，可由 Agent 自动执行。
    - True：写操作工具，只产生审批事件，不直接执行。
    """

    name: str
    description: str
    args_schema: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "read"
    requires_approval: bool = False
    source: str = "builtin"
    category: str = "general"
    enabled_for: list[str] = field(default_factory=lambda: ["admin"])


@dataclass
class AgentStep:
    """单个 Agent 计划步骤。"""

    title: str
    tool_name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    assigned_agent: str = ""
    status: StepStatus = StepStatus.PENDING
    observation: str = ""
    reasoning: str = ""


@dataclass
class SubTask:
    """编排器拆解后分配给子 Agent 的任务。"""

    agent: str
    task: str
    reason: str = ""


@dataclass
class AgentResult:
    """Agent 执行结果，保留给后续非 SSE 调用场景使用。"""

    agent: str
    status: str
    steps: list[AgentStep] = field(default_factory=list)
    report: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class BaseAgent:
    """所有 Agent 的最小基类。

    这里刻意保持框架很薄：
    - plan 只负责产出步骤。
    - execute_step 只负责调用白名单工具。
    - run 负责把计划、工具调用、观察、总结转换为 SSE 事件。
    """

    role: AgentRole = AgentRole.DIAGNOSTICS
    name: str = "base"
    description: str = ""

    def __init__(self, tools: dict[str, Any] | None = None) -> None:
        # tools 由 OpsToolkit 注入，避免 Agent 自己创建任意执行能力。
        self.tools = tools or {}

    def tool_specs(self) -> list[ToolSpec]:
        """子类覆盖此方法声明自己可以使用的工具。"""

        return []

    async def plan(self, task: str, context: dict[str, Any] | None = None) -> list[AgentStep]:
        """生成执行计划。

        首期使用确定性计划，避免 LLM 不可用时运维诊断完全不可用。
        后续可以在这里接入 LLM Planner，但必须保留确定性回退。
        """

        return self._deterministic_plan(task, context or {})

    def _deterministic_plan(self, task: str, context: dict[str, Any] | None = None) -> list[AgentStep]:
        """默认计划，只输出一个说明性步骤。"""

        return [AgentStep(title="分析问题并给出建议", assigned_agent=self.name)]

    async def execute_step(self, step: AgentStep) -> dict[str, Any]:
        """执行单步工具调用。

        未知工具返回结构化失败结果，而不是抛异常中断整个 Agent。
        """

        if not step.tool_name:
            return {"success": True, "summary": step.title, "data": {}, "riskLevel": "read"}

        tool = self.tools.get(step.tool_name)
        if tool is None:
            return {
                "success": False,
                "summary": f"工具不存在：{step.tool_name}",
                "data": {},
                "error": "unknown_tool",
                "riskLevel": "read",
            }

        result = tool(**step.args)
        if hasattr(result, "__await__"):
            result = await result
        return result

    async def reflect(self, task: str, steps: list[AgentStep]) -> str:
        """根据步骤执行结果生成简短反思结论。"""

        failed = [step for step in steps if step.status == StepStatus.FAILED]
        if failed:
            return f"任务存在 {len(failed)} 个失败步骤，建议先查看失败工具的错误信息。"
        blocked = [step for step in steps if step.status == StepStatus.BLOCKED]
        if blocked:
            return f"有 {len(blocked)} 个步骤等待审批，审批后才能继续执行写操作。"
        return f"已完成 {self.name} 的检查步骤。"

    async def run(self, task: str, context: dict[str, Any] | None = None) -> AsyncIterator[dict[str, Any]]:
        """以事件流输出完整执行过程。"""

        steps = await self.plan(task, context)
        yield {"type": "agent_plan", "agent": self.name, "steps": [self._step_to_dict(step) for step in steps]}

        for index, step in enumerate(steps):
            step.assigned_agent = step.assigned_agent or self.name
            spec = next((item for item in self.tool_specs() if item.name == step.tool_name), None)

            # 写操作只产生审批事件，不在这里直接执行。
            if spec and spec.requires_approval:
                step.status = StepStatus.BLOCKED
                yield {
                    "type": "approval_required",
                    "agent": self.name,
                    "stepIndex": index,
                    "tool": step.tool_name,
                    "args": step.args,
                    "riskLevel": spec.risk_level,
                }
                continue

            step.status = StepStatus.RUNNING
            yield {"type": "tool_call", "agent": self.name, "stepIndex": index, "tool": step.tool_name, "args": step.args}
            try:
                result = await self.execute_step(step)
                step.status = StepStatus.SUCCESS if result.get("success", False) else StepStatus.FAILED
                step.observation = result.get("summary") or json.dumps(result, ensure_ascii=False)
                yield {"type": "observation", "agent": self.name, "stepIndex": index, "result": result}
            except Exception as exc:  # pragma: no cover - 单工具失败不应打断整个 SSE 连接。
                step.status = StepStatus.FAILED
                step.observation = str(exc)
                yield {"type": "error", "agent": self.name, "stepIndex": index, "error": str(exc)}

        report = await self.reflect(task, steps)
        yield {"type": "agent_done", "agent": self.name, "status": "completed", "report": report}

    def _step_to_dict(self, step: AgentStep) -> dict[str, Any]:
        """将步骤转换为 JSON 可序列化结构，避免 Enum 直接进入 SSE。"""

        data = step.__dict__.copy()
        data["status"] = step.status.value if isinstance(step.status, StepStatus) else str(step.status)
        return data
