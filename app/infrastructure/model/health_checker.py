"""模块导读：本文件位于 app/infrastructure/model/health_checker.py，属于基础设施适配层。

主要职责：封装模型、MCP、会话等外部或底层依赖，降低业务代码耦合。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

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
        """check 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        return ModelHealth(provider=provider, model=model, healthy=bool(api_key), message="已配置 API Key" if api_key else "未配置 API Key")
