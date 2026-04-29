"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

from sqlalchemy import Engine, text


def run_compatible_migrations(engine: Engine) -> None:
    """执行兼容性轻量迁移；失败不阻断应用启动。"""

    statements = [
        "ALTER TABLE knowledge_document ADD COLUMN content_hash VARCHAR(128)",
        "ALTER TABLE message_feedback ADD COLUMN reason_tags TEXT",
        "ALTER TABLE message_feedback ADD COLUMN expected_answer TEXT",
    ]
    with engine.begin() as conn:
        for statement in statements:
            try:
                conn.execute(text(statement))
            except Exception:
                # SQLite/MySQL/PostgreSQL 的重复列错误都可以忽略，create_all 仍是事实来源。
                continue
