"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelHealth:
    """模型健康状态。"""

    provider: str
    model: str
    healthy: bool
    message: str = ""


class HealthChecker:
    """模型健康检查器，当前只做配置级检查。"""

    def check(self, provider: str, model: str, api_key: str | None = None) -> ModelHealth:
        return ModelHealth(provider=provider, model=model, healthy=bool(api_key), message="已配置 API Key" if api_key else "未配置 API Key")
