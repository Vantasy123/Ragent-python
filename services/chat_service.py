"""
聊天服务模块 (Chat Service Module)

本模块实现智能对话系统的核心功能，包括对话管理、RAG（检索增强生成）、
流式响应和链路追踪。

核心功能：
1. 对话管理：创建、查询、重命名、删除对话
2. 消息管理：保存消息、生成对话摘要
3. RAG 增强回答：检索 + 重排序 + 生成
4. 流式响应支持
5. 链路追踪和错误处理
6. 用户反馈收集

主要组件：
- ConversationService: 对话和消息的 CRUD 操作
- stream_chat(): 主聊天处理流程，支持流式输出
- _prepare_rag_context(): RAG 上下文准备（查询重写 + 检索 + 重排序）
- generate_answer(): LLM 回答生成，支持流式输出

工作流程：
1. 用户发送消息 → 保存用户消息到数据库
2. 准备 RAG 上下文（查询重写 → 多路检索 → 重排序）
3. 构建提示词（结合检索结果）
4. 流式生成回答 → 实时返回 token
5. 保存助手回答到数据库
6. 记录追踪信息

异常处理：
- 自定义 ChatGenerationError 异常，携带阶段信息
- 每个处理阶段都有独立的错误追踪
- 支持任务中断（STOP_TASKS 机制）

性能优化：
- 对话摘要：长对话自动生成摘要以节省上下文
- 历史截断：只保留最近 N 轮对话
- 异步流式处理，支持实时响应
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

from sqlalchemy.orm import Session

from models import Conversation, ConversationMessage, MessageFeedback
from services.settings_service import RuntimeSettings, get_runtime_settings
from services.trace_service import TraceService

# 全局停止任务集合，用于中断正在进行的聊天任务
STOP_TASKS: set[str] = set()
logger = logging.getLogger(__name__)


class ChatGenerationError(RuntimeError):
    """
    聊天生成异常类
    
    用于在聊天生成的不同阶段抛出异常，携带阶段信息和详细错误信息。
    
    Attributes:
        stage: 异常发生的阶段名称（如 workflow_import, query_rewrite, retrieval, llm_stream 等）
        detail: 详细的错误描述信息
    """
    def __init__(self, stage: str, detail: str):
        super().__init__(detail)
        self.stage = stage
        self.detail = detail


def _role_label(role: str) -> str:
    """
    将角色标识转换为中文标签
    
    Args:
        role: 角色标识，"user" 或 "assistant"
        
    Returns:
        中文字符串，"用户" 或 "助手"
    """
    return "用户" if role == "user" else "助手"


def _build_summary_text(messages: list[ConversationMessage], max_chars: int) -> str:
    """
    构建对话摘要文本
    
    将消息列表格式化为可读的对话文本，如果超过最大长度则截断并添加省略号。
    
    Args:
        messages: 消息对象列表
        max_chars: 最大字符数限制
        
    Returns:
        格式化后的对话文本，如果为空则返回空字符串
    """
    if not messages:
        return ""
    text = "\n".join(f"{_role_label(message.role)}: {message.content}" for message in messages)
    if len(text) <= max_chars:
        return text
    return text[: max(max_chars - 1, 0)].rstrip() + "..."


class ConversationService:
    """
    对话服务类
    
    提供对话和消息的完整 CRUD 操作，包括对话创建、查询、更新、删除，
    以及消息的添加、查询和反馈管理。同时负责对话摘要的自动维护。
    
    Attributes:
        db: SQLAlchemy 数据库会话对象
    """
    def __init__(self, db: Session):
        """
        初始化对话服务
        
        Args:
            db: SQLAlchemy 数据库会话对象
        """
        self.db = db

    def create_conversation(self, user_id: str | None, title: str | None = None) -> Conversation:
        """
        创建新对话
        
        Args:
            user_id: 用户 ID，可选
            title: 对话标题，默认为"新对话"
            
        Returns:
            创建的 Conversation 对象
        """
        row = Conversation(user_id=user_id, title=(title or "新对话")[:255])
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """
        根据 ID 获取对话
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            Conversation 对象，如果不存在则返回 None
        """
        return self.db.query(Conversation).filter(Conversation.id == conversation_id).first()

    def list_conversations(self, user_id: str | None, page_no: int, page_size: int):
        """
        分页查询对话列表
        
        Args:
            user_id: 用户 ID 过滤条件，可选
            page_no: 页码（从 1 开始）
            page_size: 每页数量
            
        Returns:
            元组 (对话列表, 总数量)
        """
        query = self.db.query(Conversation)
        if user_id:
            query = query.filter(Conversation.user_id == user_id)
        total = query.count()
        rows = query.order_by(Conversation.updated_at.desc()).offset((page_no - 1) * page_size).limit(page_size).all()
        return rows, total

    def rename_conversation(self, conversation_id: str, title: str) -> Conversation | None:
        """
        重命名对话
        
        Args:
            conversation_id: 对话 ID
            title: 新标题
            
        Returns:
            更新后的 Conversation 对象，如果对话不存在则返回 None
        """
        row = self.get_conversation(conversation_id)
        if not row:
            return None
        row.title = title[:255]
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_conversation(self, conversation_id: str) -> bool:
        """
        删除对话及其所有消息
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            是否删除成功
        """
        row = self.get_conversation(conversation_id)
        if not row:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    def list_messages(self, conversation_id: str) -> list[ConversationMessage]:
        """
        获取对话的所有消息（按时间升序）
        
        Args:
            conversation_id: 对话 ID
            
        Returns:
            消息对象列表
        """
        return (
            self.db.query(ConversationMessage)
            .filter(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at.asc())
            .all()
        )

    def _refresh_summary(self, conversation: Conversation, runtime_settings: RuntimeSettings) -> None:
        """
        刷新对话摘要
        
        当对话消息数量达到阈值时，基于早期消息生成摘要以优化上下文长度。
        如果摘要功能未启用或消息数量不足，则清空摘要。
        
        Args:
            conversation: 对话对象
            runtime_settings: 运行时配置
        """
        if not runtime_settings.summary_enabled:
            conversation.summary = ""
            return

        threshold_messages = max(runtime_settings.summary_start_turns * 2, 2)
        if conversation.message_count < threshold_messages:
            conversation.summary = ""
            return

        keep_messages = max(runtime_settings.history_keep_turns * 2, 2)
        all_messages = self.list_messages(conversation.id)
        summary_source = all_messages[:-keep_messages] if len(all_messages) > keep_messages else all_messages
        conversation.summary = _build_summary_text(summary_source, runtime_settings.summary_max_chars)

    def add_message(self, conversation_id: str, role: str, content: str, metadata: dict | None = None) -> ConversationMessage:
        """
        添加消息到对话
        
        同时更新对话的消息计数、标题（首次用户消息）和摘要。
        
        Args:
            conversation_id: 对话 ID
            role: 消息角色（"user" 或 "assistant"）
            content: 消息内容
            metadata: 附加元数据，可选
            
        Returns:
            创建的 ConversationMessage 对象
        """
        row = ConversationMessage(conversation_id=conversation_id, role=role, content=content, meta_data=metadata or {})
        self.db.add(row)
        conversation = self.get_conversation(conversation_id)
        if conversation:
            runtime_settings = get_runtime_settings(self.db)
            conversation.message_count += 1
            # 首次用户消息时自动设置对话标题
            if role == "user" and conversation.message_count == 1:
                conversation.title = content[: runtime_settings.title_max_length] or conversation.title
        self.db.flush()
        if conversation:
            self._refresh_summary(conversation, runtime_settings)
        self.db.commit()
        self.db.refresh(row)
        return row

    def add_feedback(self, message_id: str, feedback_type: str, comment: str = "") -> MessageFeedback:
        """
        添加消息反馈
        
        Args:
            message_id: 消息 ID
            feedback_type: 反馈类型（如 "like", "dislike"）
            comment: 反馈评论，可选
            
        Returns:
            创建的 MessageFeedback 对象
        """
        feedback = MessageFeedback(message_id=message_id, feedback_type=feedback_type, comment=comment)
        self.db.add(feedback)
        self.db.commit()
        self.db.refresh(feedback)
        return feedback


def _conversation_history(service: ConversationService, conversation_id: str) -> list[dict[str, str]]:
    """
    获取对话历史
    
    提取最近的对话历史，如果启用了摘要功能且存在摘要，则在历史前添加系统消息形式的摘要。
    
    Args:
        service: 对话服务实例
        conversation_id: 对话 ID
        
    Returns:
        消息字典列表，每个字典包含 "role" 和 "content" 字段
    """
    rows = service.list_messages(conversation_id)
    conversation = service.get_conversation(conversation_id)
    runtime_settings = get_runtime_settings(service.db)
    max_messages = max(runtime_settings.history_keep_turns * 2, 2)
    history = [{"role": row.role, "content": row.content} for row in rows[-max_messages:]]
    if runtime_settings.summary_enabled and conversation and conversation.summary:
        return [{"role": "system", "content": f"对话摘要:\n{conversation.summary}"}] + history
    return history


def _build_rag_prompt(question: str, retrieved_chunks: list) -> str:
    """
    构建 RAG 提示词
    
    将检索到的知识片段和问题组合成结构化的提示词，引导模型基于知识库回答。
    如果没有检索结果，则直接返回原始问题。
    
    Args:
        question: 用户问题
        retrieved_chunks: 检索到的知识片段列表
        
    Returns:
        构建好的提示词字符串
    """
    if not retrieved_chunks:
        return question

    context_text = "\n\n".join(f"[{index + 1}] {chunk.content}" for index, chunk in enumerate(retrieved_chunks[:5]))
    return (
        "请严格基于给定知识库内容回答用户问题。"
        "如果知识库内容不足以支持结论，就明确说不知道，不要编造来源。\n\n"
        f"知识库片段:\n{context_text}\n\n"
        f"问题: {question}\n\n"
        "请给出准确、简洁的回答。"
    )


async def _prepare_rag_context(
    service: ConversationService,
    conversation_id: str,
    message: str,
) -> tuple[str, list, str]:
    """
    准备 RAG 上下文
    
    执行完整的 RAG 流程：查询重写 → 多路检索 → 重排序 → 构建提示词。
    每个步骤都有独立的异常处理和错误追踪。
    
    Args:
        service: 对话服务实例
        conversation_id: 对话 ID
        message: 用户消息
        
    Returns:
        三元组 (重写后的查询, 最终的知识片段列表, 构建的提示词)
        
    Raises:
        ChatGenerationError: 在工作流导入、查询重写或检索失败时抛出
    """
    # 导入工作流服务（查询重写器、检索器、重排序器）
    try:
        from workflow import multi_channel_retriever, query_rewriter, reranker
    except Exception as exc:
        logger.exception("Failed to import workflow services")
        raise ChatGenerationError("workflow_import", f"{type(exc).__name__}: {exc}") from exc

    history = _conversation_history(service, conversation_id)
    runtime_settings = get_runtime_settings(service.db)

    # 步骤1: 查询重写 - 基于对话历史优化用户查询
    try:
        rewritten = query_rewriter.rewrite(message, history)
    except Exception as exc:
        logger.exception("Query rewrite failed")
        raise ChatGenerationError("query_rewrite", f"{type(exc).__name__}: {exc}") from exc

    # 步骤2: 多路检索 - 从知识库中检索相关文档
    try:
        retrieved_chunks = multi_channel_retriever.retrieve(query=rewritten, top_k=runtime_settings.top_k)
    except Exception as exc:
        logger.exception("Knowledge retrieval failed")
        raise ChatGenerationError("retrieval", f"{type(exc).__name__}: {exc}") from exc

    # 步骤3: 重排序 - 对检索结果进行相关性排序并过滤低分结果
    try:
        documents = [chunk.content for chunk in retrieved_chunks]
        reranked_results = reranker.rerank_with_threshold(rewritten, documents)
        if reranked_results:
            final_chunks = []
            for result in reranked_results:
                idx = result["index"]
                if idx < len(retrieved_chunks):
                    chunk = retrieved_chunks[idx]
                    chunk.score = result["score"]
                    final_chunks.append(chunk)
        else:
            final_chunks = retrieved_chunks
    except Exception as exc:
        logger.warning("Rerank failed, fallback to retrieved chunks: %s", exc)
        final_chunks = retrieved_chunks

    prompt = _build_rag_prompt(message, final_chunks)
    return rewritten, final_chunks, prompt


async def generate_answer(prompt: str, deep_thinking: bool = False) -> AsyncIterator[str]:
    """
    生成 LLM 回答
    
    调用大语言模型流式生成回答内容，支持深度思考模式。
    
    Args:
        prompt: 提示词
        deep_thinking: 是否启用深度思考模式
        
    Yields:
        生成的文本片段（token）
        
    Raises:
        ChatGenerationError: 在工作流导入、LangChain 导入或模型流式调用失败时抛出
    """
    # 导入 LLM 构建函数
    try:
        from workflow import build_primary_llm
    except Exception as exc:
        logger.exception("Failed to import workflow llm")
        raise ChatGenerationError("workflow_import", f"{type(exc).__name__}: {exc}") from exc

    # 导入 LangChain 消息类型
    try:
        from langchain_core.messages import HumanMessage
    except Exception as exc:
        logger.exception("Failed to import langchain HumanMessage")
        raise ChatGenerationError("langchain_import", f"{type(exc).__name__}: {exc}") from exc

    # 根据深度思考模式调整提示词
    final_prompt = prompt if not deep_thinking else f"请进行更深入的回答：{prompt}"

    # 流式调用 LLM 并逐块返回内容
    try:
        llm = build_primary_llm()
        async for chunk in llm.astream([HumanMessage(content=final_prompt)]):
            content = getattr(chunk, "content", "")
            if content:
                yield content
    except Exception as exc:
        logger.exception("Model streaming failed")
        raise ChatGenerationError("llm_stream", f"{type(exc).__name__}: {exc}") from exc


async def stream_chat(
    db: Session,
    conversation_id: str,
    message: str,
    task_id: str,
    deep_thinking: bool = False,
) -> AsyncIterator[dict]:
    """
    流式聊天主函数
    
    完整的聊天处理流程：保存用户消息 → 准备 RAG 上下文 → 流式生成回答 → 保存助手消息。
    全程支持链路追踪、错误处理和任务中断。
    
    Args:
        db: 数据库会话
        conversation_id: 对话 ID
        message: 用户消息内容
        task_id: 任务 ID（用于追踪和中断控制）
        deep_thinking: 是否启用深度思考模式
        
    Yields:
        字典类型的流式事件，包括：
        - {"type": "token", "content": "..."}: 文本片段
        - {"type": "done", ...}: 完成事件
        - {"type": "error", "content": "..."}: 错误事件
        - {"type": "stopped", ...}: 任务中断事件
        
    Raises:
        ChatGenerationError: 内部捕获并转换为错误事件返回
    """
    trace_service = TraceService(db)
    trace = trace_service.start_run(session_id=conversation_id, task_id=task_id)
    service = ConversationService(db)
    service.add_message(conversation_id, "user", message, {"taskId": task_id, "traceId": trace.id})

    text = ""
    # 创建各阶段的追踪 span
    intent_span = trace_service.create_span(trace.id, "intent_analysis")
    rewrite_span = trace_service.create_span(trace.id, "query_rewrite")
    retrieval_span = trace_service.create_span(trace.id, "retrieval")
    generation_span = trace_service.create_span(trace.id, "generation")
    rewrite_recorded = False
    retrieval_recorded = False

    try:
        # 标记意图分析完成
        trace_service.complete_span(intent_span, metadata={"mode": "rag"})
        # 准备 RAG 上下文（查询重写 + 检索 + 重排序）
        rewritten, retrieved_chunks, prompt = await _prepare_rag_context(service, conversation_id, message)
        trace_service.complete_span(rewrite_span, metadata={"rewritten": rewritten})
        rewrite_recorded = True
        # 记录检索结果信息
        trace_service.complete_span(
            retrieval_span,
            metadata={
                "chunks": len(retrieved_chunks),
                "sources": [chunk.metadata.get("doc_id") for chunk in retrieved_chunks[:5]],
            },
        )
        retrieval_recorded = True

        # 流式生成回答并实时返回 token
        async for token in generate_answer(prompt, deep_thinking=deep_thinking):
            # 检查任务是否被中断
            if task_id in STOP_TASKS:
                STOP_TASKS.discard(task_id)
                trace_service.complete_span(generation_span, status="error", error_message="task stopped")
                trace_service.complete_run(trace.id, "error")
                yield {"type": "stopped", "taskId": task_id, "traceId": trace.id}
                return
            text += token
            yield {"type": "token", "content": token, "taskId": task_id, "traceId": trace.id}
    except ChatGenerationError as exc:
        # 处理聊天生成异常，记录错误信息并返回错误事件
        diagnostic = f"聊天链路失败：[{exc.stage}] {exc.detail}"
        service.add_message(
            conversation_id,
            "assistant",
            diagnostic,
            {"taskId": task_id, "traceId": trace.id, "errorStage": exc.stage},
        )
        if not rewrite_recorded:
            trace_service.complete_span(rewrite_span, status="error", error_message=diagnostic, stage=exc.stage)
        if not retrieval_recorded:
            trace_service.complete_span(retrieval_span, status="error", error_message=diagnostic, stage=exc.stage)
        trace_service.complete_span(generation_span, status="error", error_message=diagnostic, stage=exc.stage)
        trace_service.complete_run(trace.id, "error")
        yield {"type": "error", "content": diagnostic, "taskId": task_id, "traceId": trace.id, "stage": exc.stage}
        return

    # 保存助手回答并完成追踪
    service.add_message(conversation_id, "assistant", text, {"taskId": task_id, "traceId": trace.id})
    trace_service.complete_span(generation_span, metadata={"responseLength": len(text)})
    trace_service.complete_run(trace.id, "success")
    yield {"type": "done", "taskId": task_id, "traceId": trace.id}
