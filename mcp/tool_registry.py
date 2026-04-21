from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx
from sqlalchemy.orm import Session

from config import settings
from models import KnowledgeChunk


@dataclass
class MCPTool:
    name: str
    description: str
    category: str
    handler: Callable[[Session, dict[str, Any]], Awaitable[dict[str, Any]]]


class ToolRegistry:
    def __init__(self):
        self.tools = {
            "get_current_time": MCPTool("get_current_time", "获取当前时间", "utility", self._get_current_time),
            "get_weather": MCPTool("get_weather", "查询实时天气", "weather", self._get_weather),
            "search_knowledge_base": MCPTool("search_knowledge_base", "搜索知识库分块内容", "knowledge", self._search_kb),
        }

    def list_tools(self) -> list[dict]:
        return [{"name": tool.name, "description": tool.description, "category": tool.category} for tool in self.tools.values()]

    async def execute_tool(self, db: Session, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        tool = self.tools.get(tool_name)
        if not tool:
            return {"success": False, "error": f"Tool not found: {tool_name}"}
        result = await tool.handler(db, params)
        return {"success": True, "tool": tool_name, "result": result}

    async def _get_current_time(self, db: Session, params: dict[str, Any]) -> dict[str, Any]:
        now = dt.datetime.now()
        return {"current_time": now.strftime("%Y-%m-%d %H:%M:%S"), "timezone": "Asia/Shanghai"}

    async def _get_weather(self, db: Session, params: dict[str, Any]) -> dict[str, Any]:
        city = params.get("city", "Shanghai")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{settings.WEATHER_API_URL}/{city}", params={"format": "j1"})
                response.raise_for_status()
                payload = response.json()
                current = payload.get("current_condition", [{}])[0]
                return {
                    "city": city,
                    "temperatureC": current.get("temp_C"),
                    "description": current.get("weatherDesc", [{}])[0].get("value"),
                    "humidity": current.get("humidity"),
                }
        except Exception as exc:
            return {"city": city, "error": str(exc)}

    async def _search_kb(self, db: Session, params: dict[str, Any]) -> dict[str, Any]:
        query = params.get("query", "")
        kb_id = params.get("kb_id")
        q = db.query(KnowledgeChunk)
        if kb_id:
            q = q.filter(KnowledgeChunk.kb_id == kb_id)
        rows = q.filter(KnowledgeChunk.content.ilike(f"%{query}%")).limit(5).all()
        return {
            "query": query,
            "results": [
                {"id": row.id, "content": row.content[:200], "kbId": row.kb_id, "docId": row.doc_id}
                for row in rows
            ],
        }
