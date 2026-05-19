"""Agent 基础类型与执行骨架，定义步骤、工具元数据和事件流协议。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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


class BaseAgent:
    """所有 Agent 的最小基类，只保留身份和工具元数据入口。"""

    role: AgentRole = AgentRole.DIAGNOSTICS
    name: str = "base"
    description: str = ""

    def __init__(self, tools: dict[str, Any] | None = None) -> None:
        # tools 由 OpsToolkit 注入，避免 Agent 自己创建任意执行能力。
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
        self.tools = tools or {}

    def tool_specs(self) -> list[ToolSpec]:
        """子类覆盖此方法声明自己可以使用的工具。"""

        return []
