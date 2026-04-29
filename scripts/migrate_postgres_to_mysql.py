from __future__ import annotations

import os
from collections.abc import Iterable

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.text_sanitizer import sanitize_payload
from app.domain.models import Base


# 按依赖顺序迁移，避免外键引用失败。
TABLE_ORDER = [
    "users",
    "revoked_tokens",
    "system_setting",
    "knowledge_base",
    "knowledge_document",
    "knowledge_chunk",
    "knowledge_document_chunk_log",
    "ingestion_pipeline",
    "ingestion_task",
    "ingestion_task_node_run",
    "conversation",
    "conversation_message",
    "message_feedback",
    "trace_run",
    "trace_span",
    "evaluation_run",
    "evaluation_metric",
    "evaluation_issue",
    "sample_question",
    "query_term_mapping",
    "intent_tree_node",
    "agent_run",
    "agent_step",
    "agent_tool_call",
    "agent_approval",
]


def _iter_models() -> Iterable[type]:
    """按固定顺序返回 ORM 模型，确保迁移时外键顺序稳定。"""

    table_to_model = {mapper.local_table.name: mapper.class_ for mapper in Base.registry.mappers}
    for table_name in TABLE_ORDER:
        model = table_to_model.get(table_name)
        if model is not None:
            yield model


def _copy_table(source: Session, target: Session, model: type) -> int:
    """把单张表从源库复制到目标库；JSON/时间字段由 SQLAlchemy 负责序列化。"""

    # 这里必须使用 ORM 属性名而不是裸列名。
    # 例如 KnowledgeChunk 的数据库列名是 metadata，但 ORM 属性名是 meta_data；
    # 如果直接 getattr(row, "metadata")，会拿到 SQLAlchemy Declarative 的元数据对象而不是行值。
    attr_pairs = []
    for attr in model.__mapper__.column_attrs:
        column = attr.columns[0]
        attr_pairs.append((attr.key, column.name))

    rows = source.query(model).all()
    if not rows:
        return 0

    payload = []
    for row in rows:
        item = {}
        for attr_key, column_name in attr_pairs:
            item[column_name] = sanitize_payload(getattr(row, attr_key))
        payload.append(item)

    # 使用 merge 风格的批量插入，避免目标库中已存在记录时主键冲突。
    target.execute(model.__table__.insert().prefix_with("IGNORE"), payload)
    target.commit()
    return len(payload)


def main() -> None:
    """执行一次性业务数据迁移。"""

    source_url = os.getenv("SOURCE_DATABASE_URL")
    target_url = os.getenv("TARGET_DATABASE_URL")

    if not source_url or not target_url:
        raise RuntimeError("缺少 SOURCE_DATABASE_URL 或 TARGET_DATABASE_URL")

    source_engine = create_engine(source_url, pool_pre_ping=True)
    target_engine = create_engine(target_url, pool_pre_ping=True)

    # 先在目标库建表，避免迁移前目标库结构不完整。
    Base.metadata.create_all(target_engine)

    source_session = sessionmaker(bind=source_engine, autoflush=False, autocommit=False)()
    target_session = sessionmaker(bind=target_engine, autoflush=False, autocommit=False)()

    try:
        total = 0
        for model in _iter_models():
            count = _copy_table(source_session, target_session, model)
            print(f"{model.__tablename__}: {count}")
            total += count
        print(f"TOTAL: {total}")
    finally:
        source_session.close()
        target_session.close()


if __name__ == "__main__":
    main()
