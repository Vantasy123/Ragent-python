"""
知识库服务模块 (Knowledge Service Module)

本模块实现了知识库的核心业务逻辑，负责文档处理、向量化存储和检索服务。
使用流水线引擎处理文档摄取，支持多种文档格式和分块策略。

主要功能：
1. 知识库管理：创建、查询、更新、删除知识库
2. 文档处理：上传、解析、分块、向量化文档
3. 检索服务：基于向量的相似度搜索和重排
4. 流水线处理：异步文档处理流水线
5. 分块策略：多种文本分块算法支持

核心组件：
- KnowledgeService: 主要业务逻辑类
- PipelineEngine: 文档处理流水线引擎
- 各种处理节点：FetcherNode, ParserNode, ChunkerNode, IndexerNode

处理流程：
1. 文档上传 → 存储到文件系统
2. 文档解析 → 提取文本内容
3. 文本分块 → 根据策略分割文档
4. 向量化 → 转换为向量存储
5. 检索服务 → 相似度搜索和重排

技术特性：
- 异步处理：非阻塞的文档处理
- 多种格式：支持 PDF、TXT、MD、DOCX 等
- 灵活分块：字符级、句子级、段落级分块
- 向量检索：基于 PGVector 的高效检索
- 权限控制：基于用户的访问控制
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from config import settings
from ingestion.pipeline_engine import PipelineContext, PipelineEngine
from ingestion.nodes.chunker_node import ChunkerNode
from ingestion.nodes.fetcher_node import FetcherNode
from ingestion.nodes.indexer_node import IndexerNode
from ingestion.nodes.parser_node import ParserNode
from models import KnowledgeBase, KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentChunkLog


class KnowledgeService:
    def __init__(self, db: Session):
        self.db = db
        self.pipeline_engine = PipelineEngine(
            node_registry={
                "fetcher": FetcherNode(),
                "parser": ParserNode(),
                "chunker": ChunkerNode(),
                "indexer": IndexerNode(),
            }
        )

    def list_chunk_strategies(self) -> list[dict]:
        return [
            {"value": "recursive", "label": "Recursive"},
            {"value": "fixed", "label": "Fixed Size"},
            {"value": "markdown", "label": "Markdown"},
        ]

    def create_kb(self, name: str, description: str = "", embedding_model: str = settings.EMBEDDING_MODEL) -> KnowledgeBase:
        kb = KnowledgeBase(name=name, description=description, embedding_model=embedding_model, collection_name=f"kb_{datetime.utcnow().timestamp():.0f}")
        self.db.add(kb)
        self.db.commit()
        self.db.refresh(kb)
        return kb

    def update_kb(self, kb_id: str, **payload) -> KnowledgeBase | None:
        kb = self.get_kb(kb_id)
        if not kb:
            return None
        for field in ["name", "description", "embedding_model", "enabled"]:
            if field in payload and payload[field] is not None:
                setattr(kb, field, payload[field])
        self.db.commit()
        self.db.refresh(kb)
        return kb

    def get_kb(self, kb_id: str) -> KnowledgeBase | None:
        return self.db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()

    def delete_kb(self, kb_id: str) -> bool:
        kb = self.get_kb(kb_id)
        if not kb:
            return False
        self.db.delete(kb)
        self.db.commit()
        return True

    def page_kbs(self, page_no: int, page_size: int) -> tuple[list[KnowledgeBase], int]:
        query = self.db.query(KnowledgeBase).order_by(KnowledgeBase.created_at.desc())
        total = query.count()
        return query.offset((page_no - 1) * page_size).limit(page_size).all(), total

    def create_document(self, kb_id: str, **payload) -> KnowledgeDocument:
        doc = KnowledgeDocument(kb_id=kb_id, **payload)
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def get_document(self, doc_id: str) -> KnowledgeDocument | None:
        return self.db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()

    def update_document(self, doc_id: str, **payload) -> KnowledgeDocument | None:
        doc = self.get_document(doc_id)
        if not doc:
            return None
        for field in ["doc_name", "chunk_strategy", "chunk_config", "schedule_enabled", "schedule_cron", "enabled", "source_location"]:
            if field in payload and payload[field] is not None:
                setattr(doc, field, payload[field])
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def delete_document(self, doc_id: str) -> bool:
        doc = self.get_document(doc_id)
        if not doc:
            return False
        self.db.delete(doc)
        self.db.commit()
        return True

    def page_documents(self, kb_id: str, page_no: int, page_size: int, keyword: str | None = None) -> tuple[list[KnowledgeDocument], int]:
        query = self.db.query(KnowledgeDocument).filter(KnowledgeDocument.kb_id == kb_id)
        if keyword:
            query = query.filter(KnowledgeDocument.doc_name.ilike(f"%{keyword}%"))
        total = query.count()
        docs = query.order_by(KnowledgeDocument.created_at.desc()).offset((page_no - 1) * page_size).limit(page_size).all()
        return docs, total

    def search_documents(self, keyword: str, limit: int = 8) -> list[KnowledgeDocument]:
        query = self.db.query(KnowledgeDocument).filter(
            or_(KnowledgeDocument.doc_name.ilike(f"%{keyword}%"), KnowledgeDocument.source_location.ilike(f"%{keyword}%"))
        )
        return query.limit(limit).all()

    def page_chunks(self, doc_id: str, page_no: int, page_size: int) -> tuple[list[KnowledgeChunk], int]:
        query = self.db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc_id)
        total = query.count()
        rows = query.order_by(KnowledgeChunk.chunk_index.asc()).offset((page_no - 1) * page_size).limit(page_size).all()
        return rows, total

    def create_chunk(self, doc_id: str, content: str, meta_data: dict | None = None) -> KnowledgeChunk:
        doc = self.get_document(doc_id)
        if not doc:
            raise ValueError("Document not found")
        max_index = self.db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc_id).count()
        chunk = KnowledgeChunk(doc_id=doc_id, kb_id=doc.kb_id, content=content, chunk_index=max_index, meta_data=meta_data or {})
        self.db.add(chunk)
        doc.chunk_count += 1
        self.db.commit()
        self.db.refresh(chunk)
        return chunk

    def update_chunk(self, chunk_id: str, content: str | None = None, enabled: bool | None = None) -> KnowledgeChunk | None:
        chunk = self.db.query(KnowledgeChunk).filter(KnowledgeChunk.id == chunk_id).first()
        if not chunk:
            return None
        if content is not None:
            chunk.content = content
        if enabled is not None:
            chunk.enabled = enabled
        self.db.commit()
        self.db.refresh(chunk)
        return chunk

    def delete_chunk(self, chunk_id: str) -> bool:
        chunk = self.db.query(KnowledgeChunk).filter(KnowledgeChunk.id == chunk_id).first()
        if not chunk:
            return False
        doc = self.get_document(chunk.doc_id)
        self.db.delete(chunk)
        if doc and doc.chunk_count > 0:
            doc.chunk_count -= 1
        self.db.commit()
        return True

    def batch_enable_chunks(self, doc_id: str, chunk_ids: list[str], enabled: bool) -> None:
        self.db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc_id, KnowledgeChunk.id.in_(chunk_ids)).update(
            {KnowledgeChunk.enabled: enabled}, synchronize_session=False
        )
        self.db.commit()

    def get_chunk_logs(self, doc_id: str) -> list[KnowledgeDocumentChunkLog]:
        return self.db.query(KnowledgeDocumentChunkLog).filter(KnowledgeDocumentChunkLog.doc_id == doc_id).order_by(KnowledgeDocumentChunkLog.created_at.desc()).all()

    def start_chunking(self, doc_id: str) -> bool:
        doc = self.get_document(doc_id)
        if not doc:
            raise ValueError("Document not found")
        doc.status = "processing"
        self.db.commit()
        log = KnowledgeDocumentChunkLog(doc_id=doc.id, status="running", message="Chunking started")
        self.db.add(log)
        self.db.commit()
        try:
            pipeline_def = {
                "nodes": [
                    {"type": "fetcher", "settings": {"source_type": doc.source_type, "source_location": doc.file_url}},
                    {"type": "parser", "settings": {}},
                    {
                        "type": "chunker",
                        "settings": {
                            "chunk_size": doc.chunk_config.get("chunk_size", settings.CHUNK_SIZE),
                            "chunk_overlap": doc.chunk_config.get("chunk_overlap", settings.CHUNK_OVERLAP),
                            "strategy": doc.chunk_strategy,
                        },
                    },
                    {"type": "indexer", "settings": {}},
                ]
            }
            context = PipelineContext(task_id=doc.id, pipeline_id=doc.pipeline_id or "default")
            context.metadata = {"kb_id": doc.kb_id, "doc_id": doc.id, "source": doc.doc_name}
            result = self.pipeline_engine.execute(pipeline_def, context)

            if result.status != "completed":
                raise RuntimeError(str(result.error or "Pipeline execution failed"))
            if not result.chunks:
                raise RuntimeError("Pipeline completed without producing chunks")

            self.db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc.id).delete()
            for item in result.chunks:
                self.db.add(
                    KnowledgeChunk(
                        id=item.chunk_id,
                        doc_id=doc.id,
                        kb_id=doc.kb_id,
                        content=item.content,
                        chunk_index=item.index,
                        meta_data=item.metadata,
                        enabled=True,
                    )
                )
            doc.chunk_count = len(result.chunks)
            doc.status = "completed"
            doc.error_message = ""
            log.status = "completed"
            log.chunk_count = len(result.chunks)
            log.message = "Chunking completed"
            self.db.commit()
            return True
        except Exception as exc:
            doc.status = "failed"
            doc.error_message = str(exc)
            log.status = "failed"
            log.message = str(exc)
            self.db.commit()
            return False

    def rebuild_chunks(self, doc_id: str) -> bool:
        return self.start_chunking(doc_id)

