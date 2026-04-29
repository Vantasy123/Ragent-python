"""统一工具注册表，适配 MCP 工具与运维白名单工具。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.agents.base import ToolSpec
from app.agents.tools import OpsToolkit
from app.infrastructure.mcp.tool_registry import ToolRegistry


ToolHandler = Callable[..., Any | Awaitable[Any]]


@dataclass
class ToolCallRequest:
    """Agent 内部统一工具调用请求。"""

    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallResult:
    """Agent 内部统一工具调用结果。"""

    success: bool
    summary: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    risk_level: str = "read"
    requires_approval: bool = False
    source: str = "builtin"
    category: str = "general"

    def to_dict(self) -> dict[str, Any]:
        """转换成 SSE 和数据库可直接保存的结构。"""

        return {
            "success": self.success,
            "summary": self.summary,
            "data": self.data,
            "error": self.error,
            "riskLevel": self.risk_level,
            "requiresApproval": self.requires_approval,
            "source": self.source,
            "category": self.category,
        }


@dataclass
class UnifiedTool:
    """统一工具定义，屏蔽内置工具和 MCP 工具的调用差异。"""

    spec: ToolSpec
    handler: ToolHandler

    async def call(self, **kwargs: Any) -> ToolCallResult:
        """执行工具并规范化返回值。"""

        try:
            result = self.handler(**kwargs)
            if hasattr(result, "__await__"):
                result = await result
        except Exception as exc:
            return ToolCallResult(
                success=False,
                summary=f"工具调用失败：{exc}",
                error=type(exc).__name__,
                risk_level=self.spec.risk_level,
                requires_approval=self.spec.requires_approval,
                source=self.spec.source,
                category=self.spec.category,
            )

        if isinstance(result, ToolCallResult):
            return result

        payload = result if isinstance(result, dict) else {"data": result}
        success = bool(payload.get("success", False))
        data = payload.get("data")
        if not isinstance(data, dict):
            data = {"value": data}
        summary = payload.get("summary") or payload.get("error") or ("工具执行成功" if success else "工具执行失败")
        return ToolCallResult(
            success=success,
            summary=str(summary),
            data=data,
            error=str(payload.get("error") or ""),
            risk_level=str(payload.get("riskLevel") or self.spec.risk_level),
            requires_approval=self.spec.requires_approval,
            source=self.spec.source,
            category=self.spec.category,
        )

    def to_public_dict(self) -> dict[str, Any]:
        """返回前端工具目录需要的公开字段。"""

        return {
            "name": self.spec.name,
            "description": self.spec.description,
            "args_schema": self.spec.args_schema,
            "argsSchema": self.spec.args_schema,
            "risk_level": self.spec.risk_level,
            "riskLevel": self.spec.risk_level,
            "requires_approval": self.spec.requires_approval,
            "requiresApproval": self.spec.requires_approval,
            "source": self.spec.source,
            "category": self.spec.category,
            "enabledFor": self.spec.enabled_for,
        }


class UnifiedToolRegistry:
    """统一内置工具、MCP 工具和运维工具的注册表。"""

    def __init__(self, include_ops: bool = False, toolkit: OpsToolkit | None = None) -> None:
        self.include_ops = include_ops
        self.toolkit = toolkit or OpsToolkit()
        self.mcp_registry = ToolRegistry()
        self._tools: dict[str, UnifiedTool] = {}
        self._register_mcp_tools()
        if include_ops:
            self._register_ops_tools()

    @property
    def tools(self) -> dict[str, UnifiedTool]:
        """返回按名称索引的统一工具。"""

        return self._tools

    def list_tools(self, audience: str = "user") -> list[dict[str, Any]]:
        """按用户类型返回可见工具。"""

        return [
            tool.to_public_dict()
            for tool in self._tools.values()
            if audience in tool.spec.enabled_for or "all" in tool.spec.enabled_for
        ]

    async def call(self, request: ToolCallRequest) -> ToolCallResult:
        """执行统一工具调用，未知工具返回结构化失败。"""

        tool = self._tools.get(request.name)
        if tool is None:
            return ToolCallResult(success=False, summary=f"工具不存在：{request.name}", error="unknown_tool")
        if tool.spec.requires_approval:
            return ToolCallResult(
                success=False,
                summary=f"工具需要审批：{request.name}",
                error="approval_required",
                risk_level=tool.spec.risk_level,
                requires_approval=True,
                source=tool.spec.source,
                category=tool.spec.category,
            )
        return await tool.call(**request.args)

    def _register_mcp_tools(self) -> None:
        """把内置 MCP 工具注册为普通对话可用的安全工具。"""

        for item in self.mcp_registry.tools.values():
            spec = ToolSpec(
                name=item.name,
                description=item.description,
                args_schema=self._mcp_args_schema(item.name),
                risk_level="read",
                requires_approval=False,
                source="mcp",
                category=item.category,
                enabled_for=["user", "admin"],
            )
            self._tools[item.name] = UnifiedTool(spec=spec, handler=lambda _name=item.name, **kwargs: self.mcp_registry.call(_name, **kwargs))

        # 兼容运维 Planner 中更自然的知识库工具名。
        if "search_knowledge_base" in self._tools:
            original = self._tools["search_knowledge_base"]
            alias_spec = ToolSpec(
                name="knowledge_search",
                description=original.spec.description,
                args_schema={"query": "string", "topK": "integer"},
                risk_level="read",
                requires_approval=False,
                source="mcp",
                category="knowledge",
                enabled_for=["user", "admin"],
            )
            self._tools["knowledge_search"] = UnifiedTool(
                spec=alias_spec,
                handler=lambda **kwargs: self.mcp_registry.call(
                    "search_knowledge_base",
                    query=kwargs.get("query", ""),
                    top_k=kwargs.get("topK", kwargs.get("top_k", 5)),
                ),
            )

    def _register_ops_tools(self) -> None:
        """把运维白名单工具注册为管理员可用工具。"""

        for spec in self.toolkit.specs():
            spec.source = "builtin"
            spec.category = "ops"
            spec.enabled_for = ["admin"]
            handler = self.toolkit.tools.get(spec.name)
            if handler:
                self._tools[spec.name] = UnifiedTool(spec=spec, handler=handler)

    def _mcp_args_schema(self, name: str) -> dict[str, Any]:
        """为当前内置 MCP 工具补充轻量参数描述。"""

        if name == "search_knowledge_base":
            return {"query": "string", "top_k": "integer"}
        if name == "get_weather":
            return {"location": "string"}
        return {}
