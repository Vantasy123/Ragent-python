"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.rag.query.query_rewriter import QueryRewriter
from app.rag.retrieval.multi_channel_retriever import MultiChannelRetriever
from app.rag.retrieval.reranker import RerankerService
from app.services.settings_service import get_runtime_settings


query_rewriter = QueryRewriter()
multi_channel_retriever = MultiChannelRetriever()
reranker = RerankerService()


def build_primary_llm(streaming: bool = True) -> ChatOpenAI:
    """构建主聊天模型；运行时温度从系统设置读取，模型名仍来自环境配置。"""

    runtime = get_runtime_settings()
    api_key = settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY
    return ChatOpenAI(
        model=settings.CHAT_MODEL,
        api_key=api_key,
        base_url=settings.OPENAI_API_BASE,
        temperature=runtime.temperature,
        streaming=streaming,
    )


class SimpleAppGraph:
    """兼容旧测试导入的轻量工作流对象。"""

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        question = state.get("question") or state.get("input") or ""
        docs = multi_channel_retriever.retrieve(question, top_k=get_runtime_settings().top_k)
        return {"question": question, "documents": docs}


app_graph = SimpleAppGraph()
