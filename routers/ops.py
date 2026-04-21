from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import User
from services.common import success
from services.dependencies import require_admin
from services.ops_service import intent_tree_service, mapping_service, sample_question_service

router = APIRouter(tags=["ops"])


class IntentPayload(BaseModel):
    parent_id: str | None = None
    name: str
    description: str = ""
    kb_id: str | None = None
    enabled: bool = True
    priority: int = 0


class SampleQuestionPayload(BaseModel):
    question: str
    answer: str = ""
    enabled: bool = True
    sort_order: int = 0


class MappingPayload(BaseModel):
    source_term: str
    target_term: str
    enabled: bool = True


@router.get("/intent-tree/trees")
def list_intents(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = intent_tree_service(db).list()
    return success(
        [
            {
                "id": item.id,
                "parentId": item.parent_id,
                "name": item.name,
                "description": item.description,
                "kbId": item.kb_id,
                "enabled": item.enabled,
                "priority": item.priority,
            }
            for item in rows
        ]
    )


@router.post("/intent-tree")
def create_intent(payload: IntentPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = intent_tree_service(db).create(**payload.model_dump())
    return success({"id": row.id})


@router.put("/intent-tree/{item_id}")
def update_intent(item_id: str, payload: IntentPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = intent_tree_service(db).update(item_id, **payload.model_dump())
    if not row:
        raise HTTPException(status_code=404, detail="意图节点不存在")
    return success()


@router.delete("/intent-tree/{item_id}")
def delete_intent(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if not intent_tree_service(db).delete(item_id):
        raise HTTPException(status_code=404, detail="意图节点不存在")
    return success()


@router.get("/sample-questions")
def list_samples(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = sample_question_service(db).list()
    return success([{"id": row.id, "question": row.question, "answer": row.answer, "enabled": row.enabled, "sortOrder": row.sort_order} for row in rows])


@router.post("/sample-questions")
def create_sample(payload: SampleQuestionPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = sample_question_service(db).create(**payload.model_dump())
    return success({"id": row.id})


@router.put("/sample-questions/{item_id}")
def update_sample(item_id: str, payload: SampleQuestionPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if not sample_question_service(db).update(item_id, **payload.model_dump()):
        raise HTTPException(status_code=404, detail="示例问题不存在")
    return success()


@router.delete("/sample-questions/{item_id}")
def delete_sample(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if not sample_question_service(db).delete(item_id):
        raise HTTPException(status_code=404, detail="示例问题不存在")
    return success()


@router.get("/mappings")
def list_mappings(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rows = mapping_service(db).list()
    return success([{"id": row.id, "sourceTerm": row.source_term, "targetTerm": row.target_term, "enabled": row.enabled} for row in rows])


@router.post("/mappings")
def create_mapping(payload: MappingPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    row = mapping_service(db).create(**payload.model_dump())
    return success({"id": row.id})


@router.put("/mappings/{item_id}")
def update_mapping(item_id: str, payload: MappingPayload, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if not mapping_service(db).update(item_id, **payload.model_dump()):
        raise HTTPException(status_code=404, detail="术语映射不存在")
    return success()


@router.delete("/mappings/{item_id}")
def delete_mapping(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if not mapping_service(db).delete(item_id):
        raise HTTPException(status_code=404, detail="术语映射不存在")
    return success()
