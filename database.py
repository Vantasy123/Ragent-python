"""
数据库配置模块 (Database Configuration Module)

本模块负责 SQLAlchemy 数据库引擎的配置和会话管理。
提供数据库连接、会话工厂和基础模型类的创建。

支持的数据库：
- SQLite：轻量级文件数据库，适合开发和测试
- PostgreSQL：生产级关系型数据库
- MySQL：另一种常见的关系型数据库

配置说明：
- 使用连接池预检（pool_pre_ping）确保连接有效性
- SQLite 特殊配置：允许多线程访问
- 会话自动提交和刷新关闭，提高性能
"""

from __future__ import annotations

from sqlalchemy import create_engine  # 数据库引擎创建
from sqlalchemy.orm import declarative_base, sessionmaker  # ORM 基础类和会话工厂

from config import settings  # 应用配置


def _create_engine():
    """
    创建数据库引擎。

    根据配置的数据库 URL 创建相应的引擎实例。
    支持不同数据库类型的特殊配置。

    返回：
        Engine: SQLAlchemy 数据库引擎实例

    配置选项：
        - pool_pre_ping: 连接前检查连接是否有效
        - check_same_thread: SQLite 多线程支持（仅 SQLite）
    """
    connect_args = {}  # 连接参数字典

    # SQLite 特殊配置：允许在不同线程中使用同一连接
    if settings.DATABASE_URL.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    # 创建数据库引擎
    return create_engine(
        settings.DATABASE_URL,      # 数据库连接 URL
        pool_pre_ping=True,         # 连接前检查连接有效性
        connect_args=connect_args   # 额外的连接参数
    )


# 创建全局数据库引擎实例
engine = _create_engine()

# 创建会话工厂
# autocommit=False: 不自动提交事务
# autoflush=False: 不自动刷新变更到数据库
# bind=engine: 绑定到创建的引擎
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# 创建声明式基类，所有模型类都继承自此基类
Base = declarative_base()


def get_db():
    """
    数据库会话生成器。

    FastAPI 的依赖注入函数，提供数据库会话实例。
    使用生成器模式确保会话在使用后被正确关闭。

    使用方式：
        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            return db.query(Item).all()

    异常处理：
        - 无论是否发生异常，都会确保会话被关闭
        - 防止数据库连接泄漏
    """
    db = SessionLocal()  # 创建新的数据库会话
    try:
        yield db  # 返回会话给调用者
    finally:
        db.close()  # 确保会话被关闭
