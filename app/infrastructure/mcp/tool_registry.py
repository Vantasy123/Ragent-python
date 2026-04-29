"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

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
        self.tools = {
            "get_time": MCPTool("get_time", "获取当前时间", "system", self._get_time),
            "search_knowledge_base": MCPTool("search_knowledge_base", "检索知识库内容", "knowledge", self._search_kb),
            "get_weather": MCPTool("get_weather", "获取天气信息", "external", self._get_weather),
        }

    def list_tools(self) -> list[dict]:
        return [
            {"name": item.name, "description": item.description, "category": item.category}
            for item in self.tools.values()
        ]

    async def call(self, name: str, **kwargs) -> dict:
        tool = self.tools.get(name)
        if not tool:
            return {"success": False, "error": f"未知工具：{name}"}
        return await tool.handler(**kwargs)

    async def _get_time(self, **kwargs) -> dict:
        # MCP 时间工具直接返回东八区时间，避免前端或 Agent 二次猜测时区。
        return {"success": True, "data": {"now": to_shanghai_iso(shanghai_now())}}

    async def _search_kb(self, query: str = "", top_k: int = 5, **kwargs) -> dict:
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
        return {"success": True, "data": {"location": location, "summary": "天气工具未配置外部 API，当前返回占位说明。"}}
