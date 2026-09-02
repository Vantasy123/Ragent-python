"""模块导读：本文件位于 app/rag/workflow.py，属于RAG 问答链路。

主要职责：处理问题改写、知识检索、结果融合、重排和最终回答生成。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.rag.query.query_rewriter import QueryRewriter
from app.rag.retrieval.multi_channel_retriever import MultiChannelRetriever
from app.rag.retrieval.reranker import RerankerService
from app.services.settings_service import get_runtime_settings


query_rewriter = QueryRewriter()
multi_channel_retriever = MultiChannelRetriever()
reranker = RerankerService()


def build_primary_llm(streaming: bool = True, model: str | None = None) -> ChatOpenAI:
    """构建聊天模型；支持指定子任务模型，未指定时默认使用 CHAT_MODEL。"""

    runtime = get_runtime_settings()
    api_key = settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY
    selected_model = model or settings.CHAT_MODEL
    if settings.LANGCHAIN_TRACING_V2 and settings.LANGCHAIN_API_KEY:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.LANGCHAIN_API_KEY)
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.LANGCHAIN_PROJECT)
        os.environ.setdefault("LANGCHAIN_ENDPOINT", settings.LANGCHAIN_ENDPOINT)
    return ChatOpenAI(
        model=selected_model,
        api_key=api_key,
        base_url=settings.OPENAI_API_BASE,
        temperature=runtime.temperature,
        streaming=streaming,
    )
