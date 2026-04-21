"""
Rerank 重排序服务
使用交叉编码器对检索结果进行精排
"""
import logging
from typing import List, Optional
from config import settings

logger = logging.getLogger(__name__)


class RerankerService:
    """Rerank 重排序服务"""
    
    def __init__(self):
        self.reranker = None
        self._initialize_reranker()
    
    def _initialize_reranker(self):
        """初始化 Rerank 模型"""
        try:
            # 尝试使用 FlagEmbedding（本地模型）
            from FlagEmbedding import FlagReranker
            self.reranker = FlagReranker('BAAI/bge-reranker-large', use_fp16=True)
            logger.info("Reranker initialized with BGE model")
        except ImportError:
            logger.warning("FlagEmbedding not installed, reranking disabled")
            self.reranker = None
        except Exception as e:
            logger.error(f"Failed to initialize reranker: {str(e)}")
            self.reranker = None
    
    def rerank(
        self, 
        query: str, 
        documents: List[str],
        top_k: Optional[int] = None
    ) -> List[dict]:
        """
        对文档列表进行重排序
        
        Args:
            query: 查询文本
            documents: 待排序的文档列表
            top_k: 返回前 K 个结果
            
        Returns:
            重排序后的结果列表，包含 index 和 score
        """
        if not self.reranker:
            logger.warning("Reranker not available, returning original order")
            return [{"index": i, "score": 0.0} for i in range(len(documents))]
        
        if not documents:
            return []
        
        try:
            # 构建查询-文档对
            pairs = [[query, doc] for doc in documents]
            
            # 计算相关性分数
            scores = self.reranker.compute_score(pairs, normalize=True)
            
            # 如果只有一个文档，scores 是 float，需要转换为列表
            if isinstance(scores, float):
                scores = [scores]
            
            # 构建结果
            results = [
                {"index": i, "score": float(score)}
                for i, score in enumerate(scores)
            ]
            
            # 按分数降序排序
            results.sort(key=lambda x: x["score"], reverse=True)
            
            # 截取 top_k
            if top_k:
                results = results[:top_k]
            
            logger.info(f"Reranking completed: input={len(documents)}, output={len(results)}")
            
            return results
            
        except Exception as e:
            logger.error(f"Reranking failed: {str(e)}", exc_info=True)
            # 失败时返回原始顺序
            return [{"index": i, "score": 0.0} for i in range(len(documents))]
    
    def rerank_with_threshold(
        self,
        query: str,
        documents: List[str],
        threshold: float = None
    ) -> List[dict]:
        """
        带阈值过滤的重排序
        
        Args:
            query: 查询文本
            documents: 待排序的文档列表
            threshold: 分数阈值，低于此分数的文档被过滤
            
        Returns:
            通过阈值的重排序结果
        """
        if threshold is None:
            threshold = settings.RERANK_THRESHOLD
        
        results = self.rerank(query, documents)
        
        # 过滤低分数结果
        filtered_results = [r for r in results if r["score"] >= threshold]
        
        logger.info(f"Rerank with threshold: total={len(results)}, passed={len(filtered_results)}, threshold={threshold}")
        
        return filtered_results
