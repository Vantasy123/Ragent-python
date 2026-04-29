"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

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
    parent_id: str | None = None
    name: str
    description: str = ""
    kb_id: str | None = None
    enabled: bool = True
    priority: int = 0


class QuestionPayload(BaseModel):
    question: str
    answer: str = ""
    enabled: bool = True
    sort_order: int = 0


class MappingPayload(BaseModel):
    source_term: str
    target_term: str
    enabled: bool = True


def _serialize(row) -> dict:
    """序列化 ORM 对象，避免把 SQLAlchemy 内部字段暴露给前端。"""

    return {key: value for key, value in row.__dict__.items() if not key.startswith("_")}


@router.get("/intent-tree")
def list_intent_tree(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return success([_serialize(row) for row in intent_tree_service(db).list()])


@router.get("/intent-tree/trees")
def list_intent_tree_alias(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """兼容原版 `/intent-tree/trees` 路径。"""

    return success([_serialize(row) for row in intent_tree_service(db).list()])


@router.get("/intent-tree/{item_id}")
def get_intent_tree(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = intent_tree_service(db).get(item_id)
    if not row:
        raise HTTPException(status_code=404, detail="意图节点不存在")
    return success(_serialize(row))


@router.post("/intent-tree")
def create_intent_tree(payload: IntentPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return success(_serialize(intent_tree_service(db).create(**payload.model_dump())))


@router.put("/intent-tree/{item_id}")
def update_intent_tree(item_id: str, payload: IntentPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = intent_tree_service(db).update(item_id, **payload.model_dump())
    if not row:
        raise HTTPException(status_code=404, detail="意图节点不存在")
    return success(_serialize(row))


@router.delete("/intent-tree/{item_id}")
def delete_intent_tree(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if not intent_tree_service(db).delete(item_id):
        raise HTTPException(status_code=404, detail="意图节点不存在")
    return success()


@router.get("/sample-questions")
def list_sample_questions(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return success([_serialize(row) for row in sample_question_service(db).list()])


@router.get("/sample-questions/{item_id}")
def get_sample_question(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = sample_question_service(db).get(item_id)
    if not row:
        raise HTTPException(status_code=404, detail="示例问题不存在")
    return success(_serialize(row))


@router.post("/sample-questions")
def create_sample_question(payload: QuestionPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return success(_serialize(sample_question_service(db).create(**payload.model_dump())))


@router.put("/sample-questions/{item_id}")
def update_sample_question(item_id: str, payload: QuestionPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = sample_question_service(db).update(item_id, **payload.model_dump())
    if not row:
        raise HTTPException(status_code=404, detail="示例问题不存在")
    return success(_serialize(row))


@router.delete("/sample-questions/{item_id}")
def delete_sample_question(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if not sample_question_service(db).delete(item_id):
        raise HTTPException(status_code=404, detail="示例问题不存在")
    return success()


@router.get("/mappings")
def list_mappings(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return success([_serialize(row) for row in mapping_service(db).list()])


@router.get("/mappings/{item_id}")
def get_mapping(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = mapping_service(db).get(item_id)
    if not row:
        raise HTTPException(status_code=404, detail="术语映射不存在")
    return success(_serialize(row))


@router.post("/mappings")
def create_mapping(payload: MappingPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return success(_serialize(mapping_service(db).create(**payload.model_dump())))


@router.put("/mappings/{item_id}")
def update_mapping(item_id: str, payload: MappingPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = mapping_service(db).update(item_id, **payload.model_dump())
    if not row:
        raise HTTPException(status_code=404, detail="术语映射不存在")
    return success(_serialize(row))


@router.delete("/mappings/{item_id}")
def delete_mapping(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if not mapping_service(db).delete(item_id):
        raise HTTPException(status_code=404, detail="术语映射不存在")
    return success()
