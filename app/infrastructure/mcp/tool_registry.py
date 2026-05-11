"""模块导读：本文件位于 app/infrastructure/mcp/tool_registry.py，属于基础设施适配层。

主要职责：封装模型、MCP、会话等外部或底层依赖，降低业务代码耦合。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

from dataclasses import dataclass
from app.core.time_utils import to_shanghai_iso, shanghai_now
from typing import Awaitable, Callable


@dataclass
class MCPTool:
    """MCP 工具定义。"""

    name: str
    description: str
    category: str
    handler: Callable[..., Awaitable[dict]]


class ToolRegistry:
    """内置工具注册表，后续可扩展为外部 MCP Server 客户端。"""

    def __init__(self) -> None:
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
        self.tools = {
            "get_time": MCPTool("get_time", "获取当前时间", "system", self._get_time),
            "search_knowledge_base": MCPTool("search_knowledge_base", "检索知识库内容", "knowledge", self._search_kb),
            "get_weather": MCPTool("get_weather", "获取天气信息", "external", self._get_weather),
        }

    def list_tools(self) -> list[dict]:
        """list_tools 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
        return [
            {"name": item.name, "description": item.description, "category": item.category}
            for item in self.tools.values()
        ]

    async def call(self, name: str, **kwargs) -> dict:
        """call 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        tool = self.tools.get(name)
        if not tool:
            return {"success": False, "error": f"未知工具：{name}"}
        return await tool.handler(**kwargs)

    async def _get_time(self, **kwargs) -> dict:
        # MCP 时间工具直接返回东八区时间，避免前端或 Agent 二次猜测时区。
        """_get_time 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
        return {"success": True, "data": {"now": to_shanghai_iso(shanghai_now())}}

    async def _search_kb(self, query: str = "", top_k: int = 5, **kwargs) -> dict:
        """_search_kb 函数：执行检索逻辑，从知识库或索引中找出和用户问题最相关的内容。"""
        try:
            from app.rag.retrieval.multi_channel_retriever import MultiChannelRetriever

            rows = MultiChannelRetriever().retrieve(query, top_k=top_k)
            return {
                "success": True,
                "data": [
                    {"content": getattr(row, "content", getattr(row, "page_content", str(row))), "metadata": getattr(row, "metadata", {})}
                    for row in rows
                ],
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    async def _get_weather(self, location: str = "北京", **kwargs) -> dict:
        """_get_weather 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
        return {"success": True, "data": {"location": location, "summary": "天气工具未配置外部 API，当前返回占位说明。"}}
