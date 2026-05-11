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
- 向量检索：基于 Milvus 的高效检索
- 权限控制：基于用户的访问控制
"""
from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.text_sanitizer import sanitize_payload, sanitize_text
from app.core.time_utils import shanghai_time_id
from app.knowledge.vector_store import get_vector_store
from app.ingestion.pipeline_engine import PipelineContext, PipelineEngine
from app.ingestion.nodes.chunker_node import ChunkerNode
from app.ingestion.nodes.fetcher_node import FetcherNode
from app.ingestion.nodes.indexer_node import IndexerNode
from app.ingestion.nodes.parser_node import ParserNode
from app.domain.models import KnowledgeBase, KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentChunkLog
from app.services.storage import create_storage_service


class KnowledgeService:
    """KnowledgeService 服务类：集中处理一类业务流程，让路由层不需要直接操作数据库、缓存或外部组件。"""
    def __init__(self, db: Session):
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
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
        """list_chunk_strategies 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
        return [
            {"value": "recursive", "label": "Recursive"},
            {"value": "fixed", "label": "Fixed Size"},
            {"value": "markdown", "label": "Markdown"},
            {"value": "semantic", "label": "Semantic"},
        ]

    def create_kb(self, name: str, description: str = "", embedding_model: str = settings.EMBEDDING_MODEL) -> KnowledgeBase:
        # 集合名改为东八区可读时间标识，避免界面或排障时看到 UTC 时间戳难以判断。
        """create_kb 函数：创建新的业务记录，负责组织入库字段并返回创建后的结果。"""
        kb = KnowledgeBase(name=name, description=description, embedding_model=embedding_model, collection_name=shanghai_time_id("kb"))
        self.db.add(kb)
        self.db.commit()
        self.db.refresh(kb)
        return kb

    def update_kb(self, kb_id: str, **payload) -> KnowledgeBase | None:
        """update_kb 函数：更新已有业务记录，只修改调用方明确传入的字段。"""
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
        """get_kb 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
        return self.db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()

    def delete_kb(self, kb_id: str) -> bool:
        """delete_kb 函数：删除业务记录，并在需要时同步清理关联资源或缓存。"""
        kb = self.get_kb(kb_id)
        if not kb:
            return False
        file_urls = [doc.file_url for doc in kb.documents if doc.file_url]
        self.db.delete(kb)
        self.db.commit()
        for file_url in file_urls:
            self._delete_file_if_unreferenced(file_url)
        return True

    def page_kbs(self, page_no: int, page_size: int) -> tuple[list[KnowledgeBase], int]:
        """page_kbs 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
        query = self.db.query(KnowledgeBase).order_by(KnowledgeBase.created_at.desc())
        total = query.count()
        return query.offset((page_no - 1) * page_size).limit(page_size).all(), total

    def create_document(self, kb_id: str, **payload) -> KnowledgeDocument:
        """create_document 函数：创建新的业务记录，负责组织入库字段并返回创建后的结果。"""
        doc = KnowledgeDocument(kb_id=kb_id, **payload)
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def get_document(self, doc_id: str) -> KnowledgeDocument | None:
        """get_document 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
        return self.db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()

    def update_document(self, doc_id: str, **payload) -> KnowledgeDocument | None:
        """update_document 函数：更新已有业务记录，只修改调用方明确传入的字段。"""
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
        """delete_document 函数：删除业务记录，并在需要时同步清理关联资源或缓存。"""
        doc = self.get_document(doc_id)
        if not doc:
            return False
        file_url = doc.file_url
        # 删除业务记录前先清理向量索引，避免 Milvus 中残留孤立分块。
        get_vector_store().delete_by_doc_id(doc.id)
        self.db.delete(doc)
        self.db.commit()
        self._delete_file_if_unreferenced(file_url)
        return True

    def _delete_file_if_unreferenced(self, file_url: str | None) -> bool:
        """_delete_file_if_unreferenced 函数：删除业务记录，并在需要时同步清理关联资源或缓存。"""
        if not file_url:
            return False
        references = self.db.query(KnowledgeDocument).filter(KnowledgeDocument.file_url == file_url).count()
        if references > 0:
            return False
        try:
            return create_storage_service().delete_file(file_url)
        except Exception:
            return False

    def page_documents(
        self,
        kb_id: str,
        page_no: int,
        page_size: int,
        keyword: str | None = None,
        status: str | None = None,
    ) -> tuple[list[KnowledgeDocument], int]:
        """page_documents 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
        query = self.db.query(KnowledgeDocument).filter(KnowledgeDocument.kb_id == kb_id)
        if keyword:
            query = query.filter(KnowledgeDocument.doc_name.ilike(f"%{keyword}%"))
        if status:
            query = query.filter(KnowledgeDocument.status == status)
        total = query.count()
        docs = query.order_by(KnowledgeDocument.created_at.desc()).offset((page_no - 1) * page_size).limit(page_size).all()
        return docs, total

    def search_documents(self, keyword: str, limit: int = 8) -> list[KnowledgeDocument]:
        """search_documents 函数：执行检索逻辑，从知识库或索引中找出和用户问题最相关的内容。"""
        query = self.db.query(KnowledgeDocument).filter(
            or_(KnowledgeDocument.doc_name.ilike(f"%{keyword}%"), KnowledgeDocument.source_location.ilike(f"%{keyword}%"))
        )
        return query.limit(limit).all()

    def page_chunks(self, doc_id: str, page_no: int, page_size: int) -> tuple[list[KnowledgeChunk], int]:
        """page_chunks 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
        query = self.db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc_id)
        total = query.count()
        rows = query.order_by(KnowledgeChunk.chunk_index.asc()).offset((page_no - 1) * page_size).limit(page_size).all()
        return rows, total

    def create_chunk(self, doc_id: str, content: str, meta_data: dict | None = None) -> KnowledgeChunk:
        """create_chunk 函数：创建新的业务记录，负责组织入库字段并返回创建后的结果。"""
        doc = self.get_document(doc_id)
        if not doc:
            raise ValueError("Document not found")
        max_index = self.db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc_id).count()
        # 手工新增 chunk 也需要走同一套清洗，避免绕过摄取流水线后写入非法字符。
        chunk = KnowledgeChunk(
            doc_id=doc_id,
            kb_id=doc.kb_id,
            content=sanitize_text(content),
            chunk_index=max_index,
            meta_data=sanitize_payload(meta_data or {}),
        )
        self.db.add(chunk)
        doc.chunk_count += 1
        self.db.commit()
        self.db.refresh(chunk)
        return chunk

    def update_chunk(self, chunk_id: str, content: str | None = None, enabled: bool | None = None) -> KnowledgeChunk | None:
        """update_chunk 函数：更新已有业务记录，只修改调用方明确传入的字段。"""
        chunk = self.db.query(KnowledgeChunk).filter(KnowledgeChunk.id == chunk_id).first()
        if not chunk:
            return None
        if content is not None:
            chunk.content = sanitize_text(content)
        if enabled is not None:
            chunk.enabled = enabled
        self.db.commit()
        self.db.refresh(chunk)
        return chunk

    def delete_chunk(self, chunk_id: str) -> bool:
        """delete_chunk 函数：删除业务记录，并在需要时同步清理关联资源或缓存。"""
        chunk = self.db.query(KnowledgeChunk).filter(KnowledgeChunk.id == chunk_id).first()
        if not chunk:
            return False
        doc = self.get_document(chunk.doc_id)
        # 单个分块删除时同步清理向量索引，保证检索结果和后台状态一致。
        get_vector_store().delete_by_chunk_ids([chunk.id])
        self.db.delete(chunk)
        if doc and doc.chunk_count > 0:
            doc.chunk_count -= 1
        self.db.commit()
        return True

    def batch_enable_chunks(self, doc_id: str, chunk_ids: list[str], enabled: bool) -> None:
        """batch_enable_chunks 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        self.db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc_id, KnowledgeChunk.id.in_(chunk_ids)).update(
            {KnowledgeChunk.enabled: enabled}, synchronize_session=False
        )
        self.db.commit()

    def get_chunk_logs(self, doc_id: str) -> list[KnowledgeDocumentChunkLog]:
        """get_chunk_logs 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
        return self.db.query(KnowledgeDocumentChunkLog).filter(KnowledgeDocumentChunkLog.doc_id == doc_id).order_by(KnowledgeDocumentChunkLog.created_at.desc()).all()

    def start_chunking(self, doc_id: str) -> bool:
        """start_chunking 函数：启动一次运行流程，并创建后续追踪或状态更新需要的初始记录。"""
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
                            "semantic_threshold": doc.chunk_config.get("semantic_threshold"),
                            "min_chunk_size": doc.chunk_config.get("min_chunk_size"),
                            "max_chunk_size": doc.chunk_config.get("max_chunk_size"),
                            "preserve_headings": doc.chunk_config.get("preserve_headings", True),
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
                        content=sanitize_text(item.content),
                        chunk_index=item.index,
                        meta_data=sanitize_payload(item.metadata),
                        enabled=True,
                    )
                )
            doc.chunk_count = len(result.chunks)
            doc.status = "completed"
            doc.error_message = ""
            log.status = "completed"
            log.chunk_count = len(result.chunks)
            fallback = context.metadata.get("chunker_fallback")
            log.message = f"Chunking completed；{fallback}" if fallback else "Chunking completed"
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
        """rebuild_chunks 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        return self.start_chunking(doc_id)



