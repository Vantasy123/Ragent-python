"""
模型健康检查器
定期后台检查模型可用性
"""
import logging
import asyncio
from typing import Dict
from model.model_router import ModelRouter

logger = logging.getLogger(__name__)


class HealthChecker:
    """模型健康检查器"""
    
    def __init__(self, model_router: ModelRouter):
        """
        初始化健康检查器
        
        Args:
            model_router: 模型路由器实例
        """
        self.model_router = model_router
        self.check_interval = 60  # 检查间隔（秒）
        self.is_running = False
        self._task = None
    
    async def start(self):
        """启动后台健康检查"""
        if self.is_running:
            logger.warning("Health checker is already running")
            return
        
        self.is_running = True
        self._task = asyncio.create_task(self._check_loop())
        logger.info("Health checker started")
    
    async def stop(self):
        """停止后台健康检查"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Health checker stopped")
    
    async def _check_loop(self):
        """健康检查循环"""
        while self.is_running:
            try:
                await self._perform_health_check()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {str(e)}")
                await asyncio.sleep(10)  # 出错后等待 10 秒再重试
    
    async def _perform_health_check(self):
        """执行健康检查"""
        logger.debug("Performing health check for all models")
        
        results = await self.model_router.check_all_models_health()
        
        for model_name, is_healthy in results.items():
            status = "✅ HEALTHY" if is_healthy else "❌ UNHEALTHY"
            logger.info(f"Model {model_name}: {status}")
    
    def get_status(self) -> Dict:
        """获取健康检查器状态"""
        return {
            "is_running": self.is_running,
            "check_interval": self.check_interval,
            "models": self.model_router.get_model_stats()
        }
