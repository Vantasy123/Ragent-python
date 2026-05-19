"""统一工具注册表，适配 MCP 工具与运维白名单工具。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.agents.base import ToolSpec
from app.agents.tools import OpsToolkit
from app.infrastructure.mcp.tool_registry import ToolRegistry


ToolHandler = Callable[..., Any | Awaitable[Any]]
MAX_SUMMARY_CHARS = 1000
MAX_DATA_STRING_CHARS = 2000
MAX_LIST_ITEMS = 50


def _compact_value(value: Any, *, max_string_chars: int = MAX_DATA_STRING_CHARS) -> Any:
    """压缩工具输出中的大字段，避免日志或 inspect 结果撑爆 SSE、Trace 和数据库。"""

    if isinstance(value, str):
        if len(value) <= max_string_chars:
            return value
        return {
            "preview": value[:max_string_chars],
            "truncated": True,
            "originalLength": len(value),
        }
    if isinstance(value, list):
        compacted = [_compact_value(item, max_string_chars=max_string_chars) for item in value[:MAX_LIST_ITEMS]]
        if len(value) > MAX_LIST_ITEMS:
            compacted.append({"truncated": True, "originalLength": len(value)})
        return compacted
    if isinstance(value, dict):
        return {str(key): _compact_value(item, max_string_chars=max_string_chars) for key, item in value.items()}
    return value


def compact_tool_result_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """返回可对外展示和持久化的工具结果摘要。"""

    compacted = dict(payload)
    summary = str(compacted.get("summary") or "")
    if len(summary) > MAX_SUMMARY_CHARS:
        compacted["summary"] = summary[:MAX_SUMMARY_CHARS]
        compacted["summaryTruncated"] = True
        compacted["summaryOriginalLength"] = len(summary)
    data = compacted.get("data")
    compacted["data"] = _compact_value(data if isinstance(data, dict) else {"value": data})
    return compacted


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

        return compact_tool_result_dict({
            "success": self.success,
            "summary": self.summary,
            "data": self.data,
            "error": self.error,
            "riskLevel": self.risk_level,
            "requiresApproval": self.requires_approval,
            "source": self.source,
            "category": self.category,
        })


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

        is_read_only = self.spec.risk_level == "read" and not self.spec.requires_approval
        return {
            "name": self.spec.name,
            "description": self.spec.description,
            "args_schema": self.spec.args_schema,
            "argsSchema": self.spec.args_schema,
            "risk_level": self.spec.risk_level,
            "riskLevel": self.spec.risk_level,
            "requires_approval": self.spec.requires_approval,
            "requiresApproval": self.spec.requires_approval,
            "is_read_only": is_read_only,
            "isReadOnly": is_read_only,
            "source": self.spec.source,
            "category": self.spec.category,
            "enabledFor": self.spec.enabled_for,
        }


class UnifiedToolRegistry:
    """统一内置工具、MCP 工具和运维工具的注册表。"""

    def __init__(self, include_ops: bool = False, toolkit: OpsToolkit | None = None) -> None:
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
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

    async def call(self, request: ToolCallRequest, *, skip_approval: bool = False) -> ToolCallResult:
        """执行统一工具调用，未知工具返回结构化失败。"""

        tool = self._tools.get(request.name)
        if tool is None:
            return ToolCallResult(success=False, summary=f"工具不存在：{request.name}", error="unknown_tool")
        if tool.spec.requires_approval and not skip_approval:
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
