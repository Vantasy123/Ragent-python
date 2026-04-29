"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


@dataclass
class ModelRoute:
    """模型路由结果。"""

    provider: str
    model: str
    base_url: str
    api_key: str


class ModelRouter:
    """主模型 + fallback 的简单路由器。"""

    def select_chat_model(self) -> ModelRoute:
        return ModelRoute(
            provider="openai-compatible",
            model=settings.CHAT_MODEL,
            base_url=settings.OPENAI_API_BASE,
            api_key=settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY,
        )
