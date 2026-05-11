"""模块导读：本文件位于 app/infrastructure/model/model_router.py，属于基础设施适配层。

主要职责：封装模型、MCP、会话等外部或底层依赖，降低业务代码耦合。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

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
        """select_chat_model 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        return ModelRoute(
            provider="openai-compatible",
            model=settings.CHAT_MODEL,
            base_url=settings.OPENAI_API_BASE,
            api_key=settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY,
        )
