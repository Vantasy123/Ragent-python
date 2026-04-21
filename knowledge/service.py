"""
知识库服务层
提供知识库、文档、分块的业务逻辑
"""
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
import uuid

from models import KnowledgeBase, KnowledgeDocument, KnowledgeChunk
from ingestion.pipeline_engine import PipelineEngine, PipelineContext
from ingestion.nodes.fetcher_node import FetcherNode
from ingestion.nodes.parser_node import ParserNode
from ingestion.nodes.chunker_node import ChunkerNode
from ingestion.nodes.indexer_node import IndexerNode

logger = logging.getLogger(__name__)


class KnowledgeService:
    """知识库服务"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        # 初始化 Pipeline 引擎
        self.pipeline_engine = PipelineEngine(
            node_registry={
                "fetcher": FetcherNode(),
                "parser": ParserNode(),
                "chunker": ChunkerNode(),
                "indexer": IndexerNode(),
            }
        )
    
    # ==================== 知识库管理 ====================
    
    def create_knowledge_base(self, name: str, description: str = "", embedding_model: str = "text-embedding-v3") -> KnowledgeBase:
        """创建知识库"""
        kb_id = str(uuid.uuid4())
        collection_name = f"kb_{kb_id.replace('-', '_')}"
        
        kb = KnowledgeBase(
            id=kb_id,
            name=name,
            description=description,
            collection_name=collection_name,
            embedding_model=embedding_model,
            enabled=True,
        )
        
        self.db.add(kb)
        self.db.commit()
        self.db.refresh(kb)
        
        logger.info(f"Knowledge base created: id={kb_id}, name={name}")
        return kb
    
    def get_knowledge_base(self, kb_id: str) -> Optional[KnowledgeBase]:
        """获取知识库详情"""
        return self.db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    
    def list_knowledge_bases(self, page: int = 1, page_size: int = 10) -> Dict[str, Any]:
        """分页查询知识库列表"""
        query = self.db.query(KnowledgeBase).filter(KnowledgeBase.enabled == True)
        total = query.count()
        kbs = query.offset((page - 1) * page_size).limit(page_size).all()
        
        # 将 SQLAlchemy 模型转换为字典
        items = [
            {
                "id": kb.id,
                "name": kb.name,
                "description": kb.description,
                "collection_name": kb.collection_name,
                "embedding_model": kb.embedding_model,
                "enabled": kb.enabled,
                "created_at": kb.created_at.isoformat() if kb.created_at else None,
            }
            for kb in kbs
        ]
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items
        }
    
    def delete_knowledge_base(self, kb_id: str) -> bool:
        """删除知识库"""
        kb = self.get_knowledge_base(kb_id)
        if not kb:
            return False
        
        self.db.delete(kb)
        self.db.commit()
        logger.info(f"Knowledge base deleted: id={kb_id}")
        return True
    
    # ==================== 文档管理 ====================
    
    def upload_document(self, kb_id: str, doc_name: str, file_url: str, 
                       file_type: str, file_size: int, source_type: str = "upload",
                       chunk_strategy: str = "recursive", chunk_config: Dict = None) -> KnowledgeDocument:
        """上传文档"""
        kb = self.get_knowledge_base(kb_id)
        if not kb:
            raise ValueError(f"Knowledge base not found: {kb_id}")
        
        doc_id = str(uuid.uuid4())
        doc = KnowledgeDocument(
            id=doc_id,
            kb_id=kb_id,
            doc_name=doc_name,
            file_url=file_url,
            file_type=file_type,
            file_size=file_size,
            source_type=source_type,
            status="pending",
            process_mode="standard",
            chunk_strategy=chunk_strategy,
            chunk_config=chunk_config or {},
            enabled=True,
        )
        
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        
        logger.info(f"Document uploaded: doc_id={doc_id}, name={doc_name}")
        return doc
    
    def list_documents(self, kb_id: str, page: int = 1, page_size: int = 10) -> Dict[str, Any]:
        """分页查询知识库文档列表 - v2"""
        logger.info(f"DEBUG: list_documents called with kb_id={kb_id}, page={page}, page_size={page_size}")
        
        # 验证知识库存在
        kb = self.get_knowledge_base(kb_id)
        if not kb:
            raise ValueError(f"Knowledge base not found: {kb_id}")
        
        query = self.db.query(KnowledgeDocument).filter(
            KnowledgeDocument.kb_id == kb_id
        )
        total = query.count()
        docs = query.offset((page - 1) * page_size).limit(page_size).all()
        
        logger.info(f"list_documents: Found {len(docs)} documents for kb_id={kb_id}")
        logger.info(f"DEBUG: Type of first doc: {type(docs[0]) if docs else 'N/A'}")
        
        # 将 SQLAlchemy 模型转换为字典
        items = []
        for i, doc in enumerate(docs):
            logger.info(f"DEBUG: Converting document {i}: {doc.id}")
            item = {
                "id": doc.id,
                "kb_id": doc.kb_id,
                "doc_name": doc.doc_name,
                "file_type": doc.file_type,
                "file_size": doc.file_size,
                "source_type": doc.source_type,
                "status": doc.status,
                "chunk_count": doc.chunk_count,
                "enabled": doc.enabled,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            items.append(item)
            logger.debug(f"Converted document {doc.id} to dict")
        
        logger.info(f"list_documents: Returning {len(items)} items as dictionaries")
        logger.info(f"DEBUG: Type of first item: {type(items[0]) if items else 'N/A'}")
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items
        }
    
    def start_chunking(self, doc_id: str) -> bool:
        """开始文档分块处理"""
        doc = self.db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
        if not doc:
            raise ValueError(f"Document not found: {doc_id}")
        
        # 更新状态为处理中
        doc.status = "processing"
        self.db.commit()
        
        try:
            # 构建 Pipeline 定义
            pipeline_def = {
                "nodes": [
                    {"type": "fetcher", "settings": {
                        "source_type": doc.source_type,
                        "source_location": doc.file_url,
                    }},
                    {"type": "parser", "settings": {}},
                    {"type": "chunker", "settings": {
                        "chunk_size": doc.chunk_config.get("chunk_size", 500),
                        "chunk_overlap": doc.chunk_config.get("chunk_overlap", 50),
                        "strategy": doc.chunk_strategy or "recursive",
                    }},
                    {"type": "indexer", "settings": {}},
                ]
            }
            
            # 创建 Pipeline 上下文
            context = PipelineContext(task_id=doc_id, pipeline_id="default")
            context.metadata = {
                "doc_id": doc_id,
                "kb_id": doc.kb_id,
                "source": doc.doc_name,
            }
            
            # 执行 Pipeline
            result = self.pipeline_engine.execute(pipeline_def, context)
            
            if result.status == "completed":
                doc.status = "completed"
                doc.chunk_count = len(result.chunks)
                
                # 保存分块到数据库
                self._save_chunks_to_db(doc_id, doc.kb_id, result.chunks)
                
                logger.info(f"Document chunking completed: doc_id={doc_id}, chunks={len(result.chunks)}")
            else:
                doc.status = "failed"
                doc.error_message = str(result.error)
                logger.error(f"Document chunking failed: doc_id={doc_id}, error={result.error}")
            
            self.db.commit()
            return result.status == "completed"
            
        except Exception as e:
            doc.status = "failed"
            doc.error_message = str(e)
            self.db.commit()
            logger.error(f"Document chunking error: doc_id={doc_id}, error={str(e)}", exc_info=True)
            return False
    
    def _save_chunks_to_db(self, doc_id: str, kb_id: str, chunks: List):
        """保存分块到数据库"""
        for chunk in chunks:
            db_chunk = KnowledgeChunk(
                id=chunk.chunk_id,
                doc_id=doc_id,
                kb_id=kb_id,
                content=chunk.content,
                chunk_index=chunk.index,
                metadata=chunk.metadata,
                enabled=True,
            )
            self.db.add(db_chunk)
    
    def get_document(self, doc_id: str) -> Optional[KnowledgeDocument]:
        """获取文档详情"""
        return self.db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
    
    def delete_document(self, doc_id: str) -> bool:
        """删除文档"""
        doc = self.get_document(doc_id)
        if not doc:
            return False
        
        # 从向量库删除
        from vector_store import vector_store
        kb = self.get_knowledge_base(doc.kb_id)
        if kb:
            try:
                # 删除该文档的所有向量
                filter_expr = f'metadata["doc_id"] == "{doc_id}"'
                # 注意：不同向量库的删除API可能不同，这里需要根据实际实现调整
                logger.info(f"Deleting vectors for document: doc_id={doc_id}")
            except Exception as e:
                logger.error(f"Failed to delete vectors: {str(e)}")
        
        self.db.delete(doc)
        self.db.commit()
        logger.info(f"Document deleted: id={doc_id}")
        return True
    
    def enable_document(self, doc_id: str, enabled: bool) -> bool:
        """启用/禁用文档"""
        doc = self.get_document(doc_id)
        if not doc:
            return False
        
        doc.enabled = enabled
        self.db.commit()
        logger.info(f"Document {'enabled' if enabled else 'disabled'}: id={doc_id}")
        return True
