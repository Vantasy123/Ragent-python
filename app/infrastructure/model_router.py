"""大模型统一调用与路由适配层，提供简单稳定的 chat 接口与容错。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.core.config import settings
from app.rag.workflow import build_primary_llm

logger = logging.getLogger(__name__)


class ModelRouter:
    """提供统一的同步/异步模型调用入口。"""

    def __init__(self):
        pass

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        timeout: float = 15.0,
        model: Optional[str] = None,
    ) -> str:
        """同步调用大模型并返回完整文本响应，支持指定角色模型。"""
        api_key = settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY
        if not api_key or "your-api-key" in api_key or "test" in api_key:
            raise RuntimeError("API key is not configured or in test mode")

        try:
            llm = build_primary_llm(streaming=False, model=model)
            llm.temperature = temperature
            llm.request_timeout = timeout
            
            lc_messages = []
            for m in messages:
                role = m.get("role", "user")
                content = m.get("content", "")
                if role == "system":
                    lc_messages.append(SystemMessage(content=content))
                elif role == "assistant":
                    lc_messages.append(AIMessage(content=content))
                else:
                    lc_messages.append(HumanMessage(content=content))
            
            res = llm.invoke(lc_messages)
            return str(res.content if hasattr(res, "content") else res)
        except Exception as e:
            logger.warning(f"ModelRouter 调用失败: {e}")
            raise e
