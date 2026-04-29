"""FastAPI 应用启动入口，负责生命周期、路由注册和兼容接口。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.api.routers import (
    auth,
    chat,
    conversations,
    dashboard,
    evaluations,
    ingestion,
    knowledge,
    ops,
    ops_agent,
    settings as settings_router,
    trace,
    unified_chat,
    users,
)
from app.services.auth import ensure_default_admin
from app.services.schema_migrations import run_compatible_migrations

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except Exception:  # pragma: no cover - optional runtime dependency
    # APScheduler 是可选依赖；缺失时仅关闭本地轮询任务，不影响 API 主流程。
    AsyncIOScheduler = None


scheduler = None


def run_ingestion_poll() -> None:
    """轮询待处理的摄取任务，供本地进程内调度器周期调用。"""

    # 延迟导入可以避免 FastAPI 启动阶段产生服务层循环依赖。
    from app.services.ingestion_service import IngestionService

    db = SessionLocal()
    try:
        IngestionService(db).process_pending_tasks()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：初始化数据库、默认管理员和后台轮询任务。"""

    global scheduler

    # create_all 负责首启建表；兼容迁移用于补齐旧库中缺失的轻量字段。
    Base.metadata.create_all(bind=engine)
    run_compatible_migrations(engine)

    # 默认管理员必须在启动时保证存在，避免部署后无法进入后台。
    db = SessionLocal()
    try:
        ensure_default_admin(db)
    finally:
        db.close()

    # 第一阶段不引入 Redis 队列，摄取任务由进程内 APScheduler 轮询推进。
    if AsyncIOScheduler is not None:
        scheduler = AsyncIOScheduler()
        scheduler.add_job(run_ingestion_poll, "interval", seconds=5, id="ingestion-poll")
        scheduler.start()

    yield

    # 优雅关闭调度器，避免应用退出时残留后台任务。
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)

# 前端开发服务器、Docker Nginx 和本地调试都通过这里统一放行。
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

    return {"status": "ok", "message": "Ragent Python FastAPI is running properly."}


# 所有业务路由集中注册，便于入口文件一眼看清模块边界。
ROUTERS = [
    auth.router,
    users.router,
    dashboard.router,
    evaluations.router,
    settings_router.router,
    knowledge.router,
    ingestion.router,
    chat.router,
    unified_chat.router,
    conversations.router,
    trace.router,
    ops.router,
    ops_agent.router,
]

for router in ROUTERS:
    # 保留无前缀路由用于兼容历史前端调用。
    app.include_router(router)
    # 同时注册 /api 前缀，匹配 Docker Nginx 反向代理和对外 API 语义。
    app.include_router(router, prefix="/api")


@app.get("/api/sessions")
def api_sessions_compat():
    """兼容旧前端的 sessions 占位接口，后续可移除。"""

    return {"code": 200, "message": "success", "data": {"items": []}}


@app.get("/api/workflow/chat")
async def workflow_chat_compat(question: str | None = None, message: str | None = None):
    """兼容旧 workflow/chat 调用；真实聊天入口已迁移到 /agent/chat。"""

    content = question or message or ""
    return {"code": 200, "message": "success", "data": {"content": content, "compat": True}}


