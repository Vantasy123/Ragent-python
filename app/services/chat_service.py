"""模块导读：本文件位于 app/services/chat_service.py，属于服务层。

主要职责：承接路由层请求，组织数据库、缓存、Trace、Agent 和外部组件完成业务流程。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time_utils import utc_now_naive
from app.agents.react_agent import ConversationReactAgent
from app.domain.models import Conversation, ConversationMessage, MessageFeedback
from app.services.context_window import context_window
from app.services.long_term_memory_service import LongTermMemoryService
from app.services.settings_service import get_runtime_settings
from app.services.trace_service import TraceService

logger = logging.getLogger(__name__)


class ChatGenerationError(RuntimeError):
    """聊天链路异常，保留失败阶段以便前端和 Trace 展示。"""

    def __init__(self, stage: str, detail: str):
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
        super().__init__(detail)
        self.stage = stage
        self.detail = detail


class ConversationService:
    """会话与消息的数据库服务。"""

    def __init__(self, db: Session):
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
        self.db = db

    def create_conversation(self, user_id: str | None, title: str | None = None) -> Conversation:
        """create_conversation 函数：创建新的业务记录，负责组织入库字段并返回创建后的结果。"""
        row = Conversation(user_id=user_id, title=(title or "新对话")[:255])
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """get_conversation 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
        return self.db.query(Conversation).filter(Conversation.id == conversation_id).first()

    def list_conversations(self, user_id: str | None, page_no: int, page_size: int):
        """list_conversations 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
        query = self.db.query(Conversation)
        if user_id:
            query = query.filter(Conversation.user_id == user_id)
        # 会话主体可以保留在数据库中，但列表只展示仍有对话记录的会话。
        query = query.filter(Conversation.message_count > 0)
        total = query.count()
        rows = query.order_by(Conversation.updated_at.desc()).offset((page_no - 1) * page_size).limit(page_size).all()
        return rows, total

    def rename_conversation(self, conversation_id: str, title: str) -> Conversation | None:
        """rename_conversation 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        row = self.get_conversation(conversation_id)
        if not row:
            return None
        row.title = title[:255]
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_conversation(self, conversation_id: str) -> bool:
        """delete_conversation 函数：删除业务记录，并在需要时同步清理关联资源或缓存。"""
        row = self.get_conversation(conversation_id)
        if not row:
            return False
        self.db.delete(row)
        self.db.commit()
        context_window.clear_window(conversation_id)
        return True

    def clear_messages(self, conversation_id: str) -> int | None:
        """清空会话消息，但保留会话主体、标题、Trace 和 AgentRun 等运行数据。"""

        conversation = self.get_conversation(conversation_id)
        if not conversation:
            return None

        message_ids = [
            row.id
            for row in self.db.query(ConversationMessage.id)
            .filter(ConversationMessage.conversation_id == conversation_id)
            .all()
        ]
        if not message_ids:
            conversation.message_count = 0
            conversation.updated_at = utc_now_naive()
            self.db.commit()
            context_window.clear_window(conversation_id)
            return 0

        # 先删除消息反馈，避免部分数据库未启用外键级联时产生孤立反馈。
        self.db.query(MessageFeedback).filter(MessageFeedback.message_id.in_(message_ids)).delete(synchronize_session=False)
        deleted = (
            self.db.query(ConversationMessage)
            .filter(ConversationMessage.conversation_id == conversation_id)
            .delete(synchronize_session=False)
        )
        conversation.message_count = 0
        conversation.updated_at = utc_now_naive()
        self.db.commit()
        context_window.clear_window(conversation_id)
        return deleted

    def list_messages(self, conversation_id: str) -> list[ConversationMessage]:
        """list_messages 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
        return (
            self.db.query(ConversationMessage)
            .filter(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at.asc())
            .all()
        )

    def add_message(self, conversation_id: str, role: str, content: str, metadata: dict | None = None) -> ConversationMessage:
        """add_message 函数：向已有对象或存储中追加一条新数据，用于维护消息、Span 或工具结果。"""
        row = ConversationMessage(conversation_id=conversation_id, role=role, content=content, meta_data=metadata or {})
        self.db.add(row)
        conversation = self.get_conversation(conversation_id)
        if conversation:
            runtime = get_runtime_settings(self.db)
            conversation.message_count += 1
            if role == "user" and conversation.message_count == 1:
                conversation.title = content[: runtime.title_max_length] or conversation.title
        self.db.commit()
        self.db.refresh(row)
        runtime = get_runtime_settings(self.db)
        keep = max(runtime.history_keep_turns * 2, 2)
        context_window.append_message(conversation_id, role, content, keep, row.created_at)
        return row

    def add_feedback(self, message_id: str, feedback_type: str, comment: str = "") -> MessageFeedback:
        """add_feedback 函数：向已有对象或存储中追加一条新数据，用于维护消息、Span 或工具结果。"""
        row = MessageFeedback(message_id=message_id, feedback_type=feedback_type, comment=comment)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row


def _history(service: ConversationService, conversation_id: str) -> list[dict[str, str]]:
    """_history 函数：准备模型调用前需要的上下文、提示词或历史消息。"""
    runtime = get_runtime_settings(service.db)
    keep = max(runtime.history_keep_turns * 2, 2)
    cached = context_window.get_window(conversation_id, keep)
    if cached:
        return cached[-keep:]
    rows = service.list_messages(conversation_id)
    context_window.rebuild_window(conversation_id, rows, keep)
    return [{"role": row.role, "content": row.content} for row in rows[-keep:]]


def _chunk_content(chunk: Any) -> str:
    """统一读取检索片段正文，兼容自定义 RetrievedChunk 和 LangChain Document。"""

    return str(getattr(chunk, "content", getattr(chunk, "page_content", str(chunk))) or "")


def _chunk_metadata(chunk: Any) -> dict[str, Any]:
    """统一读取检索片段元数据，缺失时返回空字典，避免引用构造时反复判空。"""

    metadata = getattr(chunk, "metadata", {}) or {}
    return metadata if isinstance(metadata, dict) else {}


def _source_title(metadata: dict[str, Any]) -> str:
    """从元数据中挑选最适合展示给用户的来源名称。"""

    return str(
        metadata.get("source")
        or metadata.get("doc_name")
        or metadata.get("docName")
        or metadata.get("source_path")
        or metadata.get("doc_id")
        or "未知来源"
    )


def _safe_float(value: Any) -> float:
    """把检索分数转换成 JSON 友好的浮点数，异常时回退为 0。"""

    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _build_source_items(chunks: list, limit: int = 5) -> list[dict[str, Any]]:
    """把召回片段整理成面向前端、Trace 和消息持久化的来源出处。"""

    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in chunks[:limit]:
        metadata = _chunk_metadata(chunk)
        content = _chunk_content(chunk)
        chunk_index = metadata.get("chunk_index", metadata.get("chunkIndex"))
        source_key = "|".join(
            str(part or "")
            for part in (
                metadata.get("doc_id"),
                metadata.get("chunk_id") or metadata.get("chunkId"),
                chunk_index,
                content[:80],
            )
        )
        if source_key in seen:
            continue
        seen.add(source_key)

        sources.append(
            {
                "index": len(sources) + 1,
                "title": _source_title(metadata),
                "docId": metadata.get("doc_id"),
                "kbId": metadata.get("kb_id"),
                "chunkId": metadata.get("chunk_id") or metadata.get("chunkId"),
                "chunkIndex": chunk_index,
                "channel": getattr(chunk, "channel", metadata.get("channel", "")),
                "score": _safe_float(getattr(chunk, "score", 0.0)),
                "preview": content[:180],
            }
        )
    return sources


def _format_source_line(source: dict[str, Any]) -> str:
    """把单条结构化来源转换成回答末尾可读的出处行。"""

    chunk_index = source.get("chunkIndex")
    chunk_text = f"，片段 {int(chunk_index) + 1}" if isinstance(chunk_index, int) else ""
    channel = f"，通道：{source.get('channel')}" if source.get("channel") else ""
    return f"[{source['index']}] {source.get('title') or '未知来源'}{chunk_text}{channel}"


def _format_sources_block(sources: list[dict[str, Any]]) -> str:
    """生成回答末尾的来源出处区块；无命中时明确说明没有可用来源。"""

    if not sources:
        return "\n\n来源出处：\n未检索到可用知识库来源"
    lines = "\n".join(_format_source_line(source) for source in sources)
    return f"\n\n来源出处：\n{lines}"


def _build_prompt(question: str, chunks: list, memory_block: str = "") -> str:
    """_build_prompt 函数：把内部数据整理成后续步骤需要的格式，避免业务逻辑到处重复拼装。"""
    memory_text = f"长期记忆：\n{memory_block}\n\n" if memory_block else ""
    if not chunks:
        return f"{memory_text}问题：{question}" if memory_text else question
    context = "\n\n".join(
        f"[{index + 1}] 来源：{_source_title(_chunk_metadata(chunk))}\n内容：{_chunk_content(chunk)}"
        for index, chunk in enumerate(chunks[:5])
    )
    return (
        "请严格基于知识库内容回答用户问题；如果知识库不足以支撑结论，请明确说明不知道。"
        "回答中引用知识库内容时使用 [1]、[2] 这样的编号标注依据，不要编造未提供的来源。\n\n"
        f"{memory_text}知识库内容：\n{context}\n\n问题：{question}"
    )


async def _prepare_rag_context(service: ConversationService, conversation_id: str, message: str) -> tuple[str, list, str]:
    """_prepare_rag_context 函数：准备模型调用前需要的上下文、提示词或历史消息。"""
    try:
        from app.rag.workflow import multi_channel_retriever, query_rewriter, reranker
    except Exception as exc:
        raise ChatGenerationError("workflow_import", f"{type(exc).__name__}: {exc}") from exc

    runtime = get_runtime_settings(service.db)
    conversation = service.get_conversation(conversation_id)
    user_id = conversation.user_id if conversation else None
    memory_block = LongTermMemoryService(service.db).build_prompt_block(user_id, message)
    try:
        rewritten = query_rewriter.rewrite(message, _history(service, conversation_id))
    except Exception as exc:
        raise ChatGenerationError("query_rewrite", f"{type(exc).__name__}: {exc}") from exc

    try:
        retrieved_chunks = multi_channel_retriever.retrieve(query=rewritten, top_k=runtime.top_k)
    except Exception as exc:
        raise ChatGenerationError("retrieval", f"{type(exc).__name__}: {exc}") from exc

    final_chunks = retrieved_chunks
    try:
        documents = [getattr(chunk, "content", getattr(chunk, "page_content", str(chunk))) for chunk in retrieved_chunks]
        reranked = reranker.rerank_with_threshold(rewritten, documents, threshold=settings.RERANK_THRESHOLD)
        if reranked:
            final_chunks = [retrieved_chunks[item["index"]] for item in reranked if item["index"] < len(retrieved_chunks)]
    except Exception:
        logger.warning("重排失败，回退使用原始检索结果", exc_info=True)

    return rewritten, final_chunks, _build_prompt(message, final_chunks, memory_block)


async def generate_answer(prompt: str, deep_thinking: bool = False) -> AsyncIterator[str]:
    """generate_answer 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    try:
        from app.rag.workflow import build_primary_llm
        from langchain_core.messages import HumanMessage
    except Exception as exc:
        raise ChatGenerationError("workflow_import", f"{type(exc).__name__}: {exc}") from exc

    final_prompt = prompt if not deep_thinking else f"请更深入推理后回答：{prompt}"
    try:
        llm = build_primary_llm()
        async for chunk in llm.astream([HumanMessage(content=final_prompt)]):
            content = getattr(chunk, "content", "")
            if content:
                yield content
    except Exception as exc:
        raise ChatGenerationError("llm_stream", f"{type(exc).__name__}: {exc}") from exc


