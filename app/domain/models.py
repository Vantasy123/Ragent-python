"""模块导读：本文件位于 app/domain/models.py，属于领域模型层。

主要职责：定义数据库表映射和核心业务实体，是持久化结构的来源。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import Base
from app.core.time_utils import utc_now_naive


def uuid_str() -> str:
    """生成数据库主键使用的 UUID 字符串。"""
    return str(uuid.uuid4())


class TimestampMixin:
    """统一审计时间字段。"""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)


class User(Base, TimestampMixin):
    """User 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "users"

    # 用户主键，系统内部用它关联会话、Trace、Agent 运行记录等数据。
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 登录账号，必须唯一，认证逻辑会用它查找用户。
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    nickname: Mapped[str] = mapped_column(String(128), default="")
    # 只保存密码哈希，不保存明文密码。
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # 角色决定接口权限，例如普通用户和管理员的运维能力不同。
    role: Mapped[str] = mapped_column(String(32), default="user")
    # 软开关：禁用后用户不能继续登录或访问受保护接口。
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class RevokedToken(Base):
    """RevokedToken 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "revoked_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # JWT 的唯一标识，退出登录后写入这里，用于拦截已撤销 token。
    token_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    # token 过期时间，后台可据此清理无效撤销记录。
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)


class SystemSetting(Base):
    """SystemSetting 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "system_setting"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 配置项名称，例如模型、检索、并发等运行时配置的键。
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    # 配置项内容统一以字符串保存，读取时再按 value_type 转换。
    value: Mapped[str] = mapped_column(Text, default="")
    # 标记 value 的真实类型，避免布尔值、数字和 JSON 被错误解析。
    value_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # 最后修改该配置的用户 ID，便于审计配置变更。
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)


