"""FastAPI 应用启动入口，负责生命周期、路由注册和智能求职 Agent 核心能力初始化。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.security_headers import SecurityHeadersMiddleware
from app.api.routers import (
    audio,
    auth,
    conversations,
    dashboard,
    evaluations,
    ingestion,
    job_applications,
    job_autofill,
    job_matching,
    job_postings,
    job_resumes,
    knowledge,
    mock_interviews,
    project_config,
    security_audit,
    settings as settings_router,
    trace,
    unified_chat,
    users,
)
from app.services.auth import ensure_default_admin
from app.services.job_matching_service import ensure_default_job_samples
from app.services.schema_migrations import run_compatible_migrations

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except Exception:  # pragma: no cover - optional runtime dependency
    AsyncIOScheduler = None


scheduler = None


def run_ingestion_poll() -> None:
    """轮询待处理的摄取任务，供本地进程内调度器周期调用。"""

    from app.services.ingestion_service import IngestionService

    db = SessionLocal()
    try:
        IngestionService(db).process_pending_tasks()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：初始化数据库、默认管理员、求职初始样本与评测基线数据。"""

    global scheduler

    # create_all 负责首启建表；兼容迁移用于补齐旧库中缺失的轻量字段。
    Base.metadata.create_all(bind=engine)
    run_compatible_migrations(engine)

    # 迁移必须先于所有 ORM 查询执行；旧 MySQL 库缺列时避免默认数据初始化触发启动失败。
    db = SessionLocal()
    try:
        ensure_default_admin(db)
        from app.services.evaluation_service import ensure_default_evaluation_dataset
        ensure_default_evaluation_dataset(db)
        ensure_default_job_samples(db)
    finally:
        db.close()

    if AsyncIOScheduler is not None:
        scheduler = AsyncIOScheduler()
        scheduler.add_job(run_ingestion_poll, "interval", seconds=5, id="ingestion-poll")
        scheduler.start()

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)

app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    """容器健康检查和 Nginx 代理探活入口。"""

    return {"status": "ok", "message": "Ragent Intelligent Job Hunting Agent is running properly."}


# 所有业务路由集中注册：智能求职核心、智能体评测中心、知识库与后台管理
ROUTERS = [
    auth.router,
    users.router,
    dashboard.router,
    job_resumes.router,
    job_postings.router,
    job_matching.router,
    job_applications.router,
    mock_interviews.router,
    job_autofill.router,
    evaluations.router,
    settings_router.router,
    knowledge.router,
    ingestion.router,
    unified_chat.router,
    audio.router,
    conversations.router,
    trace.router,
    project_config.router,
    security_audit.router,
]

for router in ROUTERS:
    app.include_router(router, prefix="/api")