async def stream_chat(
    db: Session,
    conversation_id: str,
    message: str,
    task_id: str,
    deep_thinking: bool = False,
) -> AsyncIterator[dict]:
    """stream_chat 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    trace_service = TraceService(db)
    trace = trace_service.start_run(session_id=conversation_id, task_id=task_id)
    service = ConversationService(db)
    user_message = service.add_message(conversation_id, "user", message, {"taskId": task_id, "traceId": trace.id})

    conversation = service.get_conversation(conversation_id)
    user_id = conversation.user_id if conversation else None
    memory_service = LongTermMemoryService(db)
    remembered = memory_service.remember_from_user_message(user_id, conversation_id, user_message.id, message)
    memory_block = memory_service.build_prompt_block(user_id, message)

    # 为 Trace 显式记录输入，避免详情页把一份 metadata 同时展示成输入和输出。
    history = _history(service, conversation_id)
    history_for_agent = ([{"role": "system", "content": f"长期记忆：\n{memory_block}"}] + history) if memory_block else history
    intent_span = trace_service.create_span(
        trace.id,
        "intent_analysis",
        input_data={"question": message},
        metadata={"remembered": len(remembered), "memoryUsed": bool(memory_block)},
    )
    answer = ""

    trace_service.complete_span(intent_span, output_data={"mode": "rag", "agentMode": "react"})
    react_span = trace_service.create_span(trace.id, "react_loop", input_data={"question": message, "history": history_for_agent})
    react_events: list[dict] = []
    try:
        async for event in ConversationReactAgent().run(message, history_for_agent):
            event["taskId"] = task_id
            event["traceId"] = trace.id
            react_events.append(event)

            if event.get("type") == "observation":
                result = event.get("result") or {}
                tool_span = trace_service.create_span(
                    trace.id,
                    "tool_call",
                    input_data={
                        "stepIndex": event.get("stepIndex"),
                        "tool": event.get("tool"),
                        "args": event.get("args") or {},
                    },
                    metadata={"agent": "conversation"},
                )
                trace_service.complete_span(
                    tool_span,
                    status="success" if result.get("success") else "error",
                    error_message=result.get("error", ""),
                    output_data=result,
                )

            if event.get("type") == "final_answer":
                answer = event.get("content") or ""
                yield {"type": "final_answer", "content": answer, "taskId": task_id, "traceId": trace.id}
                yield {"type": "token", "content": answer, "taskId": task_id, "traceId": trace.id}
            elif not str(event.get("type", "")).startswith("_"):
                yield event

        if answer:
            service.add_message(conversation_id, "assistant", answer, {"taskId": task_id, "traceId": trace.id, "agentMode": "react"})
            trace_service.complete_span(react_span, output_data={"events": react_events, "responseLength": len(answer)})
            trace_service.complete_run(trace.id, "success")
            yield {"type": "done", "taskId": task_id, "traceId": trace.id}
            return
        trace_service.complete_span(react_span, status="error", error_message="ReAct 未产出最终回答", output_data={"events": react_events})
    except Exception as exc:
        # ReAct 是增强路径，失败时保留 Trace 后回退到原 RAG 链路。
        trace_service.complete_span(react_span, status="error", error_message=str(exc), output_data={"events": react_events})

    rewrite_span = trace_service.create_span(trace.id, "query_rewrite", input_data={"question": message, "history": history_for_agent})
    retrieval_span = trace_service.create_span(trace.id, "retrieval")
    generation_span = trace_service.create_span(trace.id, "generation")

    try:
        rewritten, chunks, prompt = await _prepare_rag_context(service, conversation_id, message)
        sources = _build_source_items(chunks)
        rewrite_span.input_data["query"] = rewritten
        retrieval_span.input_data = {"query": rewritten}
        generation_span.input_data = {
            "query": message,
            "rewritten": rewritten,
            "promptPreview": prompt[:500],
            "sources": sources,
        }
        trace_service.complete_span(rewrite_span, output_data={"rewritten": rewritten})
        trace_service.complete_span(
            retrieval_span,
            output_data={
                "chunks": len(chunks),
                "sources": sources,
                "channels": [
                    _chunk_metadata(chunk).get("hybridChannels") or getattr(chunk, "channel", "")
                    for chunk in chunks[:5]
                ],
                "chunkPreview": [_chunk_content(chunk)[:160] for chunk in chunks[:3]],
            },
        )
        async for token in generate_answer(prompt, deep_thinking):
            answer += token
            yield {"type": "token", "content": token, "taskId": task_id, "traceId": trace.id}
        sources_block = _format_sources_block(sources)
        if sources_block:
            answer += sources_block
            yield {"type": "token", "content": sources_block, "taskId": task_id, "traceId": trace.id}
        if sources:
            yield {"type": "sources", "sources": sources, "taskId": task_id, "traceId": trace.id}
    except ChatGenerationError as exc:
        diagnostic = f"聊天链路失败：[{exc.stage}] {exc.detail}"
        service.add_message(conversation_id, "assistant", diagnostic, {"taskId": task_id, "traceId": trace.id, "errorStage": exc.stage})
        trace_service.complete_span(generation_span, status="error", error_message=diagnostic, output_data={"stage": exc.stage})
        trace_service.complete_run(trace.id, "error")
        yield {"type": "error", "content": diagnostic, "taskId": task_id, "traceId": trace.id, "stage": exc.stage}
        return

    service.add_message(conversation_id, "assistant", answer, {"taskId": task_id, "traceId": trace.id, "sources": sources})
    trace_service.complete_span(generation_span, output_data={"responseLength": len(answer), "answerPreview": answer[:500], "sources": sources})
    trace_service.complete_run(trace.id, "success")
    yield {"type": "done", "taskId": task_id, "traceId": trace.id}
