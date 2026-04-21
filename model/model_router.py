"""
模型路由器
支持多模型优先级配置、健康检查和自动降级
"""
import logging
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
import httpx
from config import settings

logger = logging.getLogger(__name__)


class ModelStatus(Enum):
    """模型状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ModelConfig:
    """模型配置"""
    name: str                          # 模型名称
    provider: str                      # 提供商 (bailian/siliconflow/ollama)
    api_key: str                       # API Key
    api_base: str                      # API Base URL
    model_name: str                    # 具体模型名
    priority: int                      # 优先级（数字越小优先级越高）
    timeout: float = 30.0              # 超时时间（秒）
    max_retries: int = 3               # 最大重试次数
    status: ModelStatus = ModelStatus.UNKNOWN
    last_check_time: Optional[float] = None
    consecutive_failures: int = 0
    total_requests: int = 0
    failed_requests: int = 0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 1.0
        return 1.0 - (self.failed_requests / self.total_requests)


class ModelRouter:
    """模型路由器"""
    
    def __init__(self):
        """初始化模型路由器"""
        self.models: List[ModelConfig] = []
        self.current_model_index: int = 0
        self._initialize_models()
        
        logger.info(f"Model Router initialized with {len(self.models)} models")
    
    def _initialize_models(self):
        """初始化模型列表"""
        # 主模型：阿里云百炼
        self.models.append(ModelConfig(
            name="bailian-qwen-plus",
            provider="bailian",
            api_key=settings.OPENAI_API_KEY,
            api_base=settings.OPENAI_API_BASE,
            model_name=settings.CHAT_MODEL,
            priority=1,
            timeout=30.0
        ))
        
        # 备用模型1：SiliconFlow
        siliconflow_api_key = getattr(settings, 'SILICONFLOW_API_KEY', '')
        if siliconflow_api_key:
            self.models.append(ModelConfig(
                name="siliconflow-qwen",
                provider="siliconflow",
                api_key=siliconflow_api_key,
                api_base="https://api.siliconflow.cn/v1",
                model_name="Qwen/Qwen2.5-72B-Instruct",
                priority=2,
                timeout=20.0
            ))
        
        # 备用模型2：本地 Ollama
        ollama_base = getattr(settings, 'OLLAMA_API_BASE', 'http://localhost:11434')
        self.models.append(ModelConfig(
            name="ollama-local",
            provider="ollama",
            api_key="",  # Ollama 不需要 API Key
            api_base=ollama_base,
            model_name="qwen2.5:7b",
            priority=3,
            timeout=15.0
        ))
        
        # 按优先级排序
        self.models.sort(key=lambda m: m.priority)
    
    def get_available_model(self) -> Optional[ModelConfig]:
        """
        获取可用的模型（按优先级）
        
        Returns:
            可用的模型配置，如果都不可用则返回 None
        """
        for model in self.models:
            if model.status != ModelStatus.UNHEALTHY:
                return model
        
        # 如果所有模型都不健康，尝试重置状态
        logger.warning("All models are unhealthy, attempting reset")
        self._reset_all_models()
        
        # 返回优先级最高的模型
        return self.models[0] if self.models else None
    
    def get_fallback_model(self, current_model: ModelConfig) -> Optional[ModelConfig]:
        """
        获取降级模型
        
        Args:
            current_model: 当前失败的模型
            
        Returns:
            下一个可用的降级模型
        """
        current_index = self.models.index(current_model)
        
        # 尝试下一个优先级的模型
        for i in range(current_index + 1, len(self.models)):
            model = self.models[i]
            if model.status != ModelStatus.UNHEALTHY:
                logger.info(f"Falling back from {current_model.name} to {model.name}")
                return model
        
        logger.error("No fallback models available")
        return None
    
    async def check_model_health(self, model: ModelConfig) -> bool:
        """
        检查模型健康状态
        
        Args:
            model: 要检查的模型
            
        Returns:
            是否健康
        """
        try:
            start_time = time.time()
            
            # 发送一个简单的测试请求
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{model.api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {model.api_key}" if model.api_key else "",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model.model_name,
                        "messages": [{"role": "user", "content": "Hi"}],
                        "max_tokens": 5
                    }
                )
                
                elapsed = time.time() - start_time
                
                if response.status_code == 200:
                    self._mark_model_healthy(model)
                    logger.info(f"Model {model.name} is healthy (response time: {elapsed:.2f}s)")
                    return True
                else:
                    self._mark_model_unhealthy(model)
                    logger.warning(f"Model {model.name} health check failed: status={response.status_code}")
                    return False
                    
        except Exception as e:
            self._mark_model_unhealthy(model)
            logger.error(f"Model {model.name} health check error: {str(e)}")
            return False
    
    async def check_all_models_health(self) -> Dict[str, bool]:
        """
        检查所有模型的健康状态
        
        Returns:
            模型健康状态字典
        """
        results = {}
        
        for model in self.models:
            is_healthy = await self.check_model_health(model)
            results[model.name] = is_healthy
        
        return results
    
    def record_request(self, model: ModelConfig, success: bool):
        """
        记录请求结果
        
        Args:
            model: 使用的模型
            success: 是否成功
        """
        model.total_requests += 1
        
        if success:
            model.consecutive_failures = 0
            if model.status == ModelStatus.DEGRADED:
                model.status = ModelStatus.HEALTHY
        else:
            model.failed_requests += 1
            model.consecutive_failures += 1
            
            # 连续失败 3 次标记为不健康
            if model.consecutive_failures >= 3:
                self._mark_model_unhealthy(model)
    
    def _mark_model_healthy(self, model: ModelConfig):
        """标记模型为健康状态"""
        model.status = ModelStatus.HEALTHY
        model.consecutive_failures = 0
        model.last_check_time = time.time()
    
    def _mark_model_unhealthy(self, model: ModelConfig):
        """标记模型为不健康状态"""
        model.status = ModelStatus.UNHEALTHY
        model.last_check_time = time.time()
        logger.warning(f"Model {model.name} marked as UNHEALTHY")
    
    def _reset_all_models(self):
        """重置所有模型状态"""
        for model in self.models:
            model.status = ModelStatus.UNKNOWN
            model.consecutive_failures = 0
        logger.info("All model statuses reset")
    
    def get_model_stats(self) -> List[Dict[str, Any]]:
        """获取所有模型的统计信息"""
        stats = []
        
        for model in self.models:
            stats.append({
                "name": model.name,
                "provider": model.provider,
                "priority": model.priority,
                "status": model.status.value,
                "success_rate": f"{model.success_rate:.2%}",
                "total_requests": model.total_requests,
                "failed_requests": model.failed_requests,
                "consecutive_failures": model.consecutive_failures,
                "last_check_time": model.last_check_time
            })
        
        return stats
