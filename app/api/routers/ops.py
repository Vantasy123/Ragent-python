"""模块导读：本文件位于 app/api/routers/ops.py，属于API 路由层。

主要职责：把 HTTP 请求转换成服务层调用，并把结果整理成前端可以直接使用的响应。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.models import User
from app.services.common import success
from app.services.dependencies import require_admin
from app.services.ops_service import intent_tree_service, mapping_service, sample_question_service

router = APIRouter(tags=["ops"])


class IntentPayload(BaseModel):
    """IntentPayload 请求模型：描述前端提交到接口的字段，FastAPI 会用它完成参数校验和类型转换。"""
    parent_id: str | None = None
    name: str
    description: str = ""
    kb_id: str | None = None
    enabled: bool = True
    priority: int = 0


class QuestionPayload(BaseModel):
    """QuestionPayload 请求模型：描述前端提交到接口的字段，FastAPI 会用它完成参数校验和类型转换。"""
    question: str
    answer: str = ""
    enabled: bool = True
    sort_order: int = 0


class MappingPayload(BaseModel):
    """MappingPayload 请求模型：描述前端提交到接口的字段，FastAPI 会用它完成参数校验和类型转换。"""
    source_term: str
    target_term: str
    enabled: bool = True


def _serialize(row) -> dict:
    """序列化 ORM 对象，避免把 SQLAlchemy 内部字段暴露给前端。"""

    return {key: value for key, value in row.__dict__.items() if not key.startswith("_")}


@router.get("/intent-tree")
def list_intent_tree(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """list_intent_tree 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
    return success([_serialize(row) for row in intent_tree_service(db).list()])


@router.get("/intent-tree/{item_id}")
def get_intent_tree(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """get_intent_tree 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
    row = intent_tree_service(db).get(item_id)
    if not row:
        raise HTTPException(status_code=404, detail="意图节点不存在")
    return success(_serialize(row))


@router.post("/intent-tree")
def create_intent_tree(payload: IntentPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """create_intent_tree 函数：创建新的业务记录，负责组织入库字段并返回创建后的结果。"""
    return success(_serialize(intent_tree_service(db).create(**payload.model_dump())))


@router.put("/intent-tree/{item_id}")
def update_intent_tree(item_id: str, payload: IntentPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """update_intent_tree 函数：更新已有业务记录，只修改调用方明确传入的字段。"""
    row = intent_tree_service(db).update(item_id, **payload.model_dump())
    if not row:
        raise HTTPException(status_code=404, detail="意图节点不存在")
    return success(_serialize(row))


@router.delete("/intent-tree/{item_id}")
def delete_intent_tree(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """delete_intent_tree 函数：删除业务记录，并在需要时同步清理关联资源或缓存。"""
    if not intent_tree_service(db).delete(item_id):
        raise HTTPException(status_code=404, detail="意图节点不存在")
    return success()


@router.get("/sample-questions")
def list_sample_questions(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """list_sample_questions 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
    return success([_serialize(row) for row in sample_question_service(db).list()])


@router.get("/sample-questions/{item_id}")
def get_sample_question(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """get_sample_question 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
    row = sample_question_service(db).get(item_id)
    if not row:
        raise HTTPException(status_code=404, detail="示例问题不存在")
    return success(_serialize(row))


@router.post("/sample-questions")
def create_sample_question(payload: QuestionPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """create_sample_question 函数：创建新的业务记录，负责组织入库字段并返回创建后的结果。"""
    return success(_serialize(sample_question_service(db).create(**payload.model_dump())))


@router.put("/sample-questions/{item_id}")
def update_sample_question(item_id: str, payload: QuestionPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """update_sample_question 函数：更新已有业务记录，只修改调用方明确传入的字段。"""
    row = sample_question_service(db).update(item_id, **payload.model_dump())
    if not row:
        raise HTTPException(status_code=404, detail="示例问题不存在")
    return success(_serialize(row))


@router.delete("/sample-questions/{item_id}")
def delete_sample_question(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """delete_sample_question 函数：删除业务记录，并在需要时同步清理关联资源或缓存。"""
    if not sample_question_service(db).delete(item_id):
        raise HTTPException(status_code=404, detail="示例问题不存在")
    return success()


@router.get("/mappings")
def list_mappings(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """list_mappings 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
    return success([_serialize(row) for row in mapping_service(db).list()])


@router.get("/mappings/{item_id}")
def get_mapping(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """get_mapping 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
    row = mapping_service(db).get(item_id)
    if not row:
        raise HTTPException(status_code=404, detail="术语映射不存在")
    return success(_serialize(row))


@router.post("/mappings")
def create_mapping(payload: MappingPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """create_mapping 函数：创建新的业务记录，负责组织入库字段并返回创建后的结果。"""
    return success(_serialize(mapping_service(db).create(**payload.model_dump())))


@router.put("/mappings/{item_id}")
def update_mapping(item_id: str, payload: MappingPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """update_mapping 函数：更新已有业务记录，只修改调用方明确传入的字段。"""
    row = mapping_service(db).update(item_id, **payload.model_dump())
    if not row:
        raise HTTPException(status_code=404, detail="术语映射不存在")
    return success(_serialize(row))


@router.delete("/mappings/{item_id}")
def delete_mapping(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """delete_mapping 函数：删除业务记录，并在需要时同步清理关联资源或缓存。"""
    if not mapping_service(db).delete(item_id):
        raise HTTPException(status_code=404, detail="术语映射不存在")
    return success()
