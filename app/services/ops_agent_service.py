"""运维 Agent 服务，负责运行落库、Trace 记录、工具审批和详情查询。"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.agents.orchestrator import AGENT_REGISTRY, OrchestratorAgent
from app.agents.tool_registry import UnifiedToolRegistry
from app.agents.tools import OpsToolkit
from app.core.time_utils import to_shanghai_iso, utc_now_naive
from app.domain.models import AgentApproval, AgentRun, AgentStep as AgentStepModel, AgentToolCall, User
from app.services.chat_service import ConversationService
from app.services.trace_service import TraceService


class OpsAgentService:
    """多 Agent 运维入口服务。

    服务层负责把编排器的内存事件落库：
    - AgentRun 记录一次完整运维诊断。
    - AgentToolCall 记录工具调用与执行结果。
    - AgentApproval 记录危险动作审批。
    """

    def __init__(self, db: Session):
        self.db = db
        self.toolkit = OpsToolkit()

    def list_tools(self) -> list[dict[str, Any]]:
        """返回可用工具目录，供后台工具面板展示。"""

        return UnifiedToolRegistry(include_ops=True, toolkit=self.toolkit).list_tools(audience="admin")

    def list_agents(self) -> dict[str, Any]:
        """返回可用子 Agent 说明。"""

        return AGENT_REGISTRY

    async def stream_chat(self, message: str, user: User, conversation_id: str | None = None, auto_execute_readonly: bool = True) -> AsyncIterator[dict]:
        """创建一次运维 Agent 运行，并将编排器事件转为 SSE 事件。"""

        conversation_service = ConversationService(self.db)
        conversation = conversation_service.get_conversation(conversation_id) if conversation_id else None
        if not conversation:
            conversation = conversation_service.create_conversation(user.id, message[:30] or "新对话")
        conversation_id = conversation.id

        trace_service = TraceService(self.db)
        trace = trace_service.start_run(session_id=conversation_id, user_id=user.id)
        run = AgentRun(
            conversation_id=conversation_id,
            trace_id=trace.id,
            user_id=user.id,
            message=message,
            status="running",
            agent_type="orchestrator",
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        # 运维链路也写入统一会话消息，刷新前端后仍能从 /conversations 恢复本轮对话。
        conversation_service.add_message(conversation_id, "user", message, {"runId": run.id, "traceId": trace.id, "agentMode": "ops"})
        yield {"type": "run_created", "runId": run.id, "traceId": trace.id, "conversationId": conversation_id, "channel": "ops"}

        orchestrator = OrchestratorAgent(self.toolkit)
        try:
            async for event in orchestrator.run(message, {"runId": run.id, "userId": user.id}):
                event["runId"] = run.id
                event["traceId"] = trace.id
                event["conversationId"] = conversation_id
                event["channel"] = "ops"
                self._persist_event(run, event, user)
                self._persist_trace_event(trace_service, trace.id, event)
                yield event
            run.status = "completed"
            run.final_report = self._last_report(run.id)
            if run.final_report:
                conversation_service.add_message(
                    conversation_id,
                    "assistant",
                    run.final_report,
                    {"runId": run.id, "traceId": trace.id, "agentMode": "ops"},
                )
            self.db.commit()
            trace_service.complete_run(trace.id, "success")
        except Exception as exc:
            run.status = "failed"
            run.final_report = str(exc)
            conversation_service.add_message(
                conversation_id,
                "assistant",
                str(exc),
                {"runId": run.id, "traceId": trace.id, "agentMode": "ops", "error": True},
            )
            self.db.commit()
            trace_service.complete_run(trace.id, "error")
            yield {"type": "error", "runId": run.id, "traceId": trace.id, "conversationId": conversation_id, "channel": "ops", "content": str(exc)}

    def _persist_event(self, run: AgentRun, event: dict[str, Any], user: User) -> None:
        """将关键事件持久化，便于后台详情页回放执行过程。"""

        if event.get("type") == "plan_created":
            steps = event.get("steps") or []
            run.plan = steps
            for index, item in enumerate(steps):
                self.db.add(
                    AgentStepModel(
                        run_id=run.id,
                        step_index=index,
                        title=item.get("title") or "",
                        tool_name=item.get("tool_name") or item.get("toolName") or "",
                        args=item.get("args") or {},
                        status=item.get("status") or "pending",
                        assigned_agent=item.get("assigned_agent") or item.get("assignedAgent") or "executor",
                        agent_reasoning=item.get("reasoning") or "",
                    )
                )
            self.db.commit()

        if event.get("type") == "step_started":
            step = self._step_by_index(run.id, int(event.get("stepIndex", 0)))
            if step:
                step.status = "running"
                self.db.commit()

        if event.get("type") == "tool_call":
            self.db.add(
                AgentToolCall(
                    run_id=run.id,
                    step_id=self._step_id_by_index(run.id, int(event.get("stepIndex", -1))),
                    tool_name=event.get("tool") or "",
                    args=event.get("args") or {},
                    status="running",
                    approval_status="not_required",
                )
            )
            self.db.commit()

        if event.get("type") == "observation":
            result = event.get("result") or {}
            # 当前事件流串行执行，最近一条 running tool_call 就是该 observation 对应工具。
            tool = self.db.query(AgentToolCall).filter(AgentToolCall.run_id == run.id).order_by(AgentToolCall.created_at.desc()).first()
            if tool:
                tool.status = "success" if result.get("success") else "failed"
                tool.result = result
                tool.error_message = result.get("error", "")
                tool.duration_ms = int(event.get("durationMs") or 0)
            step = self._step_by_index(run.id, int(event.get("stepIndex", -1)))
            if step:
                step.status = "success" if result.get("success") else "failed"
                step.observation = result.get("summary", "")
            self.db.commit()

        if event.get("type") == "approval_required":
            # 审批事件需要同时创建 tool_call 和 approval，后续 approve 接口会继续执行该工具。
            tool_call = AgentToolCall(
                run_id=run.id,
                tool_name=event.get("tool") or "",
                args=event.get("args") or {},
                status="blocked",
                risk_level=event.get("riskLevel") or "write",
                approval_status="pending",
            )
            self.db.add(tool_call)
            self.db.flush()
            approval = AgentApproval(
                run_id=run.id,
                tool_call_id=tool_call.id,
                tool_name=tool_call.tool_name,
                args=tool_call.args,
                status="pending",
                requested_by=user.id,
            )
            self.db.add(approval)
            step = self._step_by_index(run.id, int(event.get("stepIndex", -1)))
            if step:
                step.status = "blocked"
            self.db.commit()
            event["approvalId"] = approval.id

        if event.get("type") in {"report", "final_answer"}:
            run.final_report = event.get("content") or run.final_report
            self.db.commit()

    def _persist_trace_event(self, trace_service: TraceService, trace_id: str, event: dict[str, Any]) -> None:
        """把核心 Agent 事件写入 Trace，便于详情页回放。"""

        event_type = event.get("type")
        operation_map = {
            "plan_created": "planner",
            "observation": "tool_call",
            "replan_decision": "replanner",
            "approval_required": "approval_required",
            "final_answer": "final_answer",
        }
        operation = operation_map.get(event_type)
        if not operation:
            return
        input_data = {
            "eventType": event_type,
            "stepIndex": event.get("stepIndex"),
            "tool": event.get("tool"),
            "args": event.get("args") or {},
        }
        span = trace_service.create_span(trace_id, operation, input_data=input_data, metadata={"agent": event.get("agent")})
        status = "error" if event_type == "observation" and not (event.get("result") or {}).get("success", False) else "success"
        trace_service.complete_span(span, status=status, output_data=event, duration_ms=event.get("durationMs"))

    def _step_by_index(self, run_id: str, index: int) -> AgentStepModel | None:
        """根据步骤序号查找持久化步骤。"""

        if index < 0:
            return None
        return (
            self.db.query(AgentStepModel)
            .filter(AgentStepModel.run_id == run_id, AgentStepModel.step_index == index)
            .first()
        )

    def _step_id_by_index(self, run_id: str, index: int) -> str | None:
        """根据步骤序号返回步骤 ID，工具调用可选关联。"""

        step = self._step_by_index(run_id, index)
        return step.id if step else None

    def _last_report(self, run_id: str) -> str:
        """获取最终报告占位；当前最终报告主要通过 SSE report 事件返回。"""

        run = self.db.query(AgentRun).filter(AgentRun.id == run_id).first()
        return run.final_report if run else ""

    async def approve(self, run_id: str, approval_id: str, approved: bool, comment: str | None, user: User) -> dict[str, Any]:
        """处理危险动作审批，并在批准后执行对应工具。"""

        approval = self.db.query(AgentApproval).filter(AgentApproval.id == approval_id, AgentApproval.run_id == run_id).first()
        if not approval:
            raise HTTPException(status_code=404, detail="审批记录不存在")

        approval.status = "approved" if approved else "rejected"
        approval.approved_by = user.id
        approval.comment = comment or ""
        approval.decided_at = utc_now_naive()

        if not approved:
            self.db.commit()
            return {"status": "rejected"}

        started = time.perf_counter()
        result = self.toolkit.tools[approval.tool_name](**approval.args)
        if hasattr(result, "__await__"):
            result = await result
        tool_call = self.db.query(AgentToolCall).filter(AgentToolCall.id == approval.tool_call_id).first()
        if tool_call:
            tool_call.status = "success" if result.get("success") else "failed"
            tool_call.result = result
            tool_call.duration_ms = int((time.perf_counter() - started) * 1000)
            tool_call.approval_status = "approved"
        self.db.commit()
        return {"status": "approved", "result": result}

    def stop(self, run_id: str, user: User) -> dict[str, Any]:
        """将指定运维运行标记为停止。"""

        run = self.db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="运行记录不存在")
        run.status = "stopped"
        self.db.commit()
        return {"id": run.id, "status": run.status}

    def get_run(self, run_id: str) -> dict[str, Any]:
        """查询运维运行详情。"""

        run = self.db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="运行记录不存在")
        return {
            "id": run.id,
            "message": run.message,
            "status": run.status,
            "finalReport": run.final_report,
            "createdAt": to_shanghai_iso(run.created_at),
            "updatedAt": to_shanghai_iso(run.updated_at),
            "toolCalls": [
                {
                    "id": item.id,
                    "toolName": item.tool_name,
                    "args": item.args,
                    "status": item.status,
                    "result": item.result,
                    "createdAt": to_shanghai_iso(item.created_at),
                }
                for item in run.tool_calls
            ],
            "approvals": [
                {
                    "id": item.id,
                    "toolName": item.tool_name,
                    "args": item.args,
                    "status": item.status,
                    "createdAt": to_shanghai_iso(item.created_at),
                    "decidedAt": to_shanghai_iso(item.decided_at),
                }
                for item in run.approvals
            ],
        }
