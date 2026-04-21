"""
Ragent Python 主入口文件 (Main Entry Point)

本文件是 Ragent AI 代理系统的 FastAPI 后端服务主入口，负责：
1. 应用初始化和配置
2. 数据库表结构创建
3. 默认管理员用户创建
4. 定时任务调度器启动
5. CORS 中间件配置
6. API 路由注册
7. 健康检查端点

技术栈：
- FastAPI: 现代化的 Python Web 框架
- SQLAlchemy: ORM 数据库操作
- APScheduler: 定时任务调度
- CORS: 跨域资源共享支持

启动流程：
1. 应用启动时执行 lifespan 函数
2. 创建数据库表结构
3. 初始化默认管理员账户
4. 启动定时任务（每 5 秒检查待处理的数据摄取任务）
5. 注册所有 API 路由
6. 启动 FastAPI 服务器
"""

from __future__ import annotations

from contextlib import asynccontextmanager  # 异步上下文管理器，用于应用生命周期管理

from fastapi import FastAPI  # FastAPI 框架主类
from fastapi.middleware.cors import CORSMiddleware  # CORS 跨域中间件

# 项目内部模块导入
from config import settings  # 应用配置
from database import Base, SessionLocal, engine  # 数据库基础配置
from models import User  # 用户模型（用于默认管理员创建）
from routers import (  # API 路由模块
    auth, chat, conversations, dashboard, ingestion,
    knowledge, ops, settings as settings_router, trace, users
)
from services.auth import ensure_default_admin  # 默认管理员创建服务

# 可选依赖导入（APScheduler 可能在某些部署环境中不可用）
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler  # 异步定时任务调度器
except Exception:  # pragma: no cover - optional dependency at runtime
    AsyncIOScheduler = None  # 如果导入失败，设置为 None


# 全局调度器变量
scheduler = None


