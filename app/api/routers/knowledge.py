"""
知识库路由模块 (Knowledge Router Module)

本模块定义了知识库管理相关的 REST API 接口，负责文档和知识库的 CRUD 操作。
支持文档上传、知识库管理、分块处理、检索等完整的知识库生命周期。

主要功能：
1. 知识库管理：创建、查询、更新、删除知识库
2. 文档管理：上传文档、查询文档、分块处理
3. 检索服务：基于向量的相似度检索
4. 批量操作：支持批量上传和处理文档
5. 状态监控：查看摄取任务进度和状态

核心特性：
- 文件上传：支持多种文档格式（PDF、TXT、MD等）
- 异步处理：文档上传后异步进行分块和向量化
- 向量检索：高效的相似度搜索和重排
- 权限控制：基于用户的知识库访问控制
- 进度追踪：实时查看文档处理进度

API 端点：
- GET/POST /knowledge/bases: 知识库列表和创建
- GET/PUT/DELETE /knowledge/bases/{id}: 知识库详情操作
- POST /knowledge/documents/upload: 文档上传
- GET /knowledge/documents: 文档列表查询
- POST /knowledge/search: 知识检索
- GET /knowledge/tasks/{id}: 任务进度查询
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.time_utils import to_shanghai_iso
from app.domain.models import KnowledgeChunk, User
from app.services.common import page, success
from app.services.dependencies import require_admin
from app.services.knowledge_service import KnowledgeService
from app.services.settings_service import get_runtime_settings
from app.services.storage import create_storage_service

router = APIRouter(tags=["knowledge"])
storage = create_storage_service()


class KnowledgeBasePayload(BaseModel):
    """KnowledgeBasePayload 请求模型：描述前端提交到接口的字段，FastAPI 会用它完成参数校验和类型转换。"""
    name: str
    description: str = ""
    embedding_model: str = "text-embedding-v3"
    enabled: bool | None = None


class DocumentUpdatePayload(BaseModel):
    """DocumentUpdatePayload 请求模型：描述前端提交到接口的字段，FastAPI 会用它完成参数校验和类型转换。"""
    doc_name: str | None = None
    chunk_strategy: str | None = None
    chunk_config: dict | None = None
    schedule_enabled: bool | None = None
    schedule_cron: str | None = None
    enabled: bool | None = None


class ChunkPayload(BaseModel):
    """ChunkPayload 请求模型：描述前端提交到接口的字段，FastAPI 会用它完成参数校验和类型转换。"""
    content: str
    enabled: bool | None = None
    metadata: dict | None = None


class BatchChunkPayload(BaseModel):
    """BatchChunkPayload 请求模型：描述前端提交到接口的字段，FastAPI 会用它完成参数校验和类型转换。"""
    chunk_ids: list[str]
    enabled: bool


@router.get("/knowledge-base/chunk-strategies")
def chunk_strategies(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """chunk_strategies 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    return success(KnowledgeService(db).list_chunk_strategies())


