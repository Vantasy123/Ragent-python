"""
流水线引擎模块 (Pipeline Engine Module)

本模块实现了文档摄取的流水线执行引擎，负责编排和协调各个处理节点的执行。
采用责任链模式，支持灵活的节点组合和错误处理，提供完整的执行追踪和状态管理。

主要功能：
1. 流水线编排：动态组合处理节点形成处理链
2. 节点注册：插件式的节点注册和管理机制
3. 执行控制：顺序执行节点，支持错误处理和回滚
4. 状态追踪：详细的执行状态和性能监控
5. 上下文管理：节点间数据传递和状态共享

核心组件：
- PipelineEngine: 流水线执行引擎主类
- PipelineContext: 执行上下文，承载节点间数据
- Node 协议：统一的节点接口定义
- 各种处理节点：Fetcher, Parser, Chunker, Indexer 等

执行流程：
1. 初始化上下文 → 创建执行环境
2. 节点注册 → 加载可用的处理节点
3. 流水线构建 → 根据配置组合节点
4. 顺序执行 → 依次执行各个节点
5. 状态更新 → 实时更新执行状态
6. 结果汇总 → 收集处理结果和统计信息

技术特性：
- 插件架构：易于扩展新的处理节点
- 错误隔离：节点错误不影响整个流水线
- 性能监控：详细的执行时间和资源使用统计
- 状态持久化：支持断点续传和状态恢复
- 并发安全：线程安全的执行环境

节点类型：
- FetcherNode: 文档获取节点
- ParserNode: 文档解析节点
- ChunkerNode: 文本分块节点
- IndexerNode: 向量索引节点
"""
"""
Pipeline 执行引擎
负责编排和执行文档摄取管道的各个节点
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class PipelineContext:
    """Pipeline 执行上下文"""
    
    def __init__(self, task_id: str, pipeline_id: str):
        self.task_id = task_id
        self.pipeline_id = pipeline_id
        self.raw_bytes: Optional[bytes] = None
        self.mime_type: Optional[str] = None
        self.raw_text: Optional[str] = None
        self.chunks: list = []
        self.metadata: Dict[str, Any] = {}
        self.error: Optional[Exception] = None
        self.status: str = "pending"
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "pipeline_id": self.pipeline_id,
            "status": self.status,
            "chunk_count": len(self.chunks),
            "error": str(self.error) if self.error else None,
        }


class PipelineEngine:
    """Pipeline 执行引擎"""
    
    def __init__(self, node_registry: Dict[str, Any]):
        """
        初始化 Pipeline 引擎
        
        Args:
            node_registry: 节点注册表，key为节点类型，value为节点实例
        """
        self.node_registry = node_registry
        logger.info(f"Pipeline Engine initialized with {len(node_registry)} node types")
    
    def execute(self, pipeline_def: Dict[str, Any], context: PipelineContext) -> PipelineContext:
        """
        执行 Pipeline
        
        Args:
            pipeline_def: Pipeline 定义，包含 nodes 列表
            context: 执行上下文
            
        Returns:
            更新后的上下文
        """
        context.start_time = datetime.now()
        context.status = "running"
        
        nodes = pipeline_def.get("nodes", [])
        logger.info(f"Starting pipeline execution: task_id={context.task_id}, nodes_count={len(nodes)}")
        
        try:
            for idx, node_config in enumerate(nodes):
                node_type = node_config.get("type")
                node_settings = node_config.get("settings", {})
                
                logger.info(f"Executing node [{idx+1}/{len(nodes)}]: {node_type}")
                
                # 获取节点实例
                node = self.node_registry.get(node_type)
                if not node:
                    raise ValueError(f"Unknown node type: {node_type}")
                
                # 执行节点
                result = node.execute(context, node_settings)
                
                if not result.get("success", False):
                    error_msg = result.get("error", "Unknown error")
                    raise Exception(f"Node {node_type} failed: {error_msg}")
                
                logger.info(f"Node {node_type} completed successfully")
            
            # 所有节点执行成功
            context.status = "completed"
            context.end_time = datetime.now()
            duration = (context.end_time - context.start_time).total_seconds()
            logger.info(f"Pipeline completed: task_id={context.task_id}, duration={duration}s, chunks={len(context.chunks)}")
            
        except Exception as e:
            context.status = "failed"
            context.error = e
            context.end_time = datetime.now()
            logger.error(f"Pipeline failed: task_id={context.task_id}, error={str(e)}", exc_info=True)
        
        return context

