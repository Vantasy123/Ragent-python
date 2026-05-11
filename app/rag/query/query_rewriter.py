"""基于最近会话历史的问题改写。"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


class QueryRewriter:
    """把依赖上下文的用户问题改写成可独立检索的查询。"""

    def __init__(self, llm: ChatOpenAI | None = None):
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
        self.llm = llm or ChatOpenAI(
            model=settings.CHAT_MODEL,
            temperature=0.0,
            streaming=False,
            openai_api_key=settings.OPENAI_API_KEY,
            openai_api_base=settings.OPENAI_API_BASE,
        )
        self.rewrite_prompt = """You are a search-query rewriting assistant.
Rewrite the latest user question into a clear standalone question using the recent conversation history.

Rules:
1. If the question is already standalone, return it unchanged.
2. Resolve pronouns and references such as it, this, that, the above, 这个, 它, 上述.
3. Keep the original intent. Do not add unsupported facts.
4. Output only the rewritten question.

Conversation history:
{history}

Latest user question:
{question}

Standalone question:"""

    def rewrite(self, question: str, chat_history: list[dict[str, Any]] | None = None) -> str:
        """rewrite 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        if not chat_history:
            return question

        history_text = self._format_history(chat_history)
        if len(history_text) < 20:
            return question

        try:
            prompt = self.rewrite_prompt.format(history=history_text, question=question)
            response = self.llm.invoke([HumanMessage(content=prompt)])
            rewritten_query = str(response.content).strip()
            if not rewritten_query:
                return question
            logger.info("Query rewritten: %s -> %s", question[:60], rewritten_query[:60])
            return rewritten_query
        except Exception as exc:
            logger.warning("Query rewriting failed, using original query: %s", exc)
            return question

    def _format_history(self, chat_history: list[dict[str, Any]]) -> str:
        """_format_history 函数：把内部数据整理成后续步骤需要的格式，避免业务逻辑到处重复拼装。"""
        lines: list[str] = []
        for msg in chat_history[-5:]:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "user":
                lines.append(f"User: {content}")
            elif role == "assistant":
                lines.append(f"Assistant: {content}")
        return "\n".join(lines)


