"""模块导读：本文件位于 app/services/schema_migrations.py，属于服务层。

主要职责：承接路由层请求，组织数据库、缓存、Trace、Agent 和外部组件完成业务流程。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

from sqlalchemy import Engine, text


def run_compatible_migrations(engine: Engine) -> None:
    """执行兼容性轻量迁移；失败不阻断应用启动。"""

    statements = [
        "ALTER TABLE knowledge_document ADD COLUMN content_hash VARCHAR(128)",
        "ALTER TABLE message_feedback ADD COLUMN reason_tags TEXT",
        "ALTER TABLE message_feedback ADD COLUMN expected_answer TEXT",
        """
        CREATE TABLE IF NOT EXISTS user_memory (
            id VARCHAR(64) PRIMARY KEY,
            user_id VARCHAR(64) NOT NULL,
            conversation_id VARCHAR(64),
            source_message_id VARCHAR(64),
            memory_type VARCHAR(32),
            content TEXT NOT NULL,
            weight FLOAT,
            metadata JSON,
            enabled BOOLEAN,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """,
    ]
    with engine.begin() as conn:
        for statement in statements:
            try:
                conn.execute(text(statement))
            except Exception:
                # SQLite/MySQL/PostgreSQL 的重复列错误都可以忽略，create_all 仍是事实来源。
                continue
