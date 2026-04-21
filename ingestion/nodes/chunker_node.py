"""
文档分块节点 (Chunker Node)
将长文本切分为适合向量化的文本块
支持策略: 固定长度、语义分块
"""
import logging
from typing import Dict, Any, List
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


class ChunkerNode:
    """文档分块节点"""
    
    def execute(self, context, settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行文档分块
        
        Args:
            context: Pipeline 上下文
            settings: 节点配置
            
        Returns:
            执行结果
        """
        try:
            if not context.raw_text:
                return {"success": False, "error": "No text to chunk"}
            
            # 获取分块配置
            chunk_size = settings.get("chunk_size", 500)
            chunk_overlap = settings.get("chunk_overlap", 50)
            strategy = settings.get("strategy", "recursive")
            
            logger.info(f"Chunking document: strategy={strategy}, chunk_size={chunk_size}, overlap={chunk_overlap}")
            
            # 创建文本分割器
            if strategy == "recursive":
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    length_function=len,
                    separators=["\n\n", "\n", "。", ".", " ", ""]
                )
            else:
                # 默认使用递归分割
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                    length_function=len
                )
            
            # 执行分块
            texts = splitter.split_text(context.raw_text)
            
            # 构建 VectorChunk 对象列表
            from core.chunk import VectorChunk
            chunks = []
            for idx, text in enumerate(texts):
                chunk = VectorChunk(
                    chunk_id=f"{context.task_id}_chunk_{idx}",
                    content=text,
                    index=idx,
                    embedding=None,  # 稍后在 IndexerNode 中生成
                    metadata={
                        "source": context.metadata.get("source", "unknown"),
                        "chunk_index": idx,
                        "total_chunks": len(texts),
                    }
                )
                chunks.append(chunk)
            
            context.chunks = chunks
            logger.info(f"Document chunked successfully: total_chunks={len(chunks)}")
            return {"success": True}
            
        except Exception as e:
            logger.error(f"Chunker node failed: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