def run_ingestion_poll() -> None:
    """
    数据摄取轮询任务。

    定时执行的后台任务，每 5 秒检查一次是否有待处理的数据摄取任务。
    这个任务在应用启动后由 APScheduler 调度执行。

    工作流程：
    1. 创建数据库会话
    2. 调用数据摄取服务处理待处理任务
    3. 确保数据库连接被正确关闭

    注意：这是一个同步函数，在异步调度器中运行。
    """
    from services.ingestion_service import IngestionService  # 延迟导入避免循环依赖

    # 创建数据库会话
    db = SessionLocal()
    try:
        # 处理所有待处理的数据摄取任务
        IngestionService(db).process_pending_tasks()
    finally:
        # 确保数据库连接被关闭，即使发生异常
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 应用生命周期管理器。

    这个异步上下文管理器在应用启动和关闭时执行相应的初始化和清理工作。
    相当于其他框架中的应用启动钩子（startup hook）和关闭钩子（shutdown hook）。

    启动时执行：
    1. 创建所有数据库表
    2. 确保默认管理员用户存在
    3. 启动定时任务调度器

    关闭时执行：
    1. 停止定时任务调度器

    参数：
        app (FastAPI): FastAPI 应用实例

    使用方式：
        app = FastAPI(lifespan=lifespan)
    """
    global scheduler

    # ========== 应用启动阶段 ==========
    # 1. 创建数据库表结构（如果不存在）
    Base.metadata.create_all(bind=engine)

    # 2. 确保默认管理员用户存在
    db = SessionLocal()
    ensure_default_admin(db)
    db.close()

    # 3. 启动定时任务调度器（如果可用）
    if AsyncIOScheduler is not None:
        scheduler = AsyncIOScheduler()
        # 添加数据摄取轮询任务：每 5 秒执行一次
        scheduler.add_job(
            run_ingestion_poll,      # 要执行的函数
            "interval",              # 任务类型：间隔执行
            seconds=5,               # 间隔时间：5 秒
            id="ingestion-poll"      # 任务 ID，用于后续管理
        )
        scheduler.start()  # 启动调度器

    # ========== 应用运行阶段 ==========
    yield  # 控制权交给 FastAPI，应用开始处理请求

    # ========== 应用关闭阶段 ==========
    if scheduler is not None:
        # 优雅关闭调度器，不等待正在运行的任务完成
        scheduler.shutdown(wait=False)


# 创建 FastAPI 应用实例
app = FastAPI(
    title=settings.APP_NAME,      # 应用标题
    version=settings.APP_VERSION, # 应用版本
    lifespan=lifespan             # 生命周期管理器
)

# 配置 CORS 中间件，允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # 允许的源域名列表
    allow_credentials=True,                  # 允许发送凭据（cookies, authorization headers）
    allow_methods=["*"],                     # 允许的 HTTP 方法
    allow_headers=["*"],                     # 允许的请求头
)


@app.get("/api/health")
def health():
    """
    健康检查端点。

    用于监控应用状态的简单端点。负载均衡器、容器编排系统（如 Kubernetes）
    或监控工具可以定期调用此端点来检查应用是否正常运行。

    返回：
        dict: 包含状态信息和确认消息的字典

    HTTP 响应示例：
        {
            "status": "ok",
            "message": "Ragent Python FastAPI is running properly."
        }
    """
    return {"status": "ok", "message": "Ragent Python FastAPI is running properly."}


# 注册所有 API 路由模块
# 每个路由模块都包含一组相关的 API 端点
for router in [
    auth.router,           # 认证相关路由（登录、注册、token 刷新）
    users.router,          # 用户管理路由（CRUD 操作）
    dashboard.router,      # 仪表板路由（统计信息、概览数据）
    settings_router.router,# 系统设置路由（配置管理）
    knowledge.router,      # 知识库路由（文档管理、搜索）
    ingestion.router,      # 数据摄取路由（文件上传、处理状态）
    chat.router,           # 聊天路由（对话接口）
    conversations.router,  # 会话路由（对话历史管理）
    trace.router,          # 追踪路由（性能监控、调试信息）
    ops.router,            # 运维路由（系统操作、健康检查）
]:
    # 将路由注册到应用中，同时提供两个前缀版本：
    # 1. 无前缀版本：/auth, /users, /dashboard 等
    # 2. /api 前缀版本：/api/auth, /api/users, /api/dashboard 等
    app.include_router(router)
    app.include_router(router, prefix="/api")


@app.get("/api/sessions")
def api_sessions_compat():
    """
    会话兼容性端点（临时）。

    为保持向后兼容性提供的临时端点。某些客户端可能仍然调用此端点
    来获取会话列表，但实际的会话管理已移至 conversations 路由。

    返回：
        dict: 空的会话列表，保持 API 兼容性

    注意：这是一个临时兼容性端点，应该在未来版本中移除。
    """
    return {"code": 200, "message": "success", "data": {"items": []}}


@app.get("/api/workflow/chat")
async def workflow_chat_compat(question: str | None = None, message: str | None = None):
    """
    工作流聊天兼容性端点（临时）。

    为保持向后兼容性提供的临时端点。某些客户端可能仍然使用旧的
    工作流聊天接口，但实际的聊天功能已移至 chat 路由。

    参数：
        question (str, optional): 用户问题（旧接口参数名）
        message (str, optional): 用户消息（新接口参数名）

    返回：
        dict: 包含用户输入的响应，保持 API 兼容性

    注意：这是一个临时兼容性端点，应该在未来版本中移除。
    """
    # 支持旧接口的参数名（question）和新接口的参数名（message）
    content = question or message or ""
    return {"code": 200, "message": "success", "data": {"content": content, "compat": True}}


@app.get("/api/health")
def health():
    return {"status": "ok", "message": "Ragent Python FastAPI is running properly."}


for router in [
    auth.router,
    users.router,
    dashboard.router,
    settings_router.router,
    knowledge.router,
    ingestion.router,
    chat.router,
    conversations.router,
    trace.router,
    ops.router,
]:
    app.include_router(router)
    app.include_router(router, prefix="/api")


@app.get("/api/sessions")
def api_sessions_compat():
    return {"code": 200, "message": "success", "data": {"items": []}}


@app.get("/api/workflow/chat")
async def workflow_chat_compat(question: str | None = None, message: str | None = None):
    content = question or message or ""
    return {"code": 200, "message": "success", "data": {"content": content, "compat": True}}
