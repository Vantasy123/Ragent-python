"""
数据模型定义模块 (Data Models Module)

本模块定义了 Ragent Python 应用的所有数据库模型，使用 SQLAlchemy ORM。
包含用户管理、知识库、数据摄取、对话历史、追踪等核心业务实体。

模型设计原则：
1. 使用 UUID 作为主键，确保全局唯一性
2. 统一的 TimestampMixin 提供创建和更新时间戳
3. 外键关系明确，级联删除保护数据完整性
4. JSON 字段存储灵活的元数据和配置信息
5. 索引优化查询性能

数据库表分类：
- 用户和认证：User, RevokedToken
- 系统配置：SystemSetting
- 知识库：KnowledgeBase, KnowledgeDocument, KnowledgeChunk
- 数据摄取：IngestionPipeline, IngestionTask, IngestionTaskNodeRun
- 对话管理：Conversation, ConversationMessage, MessageFeedback
- 性能追踪：TraceRun, TraceSpan
- 意图树：IntentTreeNode, SampleQuestion
"""

from __future__ import annotations

import uuid  # UUID 生成库
from datetime import datetime  # 日期时间处理

# SQLAlchemy 核心组件
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON  # JSON 类型支持

from database import Base  # 数据库基础配置


def uuid_str() -> str:
    """
    生成 UUID 字符串。

    用于为新记录生成全局唯一标识符。

    返回：
        str: UUID 字符串格式，如 "550e8400-e29b-41d4-a716-446655440000"
    """
    return str(uuid.uuid4())


class TimestampMixin:
    """
    时间戳混入类 (Timestamp Mixin)。

    为模型类提供统一的创建时间和更新时间字段。
    所有继承此混入的模型都会自动获得这两个字段。

    字段：
        created_at: 记录创建时间，默认为当前 UTC 时间
        updated_at: 记录最后更新时间，更新时自动设置为当前时间
    """
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class User(Base, TimestampMixin):
    """
    用户模型。

    存储系统用户的基本信息和认证凭据。

    字段：
        id: 用户唯一标识符（UUID）
        username: 用户名，唯一且必填
        nickname: 用户昵称，可选
        password_hash: 密码哈希值，必填
        role: 用户角色，默认为 "user"
        is_active: 是否激活状态，默认为 True
    """
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    nickname: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RevokedToken(Base):
    """
    已撤销的 Token 模型。

    存储已被撤销的 JWT token，用于防止 token 重复使用。
    当用户登出或 token 过期时，token ID 会被添加到此表中。

    字段：
        id: 记录唯一标识符
        token_id: JWT token 的唯一标识符（jti 字段）
        expires_at: token 过期时间
        created_at: 记录创建时间
    """
    __tablename__ = "revoked_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    token_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class SystemSetting(Base):
    """
    系统设置模型。

    存储系统的各种配置参数，支持不同数据类型的设置值。
    用于动态配置系统行为，而无需修改代码。

    字段：
        id: 设置唯一标识符
        key: 设置键名，唯一
        value: 设置值（字符串格式）
        value_type: 值的数据类型（用于解析）
        updated_by: 最后更新者用户 ID
        updated_at: 最后更新时间
    """
    __tablename__ = "system_setting"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, default="")
    value_type: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class KnowledgeBase(Base, TimestampMixin):
    __tablename__ = "knowledge_base"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    collection_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(100), default="text-embedding-v3")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    documents: Mapped[list["KnowledgeDocument"]] = relationship(back_populates="knowledge_base", cascade="all, delete-orphan")


class KnowledgeDocument(Base, TimestampMixin):
    __tablename__ = "knowledge_document"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    kb_id: Mapped[str] = mapped_column(ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False)
    doc_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_url: Mapped[str] = mapped_column(String(1000), default="")
    file_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    source_type: Mapped[str] = mapped_column(String(50), default="upload")
    source_location: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[str] = mapped_column(String(50), default="pending")
    process_mode: Mapped[str] = mapped_column(String(50), default="standard")
    pipeline_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_strategy: Mapped[str] = mapped_column(String(50), default="recursive")
    chunk_config: Mapped[dict] = mapped_column(JSON, default=dict)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule_cron: Mapped[str] = mapped_column(String(100), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    knowledge_base: Mapped["KnowledgeBase"] = relationship(back_populates="documents")
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    chunk_logs: Mapped[list["KnowledgeDocumentChunkLog"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunk"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    doc_id: Mapped[str] = mapped_column(ForeignKey("knowledge_document.id", ondelete="CASCADE"), nullable=False)
    kb_id: Mapped[str] = mapped_column(ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    meta_data: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    document: Mapped["KnowledgeDocument"] = relationship(back_populates="chunks")


class KnowledgeDocumentChunkLog(Base):
    __tablename__ = "knowledge_document_chunk_log"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    doc_id: Mapped[str] = mapped_column(ForeignKey("knowledge_document.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    message: Mapped[str] = mapped_column(Text, default="")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    document: Mapped["KnowledgeDocument"] = relationship(back_populates="chunk_logs")


class IngestionPipeline(Base, TimestampMixin):
    __tablename__ = "ingestion_pipeline"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    nodes: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class IngestionTask(Base, TimestampMixin):
    __tablename__ = "ingestion_task"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    pipeline_id: Mapped[str | None] = mapped_column(ForeignKey("ingestion_pipeline.id"), nullable=True)
    kb_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    doc_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    source_type: Mapped[str] = mapped_column(String(50), default="upload")
    status: Mapped[str] = mapped_column(String(50), default="pending")
    error_message: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    node_runs: Mapped[list["IngestionTaskNodeRun"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class IngestionTaskNodeRun(Base):
    __tablename__ = "ingestion_task_node_run"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    task_id: Mapped[str] = mapped_column(ForeignKey("ingestion_task.id", ondelete="CASCADE"), nullable=False)
    node_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    output_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    task: Mapped["IngestionTask"] = relationship(back_populates="node_runs")


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversation"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="新对话")
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, default="")

    messages: Mapped[list["ConversationMessage"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class ConversationMessage(Base):
    __tablename__ = "conversation_message"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta_data: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class MessageFeedback(Base):
    __tablename__ = "message_feedback"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    message_id: Mapped[str] = mapped_column(ForeignKey("conversation_message.id", ondelete="CASCADE"), nullable=False)
    feedback_type: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class TraceRun(Base):
    __tablename__ = "trace_run"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="success")
    total_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    spans: Mapped[list["TraceSpan"]] = relationship(back_populates="trace_run", cascade="all, delete-orphan")


class TraceSpan(Base):
    __tablename__ = "trace_span"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    trace_id: Mapped[str] = mapped_column(ForeignKey("trace_run.id", ondelete="CASCADE"), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="success")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    trace_run: Mapped["TraceRun"] = relationship(back_populates="spans")


class IntentTreeNode(Base, TimestampMixin):
    __tablename__ = "intent_tree_node"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    parent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    kb_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)


class SampleQuestion(Base, TimestampMixin):
    __tablename__ = "sample_question"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    question: Mapped[str] = mapped_column(String(1000), nullable=False)
    answer: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class QueryTermMapping(Base, TimestampMixin):
    __tablename__ = "query_term_mapping"
    __table_args__ = (UniqueConstraint("source_term", name="uq_source_term"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    source_term: Mapped[str] = mapped_column(String(255), nullable=False)
    target_term: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
