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
        "ALTER TABLE evaluation_batch_run ADD COLUMN openai_eval_id VARCHAR(128)",
        "ALTER TABLE evaluation_batch_run ADD COLUMN openai_eval_run_id VARCHAR(128)",
        "ALTER TABLE evaluation_batch_run ADD COLUMN openai_eval_status VARCHAR(32)",
        "ALTER TABLE evaluation_batch_run ADD COLUMN openai_eval_report JSON",
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
        """
        CREATE TABLE IF NOT EXISTS evaluation_dataset (
            id VARCHAR(64) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            kb_id VARCHAR(64),
            tags JSON,
            enabled BOOLEAN,
            created_by VARCHAR(64),
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS evaluation_case (
            id VARCHAR(64) PRIMARY KEY,
            dataset_id VARCHAR(64) NOT NULL,
            question TEXT NOT NULL,
            expected_answer TEXT,
            expected_chunk_ids JSON,
            expected_keywords JSON,
            kb_id VARCHAR(64),
            tags JSON,
            enabled BOOLEAN,
            metadata JSON,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS evaluation_batch_run (
            id VARCHAR(64) PRIMARY KEY,
            dataset_id VARCHAR(64) NOT NULL,
            status VARCHAR(32),
            total_cases INTEGER,
            completed_cases INTEGER,
            failed_cases INTEGER,
            overall_score FLOAT,
            metric_summary JSON,
            summary TEXT,
            error_message TEXT,
            created_by VARCHAR(64),
            openai_eval_id VARCHAR(128),
            openai_eval_run_id VARCHAR(128),
            openai_eval_status VARCHAR(32),
            openai_eval_report JSON,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS evaluation_case_result (
            id VARCHAR(64) PRIMARY KEY,
            batch_run_id VARCHAR(64) NOT NULL,
            case_id VARCHAR(64) NOT NULL,
            trace_id VARCHAR(64),
            status VARCHAR(32),
            question TEXT,
            answer TEXT,
            expected_answer TEXT,
            retrieved_contexts JSON,
            metrics JSON,
            overall_score FLOAT,
            issue_summary JSON,
            error_message TEXT,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS system_setting_audit_log (
            id VARCHAR(64) PRIMARY KEY,
            key VARCHAR(128) NOT NULL,
            old_value TEXT,
            new_value TEXT,
            value_type VARCHAR(32) NOT NULL,
            changed_by VARCHAR(64),
            created_at DATETIME NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_audit_log (
            id VARCHAR(64) PRIMARY KEY,
            action VARCHAR(32) NOT NULL,
            target_user_id VARCHAR(64) NOT NULL,
            target_username VARCHAR(64) NOT NULL,
            old_value JSON,
            new_value JSON,
            changed_by VARCHAR(64),
            created_at DATETIME NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS security_audit_log (
            id VARCHAR(64) PRIMARY KEY,
            category VARCHAR(64) NOT NULL,
            action VARCHAR(64) NOT NULL,
            target_type VARCHAR(64),
            target_id VARCHAR(128),
            detail JSON,
            operator_id VARCHAR(64),
            created_at DATETIME NOT NULL
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