@router.post("/knowledge-base")
def create_kb(payload: KnowledgeBasePayload, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """create_kb 函数：创建新的业务记录，负责组织入库字段并返回创建后的结果。"""
    kb = KnowledgeService(db).create_kb(payload.name, payload.description, payload.embedding_model)
    kb.created_by = user.id
    db.commit()
    return success({"id": kb.id, "name": kb.name, "collectionName": kb.collection_name})


@router.put("/knowledge-base/{kb_id}")
def update_kb(kb_id: str, payload: KnowledgeBasePayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """update_kb 函数：更新已有业务记录，只修改调用方明确传入的字段。"""
    kb = KnowledgeService(db).update_kb(kb_id, **payload.model_dump(exclude_none=True))
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return success({"id": kb.id})


@router.delete("/knowledge-base/{kb_id}")
def delete_kb(kb_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """delete_kb 函数：删除业务记录，并在需要时同步清理关联资源或缓存。"""
    if not KnowledgeService(db).delete_kb(kb_id):
        raise HTTPException(status_code=404, detail="知识库不存在")
    return success()


@router.get("/knowledge-base/{kb_id}")
def get_kb(kb_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """get_kb 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
    kb = KnowledgeService(db).get_kb(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return success(
        {
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "collectionName": kb.collection_name,
            "embeddingModel": kb.embedding_model,
            "enabled": kb.enabled,
            "createdAt": to_shanghai_iso(kb.created_at),
        }
    )


@router.get("/knowledge-base")
def list_kb(pageNo: int = 1, pageSize: int = 10, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """list_kb 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
    rows, total = KnowledgeService(db).page_kbs(pageNo, pageSize)
    items = [
        {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "collectionName": row.collection_name,
            "embeddingModel": row.embedding_model,
            "enabled": row.enabled,
            "createdAt": to_shanghai_iso(row.created_at),
        }
        for row in rows
    ]
    return success(page(items, total, pageNo, pageSize))


@router.post("/knowledge-base/{kb_id}/docs/upload")
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    chunkStrategy: str = Form("recursive"),
    chunkSize: int = Form(500),
    chunkOverlap: int = Form(50),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """upload_document 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    service = KnowledgeService(db)
    if not service.get_kb(kb_id):
        raise HTTPException(status_code=404, detail="知识库不存在")
    runtime_settings = get_runtime_settings(db)
    try:
        file_url, file_size = await storage.save_upload(
            file,
            max_file_size=runtime_settings.max_file_size,
            max_request_size=runtime_settings.max_request_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    doc = service.create_document(
        kb_id=kb_id,
        doc_name=file.filename or "upload.bin",
        file_url=file_url,
        source_location=file_url,
        file_type=file.content_type or "application/octet-stream",
        file_size=file_size,
        chunk_strategy=chunkStrategy,
        chunk_config={"chunk_size": chunkSize, "chunk_overlap": chunkOverlap},
    )
    return success({"id": doc.id, "docName": doc.doc_name, "status": doc.status})


@router.post("/knowledge-base/docs/{doc_id}/chunk")
def start_chunk(doc_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """start_chunk 函数：启动一次运行流程，并创建后续追踪或状态更新需要的初始记录。"""
    service = KnowledgeService(db)
    ok = service.start_chunking(doc_id)
    if not ok:
        raise HTTPException(status_code=500, detail="分块失败")
    return success()


@router.delete("/knowledge-base/docs/{doc_id}")
def delete_document(doc_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """delete_document 函数：删除业务记录，并在需要时同步清理关联资源或缓存。"""
    if not KnowledgeService(db).delete_document(doc_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    return success()


@router.get("/knowledge-base/docs/{doc_id}")
def get_document(doc_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """get_document 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
    doc = KnowledgeService(db).get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return success(
        {
            "id": doc.id,
            "kbId": doc.kb_id,
            "docName": doc.doc_name,
            "fileUrl": doc.file_url,
            "fileType": doc.file_type,
            "fileSize": doc.file_size,
            "status": doc.status,
            "enabled": doc.enabled,
            "chunkCount": doc.chunk_count,
            "chunkStrategy": doc.chunk_strategy,
            "chunkConfig": doc.chunk_config,
            "scheduleEnabled": doc.schedule_enabled,
            "scheduleCron": doc.schedule_cron,
            "errorMessage": doc.error_message,
        }
    )


@router.put("/knowledge-base/docs/{doc_id}")
def update_document(doc_id: str, payload: DocumentUpdatePayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """update_document 函数：更新已有业务记录，只修改调用方明确传入的字段。"""
    row = KnowledgeService(db).update_document(doc_id, **payload.model_dump(exclude_none=True))
    if not row:
        raise HTTPException(status_code=404, detail="文档不存在")
    return success()


@router.get("/knowledge-base/{kb_id}/docs")
def list_documents(
    kb_id: str,
    pageNo: int = 1,
    pageSize: int = 10,
    keyword: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """list_documents 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
    rows, total = KnowledgeService(db).page_documents(kb_id, pageNo, pageSize, keyword, status)
    items = [
        {
            "id": row.id,
            "kbId": row.kb_id,
            "docName": row.doc_name,
            "fileType": row.file_type,
            "fileSize": row.file_size,
            "status": row.status,
            "chunkCount": row.chunk_count,
            "enabled": row.enabled,
            "createdAt": to_shanghai_iso(row.created_at),
        }
        for row in rows
    ]
    return success(page(items, total, pageNo, pageSize))


@router.get("/knowledge-base/docs/search")
def search_docs(keyword: str = Query("", alias="keyword"), limit: int = 8, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """search_docs 函数：执行检索逻辑，从知识库或索引中找出和用户问题最相关的内容。"""
    rows = KnowledgeService(db).search_documents(keyword, limit)
    return success([{"id": row.id, "name": row.doc_name, "kbId": row.kb_id} for row in rows])


@router.patch("/knowledge-base/docs/{doc_id}/enable")
def enable_document(doc_id: str, value: bool, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """enable_document 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    row = KnowledgeService(db).update_document(doc_id, enabled=value)
    if not row:
        raise HTTPException(status_code=404, detail="文档不存在")
    return success()


@router.get("/knowledge-base/docs/{doc_id}/chunk-logs")
def chunk_logs(doc_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """chunk_logs 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    rows = KnowledgeService(db).get_chunk_logs(doc_id)
    return success([{"id": row.id, "status": row.status, "message": row.message, "chunkCount": row.chunk_count, "createdAt": to_shanghai_iso(row.created_at)} for row in rows])


@router.get("/knowledge-base/docs/{doc_id}/chunks")
def list_chunks(doc_id: str, pageNo: int = 1, pageSize: int = 20, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """list_chunks 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
    rows, total = KnowledgeService(db).page_chunks(doc_id, pageNo, pageSize)
    items = [{"id": row.id, "content": row.content, "chunkIndex": row.chunk_index, "enabled": row.enabled, "metadata": row.meta_data} for row in rows]
    return success(page(items, total, pageNo, pageSize))


@router.post("/knowledge-base/docs/{doc_id}/chunks")
def create_chunk(doc_id: str, payload: ChunkPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """create_chunk 函数：创建新的业务记录，负责组织入库字段并返回创建后的结果。"""
    row = KnowledgeService(db).create_chunk(doc_id, payload.content, payload.metadata)
    return success({"id": row.id})


@router.put("/knowledge-base/docs/{doc_id}/chunks/{chunk_id}")
def update_chunk(doc_id: str, chunk_id: str, payload: ChunkPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """update_chunk 函数：更新已有业务记录，只修改调用方明确传入的字段。"""
    row = KnowledgeService(db).update_chunk(chunk_id, payload.content, payload.enabled)
    if not row:
        raise HTTPException(status_code=404, detail="分块不存在")
    return success()


@router.delete("/knowledge-base/docs/{doc_id}/chunks/{chunk_id}")
def delete_chunk(doc_id: str, chunk_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """delete_chunk 函数：删除业务记录，并在需要时同步清理关联资源或缓存。"""
    if not KnowledgeService(db).delete_chunk(chunk_id):
        raise HTTPException(status_code=404, detail="分块不存在")
    return success()


@router.post("/knowledge-base/docs/{doc_id}/chunks/batch-enable")
def batch_enable(doc_id: str, payload: BatchChunkPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """batch_enable 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    KnowledgeService(db).batch_enable_chunks(doc_id, payload.chunk_ids, payload.enabled)
    return success()


@router.post("/knowledge-base/docs/{doc_id}/chunks/{chunk_id}/enable")
def enable_chunk(doc_id: str, chunk_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """对齐原版单条 Chunk 启用接口语义。"""

    row = KnowledgeService(db).update_chunk(chunk_id, enabled=True)
    if not row or row.doc_id != doc_id:
        raise HTTPException(status_code=404, detail="分块不存在")
    return success()


@router.post("/knowledge-base/docs/{doc_id}/chunks/{chunk_id}/disable")
def disable_chunk(doc_id: str, chunk_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """对齐原版单条 Chunk 停用接口语义。"""

    row = KnowledgeService(db).update_chunk(chunk_id, enabled=False)
    if not row or row.doc_id != doc_id:
        raise HTTPException(status_code=404, detail="分块不存在")
    return success()


@router.post("/knowledge-base/docs/{doc_id}/chunks/batch-disable")
def batch_disable(doc_id: str, payload: BatchChunkPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """对齐原版批量停用接口语义。"""

    KnowledgeService(db).batch_enable_chunks(doc_id, payload.chunk_ids, False)
    return success()


@router.post("/knowledge-base/docs/{doc_id}/chunks/rebuild")
def rebuild_chunks(doc_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """rebuild_chunks 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    if not KnowledgeService(db).rebuild_chunks(doc_id):
        raise HTTPException(status_code=500, detail="重建失败")
    return success()



