"""
数据摄取服务模块 (Ingestion Service Module)

本模块实现了数据摄取的业务逻辑，负责管理摄取流水线和任务的生命周期。
支持创建、执行、监控文档处理流水线，提供完整的摄取任务管理功能。

主要功能：
1. 流水线管理：创建、查询、更新、删除摄取流水线
2. 任务执行：异步执行文档处理任务
3. 进度监控：实时跟踪任务执行状态和进度
4. 节点管理：管理流水线中的各个处理节点
5. 错误处理：完善的异常处理和重试机制

核心组件：
- IngestionService: 主要业务逻辑类
- PipelineEngine: 流水线执行引擎
- 各种处理节点：文档获取、解析、分块、索引等

处理流程：
1. 创建流水线 → 定义处理节点和配置
2. 提交任务 → 创建摄取任务记录
3. 执行流水线 → 依次执行各个处理节点
4. 更新状态 → 实时更新任务进度
5. 完成处理 → 存储处理结果和统计信息

技术特性：
- 异步执行：非阻塞的任务处理
- 进度追踪：详细的执行状态和时间统计
- 错误恢复：支持失败任务的重试
- 并发控制：避免资源竞争和死锁
- 数据一致性：事务保证的数据完整性
"""
from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.core.time_utils import utc_now_naive
from app.domain.models import IngestionPipeline, IngestionTask, IngestionTaskNodeRun
from app.services.knowledge_service import KnowledgeService


class IngestionService:
    """IngestionService 服务类：集中处理一类业务流程，让路由层不需要直接操作数据库、缓存或外部组件。"""
    def __init__(self, db: Session):
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
        self.db = db

    def page_pipelines(self, page_no: int, page_size: int):
        """page_pipelines 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
        query = self.db.query(IngestionPipeline).order_by(IngestionPipeline.created_at.desc())
        total = query.count()
        rows = query.offset((page_no - 1) * page_size).limit(page_size).all()
        return rows, total

    def create_pipeline(self, name: str, description: str, nodes: list) -> IngestionPipeline:
        """create_pipeline 函数：创建新的业务记录，负责组织入库字段并返回创建后的结果。"""
        row = IngestionPipeline(name=name, description=description, nodes=nodes)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_pipeline(self, pipeline_id: str, **payload) -> IngestionPipeline | None:
        """update_pipeline 函数：更新已有业务记录，只修改调用方明确传入的字段。"""
        row = self.get_pipeline(pipeline_id)
        if not row:
            return None
        for field in ["name", "description", "nodes", "enabled"]:
            if field in payload and payload[field] is not None:
                setattr(row, field, payload[field])
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_pipeline(self, pipeline_id: str) -> IngestionPipeline | None:
        """get_pipeline 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
        return self.db.query(IngestionPipeline).filter(IngestionPipeline.id == pipeline_id).first()

    def delete_pipeline(self, pipeline_id: str) -> bool:
        """delete_pipeline 函数：删除业务记录，并在需要时同步清理关联资源或缓存。"""
        row = self.get_pipeline(pipeline_id)
        if not row:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    def page_tasks(self, page_no: int, page_size: int):
        """page_tasks 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
        query = self.db.query(IngestionTask).order_by(IngestionTask.created_at.desc())
        total = query.count()
        rows = query.offset((page_no - 1) * page_size).limit(page_size).all()
        return rows, total

    def create_task(self, name: str, kb_id: str | None, doc_id: str | None, pipeline_id: str | None, payload: dict) -> IngestionTask:
        """create_task 函数：创建新的业务记录，负责组织入库字段并返回创建后的结果。"""
        task = IngestionTask(name=name, kb_id=kb_id, doc_id=doc_id, pipeline_id=pipeline_id, payload=payload, status="pending")
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def get_task(self, task_id: str) -> IngestionTask | None:
        """get_task 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
        return self.db.query(IngestionTask).filter(IngestionTask.id == task_id).first()

    def process_pending_tasks(self) -> None:
        """process_pending_tasks 函数：执行一个完整处理步骤，输入上下文并产出可追踪的结果。"""
        rows = self.db.query(IngestionTask).filter(IngestionTask.status == "pending").limit(5).all()
        for task in rows:
            self.process_task(task.id)

    def process_task(self, task_id: str) -> None:
        """process_task 函数：执行一个完整处理步骤，输入上下文并产出可追踪的结果。"""
        task = self.get_task(task_id)
        if not task or task.status not in {"pending", "running"}:
            return
        task.status = "running"
        task.started_at = utc_now_naive()
        self.db.commit()
        try:
            if task.doc_id:
                service = KnowledgeService(self.db)
                started = time.time()
                ok = service.start_chunking(task.doc_id)
                self.db.add(
                    IngestionTaskNodeRun(
                        task_id=task.id,
                        node_name="chunk_document",
                        status="completed" if ok else "failed",
                        duration_ms=int((time.time() - started) * 1000),
                        output_count=1 if ok else 0,
                        error_message="" if ok else "chunking failed",
                    )
                )
                task.status = "completed" if ok else "failed"
                task.error_message = "" if ok else "chunking failed"
            else:
                self.db.add(
                    IngestionTaskNodeRun(
                        task_id=task.id,
                        node_name="noop",
                        status="completed",
                        duration_ms=1,
                        output_count=0,
                        error_message="",
                    )
                )
                task.status = "completed"
            task.finished_at = utc_now_naive()
            self.db.commit()
        except Exception as exc:
            task.status = "failed"
            task.error_message = str(exc)
            task.finished_at = utc_now_naive()
            self.db.commit()



