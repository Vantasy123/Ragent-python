"""模块导读：本文件位于 app/rag/workflow.py，属于RAG 问答链路。

主要职责：处理问题改写、知识检索、结果融合、重排和最终回答生成。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

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