class KnowledgeBase(Base, TimestampMixin):
    """KnowledgeBase 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "knowledge_base"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 知识库展示名称，前端列表和选择器主要显示该字段。
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    # Milvus collection 名称，MySQL 知识库和向量库通过它建立对应关系。
    collection_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # 当前知识库使用的 embedding 模型，重建索引时需要保持一致。
    embedding_model: Mapped[str] = mapped_column(String(100), default="text-embedding-v3")
    # 知识库总开关，关闭后检索链路应跳过该知识库。
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    documents: Mapped[list["KnowledgeDocument"]] = relationship(back_populates="knowledge_base", cascade="all, delete-orphan")


class KnowledgeDocument(Base, TimestampMixin):
    """KnowledgeDocument 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "knowledge_document"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 所属知识库 ID，删除知识库时文档会级联删除。
    kb_id: Mapped[str] = mapped_column(ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False)
    # 文档原始名称，前端展示和检索来源说明会用到。
    doc_name: Mapped[str] = mapped_column(String(500), nullable=False)
    # 上传文件在本地或对象存储中的访问路径。
    file_url: Mapped[str] = mapped_column(String(1000), default="")
    file_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    # 来源类型，例如 upload、url、manual，用于区分不同摄取方式。
    source_type: Mapped[str] = mapped_column(String(50), default="upload")
    source_location: Mapped[str] = mapped_column(String(1000), default="")
    # 文档处理状态，控制前端展示 pending/processing/completed/failed 等阶段。
    status: Mapped[str] = mapped_column(String(50), default="pending")
    process_mode: Mapped[str] = mapped_column(String(50), default="standard")
    # 关联的摄取流水线 ID，用于追踪该文档由哪条 pipeline 处理。
    pipeline_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 分块策略，例如 fixed、recursive、markdown、semantic。
    chunk_strategy: Mapped[str] = mapped_column(String(50), default="recursive")
    # 分块高级参数，使用 JSON 保存以兼容不同策略的扩展配置。
    chunk_config: Mapped[dict] = mapped_column(JSON, default=dict)
    # 当前文档已经生成的分块数量，便于列表页快速展示处理结果。
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule_cron: Mapped[str] = mapped_column(String(100), default="")
    # 文档级开关，关闭后该文档分块不应参与检索。
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 处理失败时记录可读错误，方便用户和运维定位。
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    knowledge_base: Mapped["KnowledgeBase"] = relationship(back_populates="documents")
    chunks: Mapped[list["KnowledgeChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    chunk_logs: Mapped[list["KnowledgeDocumentChunkLog"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class KnowledgeChunk(Base):
    """KnowledgeChunk 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "knowledge_chunk"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 所属文档 ID，删除文档时分块会级联删除。
    doc_id: Mapped[str] = mapped_column(ForeignKey("knowledge_document.id", ondelete="CASCADE"), nullable=False)
    # 冗余保存知识库 ID，便于按知识库过滤分块和做 BM25 关键词检索。
    kb_id: Mapped[str] = mapped_column(ForeignKey("knowledge_base.id", ondelete="CASCADE"), nullable=False)
    # 分块正文，是 BM25、RAG 上下文拼接和前端分块详情的核心内容。
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 分块在文档中的顺序，重建上下文或展示时用它恢复原文顺序。
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # 分块元数据，数据库列名为 metadata，代码中用 meta_data 避免和 SQLAlchemy 保留名冲突。
    meta_data: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    # 分块级开关，关闭后该片段不会参与检索。
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)

    document: Mapped["KnowledgeDocument"] = relationship(back_populates="chunks")


class KnowledgeDocumentChunkLog(Base):
    """KnowledgeDocumentChunkLog 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "knowledge_document_chunk_log"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 对应的文档 ID，用于把一次分块日志挂回文档详情页。
    doc_id: Mapped[str] = mapped_column(ForeignKey("knowledge_document.id", ondelete="CASCADE"), nullable=False)
    # 分块任务状态，展示本次处理是否成功、失败或仍在进行。
    status: Mapped[str] = mapped_column(String(50), default="pending")
    # 分块过程中的说明或错误信息，面向用户和排障人员阅读。
    message: Mapped[str] = mapped_column(Text, default="")
    # 本次任务实际产生的分块数量。
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)

    document: Mapped["KnowledgeDocument"] = relationship(back_populates="chunk_logs")


class IngestionPipeline(Base, TimestampMixin):
    """IngestionPipeline 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "ingestion_pipeline"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 流水线名称，表示一组可复用的文档处理步骤。
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    # 流水线节点配置，JSON 中保存节点顺序、参数和启停状态。
    nodes: Mapped[list] = mapped_column(JSON, default=list)
    # 流水线是否可用，关闭后不应被新任务选择。
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class IngestionTask(Base, TimestampMixin):
    """IngestionTask 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "ingestion_task"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 使用的流水线 ID，为空时表示使用默认处理流程。
    pipeline_id: Mapped[str | None] = mapped_column(ForeignKey("ingestion_pipeline.id"), nullable=True)
    # 任务关联的知识库 ID，便于按知识库查看摄取任务。
    kb_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 任务关联的文档 ID，处理完成后可回写文档状态。
    doc_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    source_type: Mapped[str] = mapped_column(String(50), default="upload")
    # 任务总状态，表示整个摄取流程当前处于哪个阶段。
    status: Mapped[str] = mapped_column(String(50), default="pending")
    # 任务失败时的错误摘要，避免只能去日志中查原因。
    error_message: Mapped[str] = mapped_column(Text, default="")
    # 任务输入参数，使用 JSON 保存不同来源、不同节点所需的扩展字段。
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    # 实际开始时间，用于计算排队等待和执行耗时。
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 实际结束时间，用于判断任务是否完成以及统计耗时。
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    node_runs: Mapped[list["IngestionTaskNodeRun"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class IngestionTaskNodeRun(Base):
    """IngestionTaskNodeRun 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "ingestion_task_node_run"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 所属摄取任务 ID，删除任务时节点运行记录会一起删除。
    task_id: Mapped[str] = mapped_column(ForeignKey("ingestion_task.id", ondelete="CASCADE"), nullable=False)
    # 节点名称，例如 fetcher、parser、chunker、indexer。
    node_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 单个节点的执行状态，用于定位流水线卡在哪一步。
    status: Mapped[str] = mapped_column(String(50), default="pending")
    # 节点耗时，便于发现解析、分块或索引中的性能瓶颈。
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    # 节点输出数量，例如生成了多少段文本或多少个分块。
    output_count: Mapped[int] = mapped_column(Integer, default=0)
    # 节点失败原因，比任务总错误更细粒度。
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)

    task: Mapped["IngestionTask"] = relationship(back_populates="node_runs")


class Conversation(Base, TimestampMixin):
    """Conversation 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "conversation"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 会话所属用户，允许为空是为了兼容匿名或历史数据。
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 会话标题，通常由第一条问题或前端重命名生成。
    title: Mapped[str] = mapped_column(String(255), default="新对话")
    # 会话消息数量，用于列表页快速展示和排序辅助。
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    # 会话摘要，可用于长对话压缩或后续上下文恢复。
    summary: Mapped[str] = mapped_column(Text, default="")

    messages: Mapped[list["ConversationMessage"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class ConversationMessage(Base):
    """ConversationMessage 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "conversation_message"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 所属会话 ID，删除会话时消息会级联删除。
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False)
    # 消息角色，例如 user、assistant、system，用于还原多轮上下文。
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    # 消息正文，是 MySQL 中保存的完整长期对话记录。
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 消息附加信息，数据库列名为 metadata，可保存 RAG 片段、模型信息等扩展数据。
    meta_data: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class MessageFeedback(Base):
    """MessageFeedback 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "message_feedback"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 被评价的消息 ID，通常指向助手回答。
    message_id: Mapped[str] = mapped_column(ForeignKey("conversation_message.id", ondelete="CASCADE"), nullable=False)
    # 反馈类型，例如 like、dislike，用于后续评估和优化回答质量。
    feedback_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # 用户补充说明，帮助定位回答哪里好或哪里有问题。
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)


class UserMemory(Base, TimestampMixin):
    """UserMemory 数据库模型：保存跨会话长期记忆，用于补充短期上下文窗口。"""

    __tablename__ = "user_memory"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 长期记忆按用户隔离，避免不同用户偏好互相污染。
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 来源会话和消息用于审计这条记忆从哪里抽取。
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # preference/profile/instruction 等类型，便于后续做不同注入策略。
    memory_type: Mapped[str] = mapped_column(String(32), default="preference")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 权重用于排序，显式“记住”类表达比普通偏好更可靠。
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    meta_data: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class TraceRun(Base):
    """TraceRun 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "trace_run"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 触发本次 Trace 的用户 ID，便于按用户审计调用链。
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 会话 ID，用于把一次问答中的 Trace 和对话记录关联起来。
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 前端或后台任务 ID，用于定位一次具体请求。
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 整体运行状态，表示这次 Trace 是否成功完成。
    status: Mapped[str] = mapped_column(String(20), default="success")
    # 整条链路总耗时，性能分析时优先看该字段。
    total_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)

    spans: Mapped[list["TraceSpan"]] = relationship(back_populates="trace_run", cascade="all, delete-orphan")
    evaluation_runs: Mapped[list["EvaluationRun"]] = relationship(back_populates="trace_run", cascade="all, delete-orphan")


class TraceSpan(Base):
    """TraceSpan 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "trace_span"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 所属 TraceRun ID，多个 Span 组成一次完整调用链。
    trace_id: Mapped[str] = mapped_column(ForeignKey("trace_run.id", ondelete="CASCADE"), nullable=False)
    # 当前 Span 的操作名称，例如 retrieval、llm、tool_call。
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    # 当前步骤状态，用于在 Trace 页面标记成功或失败。
    status: Mapped[str] = mapped_column(String(20), default="success")
    # 当前步骤耗时，用于定位慢步骤。
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    # Span 扩展信息，保存输入、输出摘要、检索片段、工具参数等可观测数据。
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    # 当前步骤失败时的错误信息。
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)

    trace_run: Mapped["TraceRun"] = relationship(back_populates="spans")


class EvaluationRun(Base):
    """EvaluationRun 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "evaluation_run"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 被评估的 TraceRun ID，评估结果围绕一次真实调用链生成。
    trace_id: Mapped[str] = mapped_column(ForeignKey("trace_run.id", ondelete="CASCADE"), nullable=False)
    # 可选会话 ID，用于把评估结果挂回对话。
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 可选消息 ID，用于定位具体哪条回答被评估。
    message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 评估运行状态，例如 completed 或 failed。
    status: Mapped[str] = mapped_column(String(20), default="completed")
    # 综合评分，便于列表和仪表盘快速排序。
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    # 评估摘要，给出本次回答质量的总体结论。
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)

    trace_run: Mapped["TraceRun"] = relationship(back_populates="evaluation_runs")
    metrics: Mapped[list["EvaluationMetric"]] = relationship(back_populates="evaluation_run", cascade="all, delete-orphan")
    issues: Mapped[list["EvaluationIssue"]] = relationship(back_populates="evaluation_run", cascade="all, delete-orphan")


class EvaluationMetric(Base):
    """EvaluationMetric 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "evaluation_metric"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 所属评估任务 ID。
    evaluation_run_id: Mapped[str] = mapped_column(ForeignKey("evaluation_run.id", ondelete="CASCADE"), nullable=False)
    # 冗余保存 Trace ID，方便不 join evaluation_run 时直接筛选。
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 评估维度，例如 outcome、process、tool、system。
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    # 指标名称，例如 faithfulness、latency、tool_success_rate。
    metric_key: Mapped[str] = mapped_column(String(100), nullable=False)
    # 指标得分，通常为 0 到 1 或约定区间。
    score: Mapped[float] = mapped_column(Float, default=0.0)
    # 评分原因，面向排查和报告展示。
    reason: Mapped[str] = mapped_column(Text, default="")
    # 评分证据，保存参与判断的片段、Span 或统计值。
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)

    evaluation_run: Mapped["EvaluationRun"] = relationship(back_populates="metrics")


class EvaluationIssue(Base):
    """EvaluationIssue 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "evaluation_issue"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 所属评估任务 ID。
    evaluation_run_id: Mapped[str] = mapped_column(ForeignKey("evaluation_run.id", ondelete="CASCADE"), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 问题维度，用于聚合“回答结果问题”或“过程问题”。
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    # 问题类型编码，便于前端筛选和后续统计。
    issue_key: Mapped[str] = mapped_column(String(100), nullable=False)
    # 严重程度，例如 low、medium、high。
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    # 人可读的问题说明。
    message: Mapped[str] = mapped_column(Text, default="")
    # 问题证据，保存触发该 issue 的上下文。
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)

    evaluation_run: Mapped["EvaluationRun"] = relationship(back_populates="issues")


class AgentRun(Base):
    """AgentRun 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "agent_run"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 关联的对话 ID，让 Agent 运行记录可以回到用户会话中查看。
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 关联 TraceRun，便于从 Agent 报告跳转到完整调用链。
    trace_id: Mapped[str | None] = mapped_column(ForeignKey("trace_run.id", ondelete="SET NULL"), nullable=True)
    # 发起本次 Agent 任务的用户 ID。
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 用户原始问题或运维任务描述。
    message: Mapped[str] = mapped_column(Text, default="")
    # Agent 运行状态，例如 running、success、failed、blocked。
    status: Mapped[str] = mapped_column(String(32), default="running")
    # Planner 生成的计划，使用 JSON 保存步骤列表，便于回放和审计。
    plan: Mapped[list] = mapped_column(JSON, default=list)
    # 最终报告，前端最终展示和历史回放主要读取该字段。
    final_report: Mapped[str] = mapped_column(Text, default="")
    # Agent 类型，例如 orchestrator、ops、react，用于区分不同执行链路。
    agent_type: Mapped[str] = mapped_column(String(32), default="orchestrator")
    # 父运行 ID，用于表达多 Agent 或子任务的层级关系。
    parent_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 子任务摘要，保存拆分后的协作任务信息。
    sub_tasks: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)

    steps: Mapped[list["AgentStep"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    tool_calls: Mapped[list["AgentToolCall"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    approvals: Mapped[list["AgentApproval"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    collaborations: Mapped[list["AgentCollaboration"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class AgentStep(Base):
    """AgentStep 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "agent_step"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 所属 AgentRun ID，多个步骤组成一次 Agent 执行计划。
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_run.id", ondelete="CASCADE"), nullable=False)
    # 步骤序号，决定计划展示和执行顺序。
    step_index: Mapped[int] = mapped_column(Integer, default=0)
    # 步骤标题，面向用户展示“当前正在做什么”。
    title: Mapped[str] = mapped_column(String(255), default="")
    # 本步骤希望调用的工具名称，为空表示不需要工具。
    tool_name: Mapped[str] = mapped_column(String(100), default="")
    # 工具参数或步骤参数，JSON 便于保存不同工具的不同参数结构。
    args: Mapped[dict] = mapped_column(JSON, default=dict)
    # 步骤状态，用于前端时间线和 Replanner 判断。
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # 步骤观察结果，记录工具返回或执行后的自然语言总结。
    observation: Mapped[str] = mapped_column(Text, default="")
    # 负责该步骤的 Agent 名称，用于多 Agent 协作审计。
    assigned_agent: Mapped[str] = mapped_column(String(32), default="")
    # Agent 对本步骤的推理或决策原因，帮助解释为什么这样执行。
    agent_reasoning: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)

    run: Mapped["AgentRun"] = relationship(back_populates="steps")


class AgentToolCall(Base):
    """AgentToolCall 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "agent_tool_call"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 所属 AgentRun ID，用于聚合一次任务中的所有工具调用。
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_run.id", ondelete="CASCADE"), nullable=False)
    # 可选步骤 ID，用于把工具调用精确挂到某个计划步骤下。
    step_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 实际调用的工具名称。
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 工具入参，审计时可以看到 Agent 准备执行什么。
    args: Mapped[dict] = mapped_column(JSON, default=dict)
    # 工具执行结果，保存结构化返回，便于最终报告引用。
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    # 工具调用状态，例如 success、failed、approval_required。
    status: Mapped[str] = mapped_column(String(32), default="success")
    # 风险级别，读操作通常为 read，写操作需要更严格控制。
    risk_level: Mapped[str] = mapped_column(String(20), default="read")
    # 审批状态，确保高风险工具不会被 Agent 直接执行。
    approval_status: Mapped[str] = mapped_column(String(32), default="not_required")
    # 工具耗时，用于定位慢工具或外部依赖问题。
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    # 工具失败原因，便于 Replanner 和人工排查。
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)

    run: Mapped["AgentRun"] = relationship(back_populates="tool_calls")


class AgentApproval(Base):
    """AgentApproval 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "agent_approval"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 所属 AgentRun ID，审批必须绑定到一次具体任务。
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_run.id", ondelete="CASCADE"), nullable=False)
    # 关联的工具调用 ID，用于审批通过后找到待执行工具。
    tool_call_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 申请执行的高风险工具名称。
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 待审批的工具参数，审批人需要看到这些参数才能判断风险。
    args: Mapped[dict] = mapped_column(JSON, default=dict)
    # 审批状态，例如 pending、approved、rejected。
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # 发起审批的用户或 Agent 运行上下文。
    requested_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 做出审批决定的管理员 ID。
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 审批意见，记录通过或拒绝的原因。
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)
    # 审批决定时间，为空表示还在等待处理。
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped["AgentRun"] = relationship(back_populates="approvals")


class AgentCollaboration(Base):
    """AgentCollaboration 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "agent_collaboration"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 所属 AgentRun ID，表示这条协作事件属于哪次任务。
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_run.id", ondelete="CASCADE"), nullable=False)
    # 发出协作消息的 Agent。
    from_agent: Mapped[str] = mapped_column(String(32), nullable=False)
    # 接收协作消息的 Agent。
    to_agent: Mapped[str] = mapped_column(String(32), nullable=False)
    # 协作事件类型，例如 message、handoff、result。
    event_type: Mapped[str] = mapped_column(String(50), default="message")
    # 协作事件的人类可读内容。
    content: Mapped[str] = mapped_column(Text, default="")
    # 协作事件的结构化数据，保存额外上下文。
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)

    run: Mapped["AgentRun"] = relationship(back_populates="collaborations")


class IntentTreeNode(Base, TimestampMixin):
    """IntentTreeNode 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "intent_tree_node"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 父节点 ID，为空表示这是意图树的顶层节点。
    parent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 意图名称，前端树形结构中展示该字段。
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    # 绑定的知识库 ID，用于把某类问题路由到特定知识库。
    kb_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 意图是否启用，关闭后路由和检索不应命中该节点。
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 排序或匹配优先级，数值越高可被更优先处理。
    priority: Mapped[int] = mapped_column(Integer, default=0)


class SampleQuestion(Base, TimestampMixin):
    """SampleQuestion 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "sample_question"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 示例问题，用于前端引导、意图测试或问答样例展示。
    question: Mapped[str] = mapped_column(String(1000), nullable=False)
    # 示例答案，可作为参考回答或测试期望结果。
    answer: Mapped[str] = mapped_column(Text, default="")
    # 示例是否启用，关闭后不再展示或参与测试。
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 展示排序字段，数值越小通常越靠前。
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class QueryTermMapping(Base, TimestampMixin):
    """QueryTermMapping 数据库模型：映射一张业务表，字段定义决定 MySQL 中保存什么数据，以及服务层如何读取和写入。"""
    __tablename__ = "query_term_mapping"
    # source_term 唯一，避免同一个用户查询词被映射到多个目标词造成歧义。
    __table_args__ = (UniqueConstraint("source_term", name="uq_source_term"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=uuid_str)
    # 用户可能输入的原始词，例如缩写、别名或业务俗称。
    source_term: Mapped[str] = mapped_column(String(255), nullable=False)
    # 系统希望检索时使用的标准词，用于提升召回准确性。
    target_term: Mapped[str] = mapped_column(String(255), nullable=False)
    # 映射是否启用，关闭后 query rewrite 不应使用该规则。
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
