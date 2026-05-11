"""模块导读：本文件位于 app/core/database.py，属于核心基础设施。

主要职责：提供配置、数据库连接、Redis、时间、文本清洗等通用能力。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings


def _create_engine():
    """创建数据库引擎；SQLite 需要允许跨线程访问。"""

    connect_args = {}
    if settings.DATABASE_URL.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)


engine = _create_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI 数据库会话依赖，确保请求结束后关闭连接。"""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
