"""
知识库管理 API
提供知识库、文档的 CRUD 操作
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from knowledge.service import KnowledgeService
from models import KnowledgeBase, KnowledgeDocument

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge-base", tags=["knowledge-base"])


# ==================== Pydantic 模型 ====================

class CreateKnowledgeBaseRequest(BaseModel):
    """创建知识库请求"""
    name: str
    description: str = ""
    embedding_model: str = "text-embedding-v3"


class UploadDocumentRequest(BaseModel):
    """上传文档请求"""
    chunk_strategy: str = "recursive"
    chunk_size: int = 500
    chunk_overlap: int = 50


class KnowledgeBaseResponse(BaseModel):
    """知识库响应"""
    id: str
    name: str
    description: str
    collection_name: str
    embedding_model: str
    enabled: bool
    created_at: str
    
    class Config:
        from_attributes = True


class DocumentResponse(BaseModel):
    """文档响应"""
    id: str
    kb_id: str
    doc_name: str
    file_type: str
    file_size: int
    status: str
    chunk_count: int
    enabled: bool
    created_at: str
    
    class Config:
        from_attributes = True


# ==================== 知识库 API ====================

@router.post("", response_model=dict)
def create_knowledge_base(
    request: CreateKnowledgeBaseRequest,
    db: Session = Depends(get_db)
):
    """创建知识库"""
    try:
        service = KnowledgeService(db)
        kb = service.create_knowledge_base(
            name=request.name,
            description=request.description,
            embedding_model=request.embedding_model
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "id": kb.id,
                "name": kb.name,
                "collection_name": kb.collection_name,
            }
        }
    except Exception as e:
        logger.error(f"Failed to create knowledge base: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_id}", response_model=dict)
def get_knowledge_base(kb_id: str, db: Session = Depends(get_db)):
    """获取知识库详情"""
    service = KnowledgeService(db)
    kb = service.get_knowledge_base(kb_id)
    
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    
    return {
        "code": 200,
        "message": "success",
        "data": kb
    }


@router.get("", response_model=dict)
def list_knowledge_bases(
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db)
):
    """分页查询知识库列表"""
    service = KnowledgeService(db)
    result = service.list_knowledge_bases(page=page, page_size=page_size)
    
    return {
        "code": 200,
        "message": "success",
        "data": result
    }


@router.delete("/{kb_id}", response_model=dict)
def delete_knowledge_base(kb_id: str, db: Session = Depends(get_db)):
    """删除知识库"""
    service = KnowledgeService(db)
    success = service.delete_knowledge_base(kb_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    
    return {
        "code": 200,
        "message": "success"
    }


# ==================== 文档 API ====================

@router.post("/{kb_id}/documents/upload", response_model=dict)
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    chunk_strategy: str = Form("recursive"),
    chunk_size: int = Form(500),
    chunk_overlap: int = Form(50),
    db: Session = Depends(get_db)
):
    """上传文档到知识库"""
    try:
        # 验证知识库存在
        service = KnowledgeService(db)
        kb = service.get_knowledge_base(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail="Knowledge base not found")
        
        from config import settings
        from services.storage import LocalStorageService

        file_url, file_size = await LocalStorageService(settings.STORAGE_BASE_DIR).save_upload(
            file,
            max_file_size=settings.MAX_FILE_SIZE,
            max_request_size=settings.MAX_REQUEST_SIZE,
        )
        
        # 创建文档记录
        doc = service.upload_document(
            kb_id=kb_id,
            doc_name=file.filename,
            file_url=file_url,
            file_type=file.content_type or "application/octet-stream",
            file_size=file_size,
            source_type="upload",
            chunk_strategy=chunk_strategy,
            chunk_config={
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
            }
        )
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "id": doc.id,
                "doc_name": doc.doc_name,
                "status": doc.status,
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload document: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_id}/documents", response_model=dict)
def list_documents(
    kb_id: str,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db)
):
    """分页查询知识库文档列表"""
    try:
        service = KnowledgeService(db)
        result = service.list_documents(kb_id=kb_id, page=page, page_size=page_size)
        
        return {
            "code": 200,
            "message": "success",
            "data": result
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list documents: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/{doc_id}/chunk", response_model=dict)
def start_chunking(doc_id: str, db: Session = Depends(get_db)):
    """开始文档分块处理"""
    service = KnowledgeService(db)
    success = service.start_chunking(doc_id)
    
    if not success:
        doc = service.get_document(doc_id)
        error_msg = doc.error_message if doc else "Unknown error"
        raise HTTPException(status_code=500, detail=f"Chunking failed: {error_msg}")
    
    return {
        "code": 200,
        "message": "success"
    }


@router.get("/documents/{doc_id}", response_model=dict)
def get_document(doc_id: str, db: Session = Depends(get_db)):
    """获取文档详情"""
    service = KnowledgeService(db)
    doc = service.get_document(doc_id)
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # 转换为字典
    doc_dict = {
        "id": doc.id,
        "kb_id": doc.kb_id,
        "doc_name": doc.doc_name,
        "file_url": doc.file_url,
        "file_type": doc.file_type,
        "file_size": doc.file_size,
        "source_type": doc.source_type,
        "status": doc.status,
        "process_mode": doc.process_mode,
        "chunk_strategy": doc.chunk_strategy,
        "chunk_config": doc.chunk_config,
        "chunk_count": doc.chunk_count,
        "enabled": doc.enabled,
        "error_message": doc.error_message,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }
    
    return {
        "code": 200,
        "message": "success",
        "data": doc_dict
    }


@router.delete("/documents/{doc_id}", response_model=dict)
def delete_document(doc_id: str, db: Session = Depends(get_db)):
    """删除文档"""
    service = KnowledgeService(db)
    success = service.delete_document(doc_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {
        "code": 200,
        "message": "success"
    }


@router.patch("/documents/{doc_id}/enable", response_model=dict)
def enable_document(doc_id: str, enabled: bool, db: Session = Depends(get_db)):
    """启用/禁用文档"""
    service = KnowledgeService(db)
    success = service.enable_document(doc_id, enabled)
    
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {
        "code": 200,
        "message": "success"
    }


# ==================== 检索 API ====================

class SearchRequest(BaseModel):
    """检索请求"""
    query: str
    kb_id: Optional[str] = None
    top_k: int = 5
    collection_name: Optional[str] = None


class SearchResultItem(BaseModel):
    """检索结果项"""
    content: str
    score: float
    metadata: dict
    channel: str


@router.post("/{kb_id}/search", response_model=dict)
def search_documents(
    kb_id: str,
    request: SearchRequest,
    db: Session = Depends(get_db)
):
    """
    检索知识库文档
    
    使用多路检索引擎进行向量相似度搜索，支持：
    - 意图定向检索（如果提供了意图节点）
    - 全局向量检索（兜底策略）
    - 结果去重和排序
    
    Args:
        kb_id: 知识库ID
        request: 检索请求，包含查询文本、top_k等参数
        
    Returns:
        检索结果列表，按相似度分数降序排列
    """
    from rag.retrieval.multi_channel_retriever import MultiChannelRetriever
    
    logger.info(f"Search request: kb_id={kb_id}, query='{request.query[:50]}...', top_k={request.top_k}")
    
    try:
        # 验证知识库存在
        service = KnowledgeService(db)
        kb = service.get_knowledge_base(kb_id)
        if not kb:
            raise HTTPException(status_code=404, detail=f"Knowledge base not found: {kb_id}")
        
        # 初始化检索器
        retriever = MultiChannelRetriever()
        
        # 执行检索
        chunks = retriever.retrieve(
            query=request.query,
            kb_id=kb_id,
            collection_name=request.collection_name,
            top_k=request.top_k
        )
        
        # 转换为响应格式
        results = []
        for chunk in chunks:
            result_item = {
                "content": chunk.content,
                "score": round(chunk.score, 4),
                "metadata": chunk.metadata,
                "channel": chunk.channel
            }
            results.append(result_item)
        
        logger.info(f"Search completed: found {len(results)} chunks")
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "query": request.query,
                "kb_id": kb_id,
                "total": len(results),
                "results": results
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/search", response_model=dict)
def global_search(
    request: SearchRequest,
    db: Session = Depends(get_db)
):
    """
    全局检索（跨所有知识库）
    
    不指定知识库ID时，在所有知识库中进行向量检索
    
    Args:
        request: 检索请求
        
    Returns:
        全局检索结果
    """
    from rag.retrieval.multi_channel_retriever import MultiChannelRetriever
    
    logger.info(f"Global search request: query='{request.query[:50]}...', top_k={request.top_k}")
    
    try:
        # 初始化检索器
        retriever = MultiChannelRetriever()
        
        # 执行全局检索（不指定 kb_id）
        chunks = retriever.retrieve(
            query=request.query,
            kb_id=None,
            collection_name=request.collection_name,
            top_k=request.top_k
        )
        
        # 转换为响应格式
        results = []
        for chunk in chunks:
            result_item = {
                "content": chunk.content,
                "score": round(chunk.score, 4),
                "metadata": chunk.metadata,
                "channel": chunk.channel
            }
            results.append(result_item)
        
        logger.info(f"Global search completed: found {len(results)} chunks")
        
        return {
            "code": 200,
            "message": "success",
            "data": {
                "query": request.query,
                "total": len(results),
                "results": results
            }
        }
        
    except Exception as e:
        logger.error(f"Global search failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Global search failed: {str(e)}")
