"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

from typing import Type

from sqlalchemy.orm import Session

from app.domain.models import IntentTreeNode, QueryTermMapping, SampleQuestion


class CrudService:
    def __init__(self, db: Session, model: Type):
        self.db = db
        self.model = model

    def list(self):
        return self.db.query(self.model).order_by(self.model.created_at.desc()).all()

    def get(self, item_id: str):
        return self.db.query(self.model).filter(self.model.id == item_id).first()

    def create(self, **payload):
        row = self.model(**payload)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update(self, item_id: str, **payload):
        row = self.get(item_id)
        if not row:
            return None
        for key, value in payload.items():
            if value is not None and hasattr(row, key):
                setattr(row, key, value)
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete(self, item_id: str) -> bool:
        row = self.get(item_id)
        if not row:
            return False
        self.db.delete(row)
        self.db.commit()
        return True


def intent_tree_service(db: Session) -> CrudService:
    return CrudService(db, IntentTreeNode)


def sample_question_service(db: Session) -> CrudService:
    return CrudService(db, SampleQuestion)


def mapping_service(db: Session) -> CrudService:
    return CrudService(db, QueryTermMapping)


