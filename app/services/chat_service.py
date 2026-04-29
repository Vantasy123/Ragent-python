"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

import logging
from typing import AsyncIterator

from sqlalchemy.orm import Session

from app.core.time_utils import utc_now_naive
from app.agents.react_agent import ConversationReactAgent
from app.domain.models import Conversation, ConversationMessage, MessageFeedback
from app.services.context_window import context_window
from app.services.runtime_state import STOP_TASKS
from app.services.settings_service import get_runtime_settings
from app.services.trace_service import TraceService

logger = logging.getLogger(__name__)


class ChatGenerationError(RuntimeError):
    """聊天链路异常，保留失败阶段以便前端和 Trace 展示。"""

    def __init__(self, stage: str, detail: str):
        super().__init__(detail)
        self.stage = stage
        self.detail = detail


class ConversationService:
    """会话与消息的数据库服务。"""

    def __init__(self, db: Session):
        self.db = db

    def create_conversation(self, user_id: str | None, title: str | None = None) -> Conversation:
        row = Conversation(user_id=user_id, title=(title or "新对话")[:255])
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        return self.db.query(Conversation).filter(Conversation.id == conversation_id).first()

    def list_conversations(self, user_id: str | None, page_no: int, page_size: int):
        query = self.db.query(Conversation)
        if user_id:
            query = query.filter(Conversation.user_id == user_id)
        # 会话主体可以保留在数据库中，但列表只展示仍有对话记录的会话。
        query = query.filter(Conversation.message_count > 0)
        total = query.count()
        rows = query.order_by(Conversation.updated_at.desc()).offset((page_no - 1) * page_size).limit(page_size).all()
        return rows, total

    def rename_conversation(self, conversation_id: str, title: str) -> Conversation | None:
        row = self.get_conversation(conversation_id)
        if not row:
            return None
        row.title = title[:255]
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_conversation(self, conversation_id: str) -> bool:
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
        return (
            self.db.query(ConversationMessage)
            .filter(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at.asc())
            .all()
        )

    def add_message(self, conversation_id: str, role: str, content: str, metadata: dict | None = None) -> ConversationMessage:
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
        row = MessageFeedback(message_id=message_id, feedback_type=feedback_type, comment=comment)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row


def _history(service: ConversationService, conversation_id: str) -> list[dict[str, str]]:
    runtime = get_runtime_settings(service.db)
    keep = max(runtime.history_keep_turns * 2, 2)
    cached = context_window.get_window(conversation_id, keep)
    if cached:
        return cached[-keep:]
    rows = service.list_messages(conversation_id)
    context_window.rebuild_window(conversation_id, rows, keep)
    return [{"role": row.role, "content": row.content} for row in rows[-keep:]]


def _build_prompt(question: str, chunks: list) -> str:
    if not chunks:
        return question
    context = "\n\n".join(f"[{index + 1}] {getattr(chunk, 'content', getattr(chunk, 'page_content', str(chunk)))}" for index, chunk in enumerate(chunks[:5]))
    return (
        "请严格基于知识库内容回答用户问题；如果知识库不足以支撑结论，请明确说明不知道。\n\n"
        f"知识库内容：\n{context}\n\n问题：{question}"
    )


async def _prepare_rag_context(service: ConversationService, conversation_id: str, message: str) -> tuple[str, list, str]:
    try:
        from app.rag.workflow import multi_channel_retriever, query_rewriter, reranker
    except Exception as exc:
        raise ChatGenerationError("workflow_import", f"{type(exc).__name__}: {exc}") from exc

    runtime = get_runtime_settings(service.db)
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
        reranked = reranker.rerank_with_threshold(rewritten, documents)
        if reranked:
            final_chunks = [retrieved_chunks[item["index"]] for item in reranked if item["index"] < len(retrieved_chunks)]
    except Exception:
        logger.warning("重排失败，回退使用原始检索结果", exc_info=True)

    return rewritten, final_chunks, _build_prompt(message, final_chunks)


async def generate_answer(prompt: str, deep_thinking: bool = False) -> AsyncIterator[str]:
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
    trace_service = TraceService(db)
    trace = trace_service.start_run(session_id=conversation_id, task_id=task_id)
    service = ConversationService(db)
    service.add_message(conversation_id, "user", message, {"taskId": task_id, "traceId": trace.id})

    # 为 Trace 显式记录输入，避免详情页把一份 metadata 同时展示成输入和输出。
    history = _history(service, conversation_id)
    intent_span = trace_service.create_span(trace.id, "intent_analysis", input_data={"question": message})
    answer = ""

    trace_service.complete_span(intent_span, output_data={"mode": "rag", "agentMode": "react"})
    react_span = trace_service.create_span(trace.id, "react_loop", input_data={"question": message, "history": history})
    react_events: list[dict] = []
    try:
        async for event in ConversationReactAgent().run(message, history):
            if task_id in STOP_TASKS:
                STOP_TASKS.discard(task_id)
                trace_service.complete_span(react_span, status="error", error_message="任务已中止", output_data={"events": react_events})
                trace_service.complete_run(trace.id, "error")
                yield {"type": "stopped", "taskId": task_id, "traceId": trace.id}
                return

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

    rewrite_span = trace_service.create_span(trace.id, "query_rewrite", input_data={"question": message, "history": history})
    retrieval_span = trace_service.create_span(trace.id, "retrieval")
    generation_span = trace_service.create_span(trace.id, "generation")

    try:
        rewritten, chunks, prompt = await _prepare_rag_context(service, conversation_id, message)
        rewrite_span.input_data["query"] = rewritten
        retrieval_span.input_data = {"query": rewritten}
        generation_span.input_data = {
            "query": message,
            "rewritten": rewritten,
            "promptPreview": prompt[:500],
        }
        trace_service.complete_span(rewrite_span, output_data={"rewritten": rewritten})
        trace_service.complete_span(
            retrieval_span,
            output_data={
                "chunks": len(chunks),
                "sources": [getattr(chunk, "metadata", {}).get("doc_id") for chunk in chunks[:5]],
                "chunkPreview": [getattr(chunk, "content", getattr(chunk, "page_content", str(chunk)))[:160] for chunk in chunks[:3]],
            },
        )
        async for token in generate_answer(prompt, deep_thinking):
            if task_id in STOP_TASKS:
                STOP_TASKS.discard(task_id)
                trace_service.complete_span(generation_span, status="error", error_message="任务已中止")
                trace_service.complete_run(trace.id, "error")
                yield {"type": "stopped", "taskId": task_id, "traceId": trace.id}
                return
            answer += token
            yield {"type": "token", "content": token, "taskId": task_id, "traceId": trace.id}
    except ChatGenerationError as exc:
        diagnostic = f"聊天链路失败：[{exc.stage}] {exc.detail}"
        service.add_message(conversation_id, "assistant", diagnostic, {"taskId": task_id, "traceId": trace.id, "errorStage": exc.stage})
        trace_service.complete_span(generation_span, status="error", error_message=diagnostic, output_data={"stage": exc.stage})
        trace_service.complete_run(trace.id, "error")
        yield {"type": "error", "content": diagnostic, "taskId": task_id, "traceId": trace.id, "stage": exc.stage}
        return

    service.add_message(conversation_id, "assistant", answer, {"taskId": task_id, "traceId": trace.id})
    trace_service.complete_span(generation_span, output_data={"responseLength": len(answer), "answerPreview": answer[:500]})
    trace_service.complete_run(trace.id, "success")
    yield {"type": "done", "taskId": task_id, "traceId": trace.id}
