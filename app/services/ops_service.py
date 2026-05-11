"""模块导读：本文件位于 app/services/ops_service.py，属于服务层。

主要职责：承接路由层请求，组织数据库、缓存、Trace、Agent 和外部组件完成业务流程。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

from typing import Type

from sqlalchemy.orm import Session

from app.domain.models import IntentTreeNode, QueryTermMapping, SampleQuestion


class CrudService:
    """CrudService 服务类：集中处理一类业务流程，让路由层不需要直接操作数据库、缓存或外部组件。"""
    def __init__(self, db: Session, model: Type):
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
        self.db = db
        self.model = model

    def list(self):
        """list 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
        return self.db.query(self.model).order_by(self.model.created_at.desc()).all()

    def get(self, item_id: str):
        """get 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
        return self.db.query(self.model).filter(self.model.id == item_id).first()

    def create(self, **payload):
        """create 函数：创建新的业务记录，负责组织入库字段并返回创建后的结果。"""
        row = self.model(**payload)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update(self, item_id: str, **payload):
        """update 函数：更新已有业务记录，只修改调用方明确传入的字段。"""
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
        """delete 函数：删除业务记录，并在需要时同步清理关联资源或缓存。"""
        row = self.get(item_id)
        if not row:
            return False
        self.db.delete(row)
        self.db.commit()
        return True


def intent_tree_service(db: Session) -> CrudService:
    """intent_tree_service 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    return CrudService(db, IntentTreeNode)


def sample_question_service(db: Session) -> CrudService:
    """sample_question_service 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    return CrudService(db, SampleQuestion)


def mapping_service(db: Session) -> CrudService:
    """mapping_service 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    return CrudService(db, QueryTermMapping)


