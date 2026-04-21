"""
文档获取节点 (Fetcher Node)
从各种数据源获取文档原始字节
支持: 本地文件、HTTP URL、飞书文档、S3
"""
import logging
import requests
from typing import Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class FetcherNode:
    """文档获取节点"""
    
    def execute(self, context, settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行文档获取
        
        Args:
            context: Pipeline 上下文
            settings: 节点配置
            
        Returns:
            执行结果
        """
        try:
            source_type = settings.get("source_type", "upload")
            source_location = settings.get("source_location")
            
            if not source_location:
                return {"success": False, "error": "Source location is required"}
            
            # 如果上下文已有原始字节，跳过获取
            if context.raw_bytes and len(context.raw_bytes) > 0:
                logger.info("Raw bytes already exist in context, skipping fetch")
                return {"success": True}
            
            # 根据来源类型获取文档
            if source_type == "upload" or source_type == "file":
                self._fetch_from_file(context, source_location)
            elif source_type == "url":
                self._fetch_from_url(context, source_location)
            else:
                return {"success": False, "error": f"Unsupported source type: {source_type}"}
            
            logger.info(f"Document fetched successfully: size={len(context.raw_bytes)} bytes")
            return {"success": True}
            
        except Exception as e:
            logger.error(f"Fetcher node failed: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _fetch_from_file(self, context, file_path: str):
        """从本地文件获取"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        context.raw_bytes = path.read_bytes()
        context.mime_type = self._detect_mime_type(path.suffix.lower())
    
    def _fetch_from_url(self, context, url: str):
        """从 URL 获取"""
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        context.raw_bytes = response.content
        context.mime_type = response.headers.get("Content-Type", "application/octet-stream")
    
    def _detect_mime_type(self, extension: str) -> str:
        """根据文件扩展名检测 MIME 类型"""
        mime_map = {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".txt": "text/plain",
            ".md": "text/markdown",
        }
        return mime_map.get(extension, "application/octet-stream")
