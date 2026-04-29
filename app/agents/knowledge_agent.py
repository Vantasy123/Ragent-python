"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

from app.agents.base import AgentRole, AgentStep, BaseAgent, ToolSpec


class KnowledgeAgent(BaseAgent):
    """知识 Agent，负责从知识库检索历史故障和项目说明。"""

    role = AgentRole.KNOWLEDGE
    name = "knowledge"
    description = "检索知识库，补充历史经验和排障文档。"

    def tool_specs(self) -> list[ToolSpec]:
        """知识 Agent 当前只暴露知识库检索工具。"""

        return [ToolSpec("knowledge_search", "检索知识库内容", {"query": "string", "topK": "integer"})]

    def _deterministic_plan(self, task: str, context: dict | None = None) -> list[AgentStep]:
        """所有运维问题都先尝试查找历史经验。"""

        return [AgentStep("检索运维知识库", "knowledge_search", {"query": task, "topK": 5}, self.name)]

    async def execute_step(self, step: AgentStep) -> dict:
        """执行知识库检索，并把片段裁剪成适合前端展示的摘要。"""

        if step.tool_name != "knowledge_search":
            return await super().execute_step(step)
        try:
            from app.rag.retrieval.multi_channel_retriever import MultiChannelRetriever

            retriever = MultiChannelRetriever()
            rows = retriever.retrieve(step.args.get("query", ""), top_k=int(step.args.get("topK", 5)))
            data = [
                {
                    "content": getattr(row, "page_content", str(row))[:500],
                    "metadata": getattr(row, "metadata", {}),
                }
                for row in rows
            ]
            return {"success": True, "summary": f"检索到 {len(data)} 条知识片段", "data": {"chunks": data}}
        except Exception as exc:
            return {"success": False, "summary": f"知识检索失败：{exc}", "data": {}, "error": type(exc).__name__}
