"""运维 Agent 的 LangGraph 状态图实现。"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.base import AgentStep, StepStatus
from app.agents.memory import SharedMemory
from app.agents.tool_registry import ToolCallRequest, ToolCallResult, UnifiedToolRegistry


class OpsGraphState(TypedDict, total=False):
    """运维图运行状态；只保存执行所需的短期状态，长期审计仍写入 MySQL。"""

    message: str
    runId: str
    userId: str
    plan: list[AgentStep]
    remaining: list[AgentStep]
    completed: list[AgentStep]
    observations: list[dict[str, Any]]
    currentStepIndex: int
    activeStep: AgentStep | None
    lastResult: ToolCallResult | None
    decision: Any
    finalReport: str
    pendingApproval: bool
    memory: SharedMemory
    events: list[dict[str, Any]]
    maxSteps: int


class OpsLangGraphRunner:
    """把现有 Plan-Execute-Replan 运维流程封装为 LangGraph 状态图。"""

    def __init__(
        self,
        *,
        registry: UnifiedToolRegistry,
        planner: Any,
        executor: Any,
        replanner: Any,
        orchestrator: Any,
        memory: SharedMemory | None = None,
        max_steps: int = 10,
    ) -> None:
        self.registry = registry
        self.planner = planner
        self.executor = executor
        self.replanner = replanner
        self.orchestrator = orchestrator
        self.memory = memory or SharedMemory()
        self.max_steps = max(1, max_steps)
        self.graph = self._build_graph()

    async def run(self, task: str, context: dict[str, Any] | None = None) -> AsyncIterator[dict[str, Any]]:
        """执行图并按原 SSE 协议逐条输出事件。"""

        initial_state: OpsGraphState = {
            "message": task,
            "runId": str((context or {}).get("runId") or ""),
            "userId": str((context or {}).get("userId") or ""),
            "plan": [],
            "remaining": [],
            "completed": [],
            "observations": [],
            "currentStepIndex": 0,
            "activeStep": None,
            "lastResult": None,
            "decision": None,
            "finalReport": "",
            "pendingApproval": False,
            "memory": self.memory,
            "events": [],
            "maxSteps": self.max_steps,
        }

        # 兼容旧事件，前端和落库逻辑仍可按原事件流处理。
        yield {"type": "orchestrator_start", "agent": self.orchestrator.name, "message": task}
        async for update in self.graph.astream(initial_state, stream_mode="updates"):
            if not isinstance(update, dict):
                continue
            for node_update in update.values():
                if not isinstance(node_update, dict):
                    continue
                for event in node_update.get("events") or []:
                    yield event

    def _build_graph(self):
        """构建运维状态图，显式表达规划、执行、重规划和收尾路由。"""

        graph = StateGraph(OpsGraphState)
        graph.add_node("planner", self._planner_node)
        graph.add_node("executor", self._executor_node)
        graph.add_node("approval", self._approval_node)
        graph.add_node("replanner", self._replanner_node)
        graph.add_node("final", self._final_node)

        graph.add_edge(START, "planner")
        graph.add_conditional_edges("planner", self._route_after_planner, {"execute": "executor", "final": "final"})
        graph.add_conditional_edges("executor", self._route_after_executor, {"approval": "approval", "replan": "replanner"})
        graph.add_edge("approval", "replanner")
        graph.add_conditional_edges("replanner", self._route_after_replanner, {"execute": "executor", "final": "final"})
        graph.add_edge("final", END)
        return graph.compile()

    async def _planner_node(self, state: OpsGraphState) -> dict[str, Any]:
        """Planner 节点：先查询知识库，再生成执行计划。"""

        task = state["message"]
        events: list[dict[str, Any]] = []

        knowledge_args = {"query": task, "topK": 5}
        knowledge_started = time.perf_counter()
        events.append({"type": "tool_call", "agent": "planner", "stepIndex": -1, "tool": "knowledge_search", "args": knowledge_args})
        knowledge_result = await self.registry.call(ToolCallRequest("knowledge_search", knowledge_args))
        events.append(
            {
                "type": "observation",
                "agent": "planner",
                "stepIndex": -1,
                "tool": "knowledge_search",
                "args": knowledge_args,
                "durationMs": self._elapsed_ms(knowledge_started),
                "result": knowledge_result.to_dict(),
            }
        )

        planner_started = time.perf_counter()
        steps = await self.planner.create_plan(task, knowledge_result)
        plan_payload = [self._step_to_dict(step) for step in steps]
        events.append(
            {
                "type": "plan_created",
                "agent": "planner",
                "durationMs": self._elapsed_ms(planner_started),
                "steps": plan_payload,
            }
        )
        events.append({"type": "agent_plan", "agent": self.orchestrator.name, "steps": plan_payload})

        return {
            "plan": steps,
            "remaining": list(steps),
            "completed": [],
            "observations": [],
            "currentStepIndex": 0,
            "pendingApproval": False,
            "events": events,
        }

    async def _executor_node(self, state: OpsGraphState) -> dict[str, Any]:
        """Executor 节点：每次只执行一个计划步骤。"""

        remaining = list(state.get("remaining") or [])
        completed = list(state.get("completed") or [])
        observations = list(state.get("observations") or [])
        events: list[dict[str, Any]] = []

        if not remaining or len(completed) >= int(state.get("maxSteps") or self.max_steps):
            return {"events": events, "pendingApproval": False}

        step = remaining.pop(0)
        index = len(completed)
        step.assigned_agent = step.assigned_agent or "executor"
        events.append({"type": "step_started", "agent": "executor", "stepIndex": index, "step": self._step_to_dict(step)})

        spec = self.registry.tools.get(step.tool_name).spec if step.tool_name in self.registry.tools else None
        if spec and spec.requires_approval:
            # 高风险工具只进入审批节点，不在图中直接执行。
            return {
                "remaining": remaining,
                "completed": completed,
                "observations": observations,
                "currentStepIndex": index,
                "activeStep": step,
                "lastResult": None,
                "pendingApproval": True,
                "events": events,
            }

        step.status = StepStatus.RUNNING
        events.append({"type": "tool_call", "agent": "executor", "stepIndex": index, "tool": step.tool_name, "args": step.args})
        tool_started = time.perf_counter()
        result = await self.executor.execute(step)
        duration_ms = self._elapsed_ms(tool_started)
        step.status = StepStatus.SUCCESS if result.success else StepStatus.FAILED
        step.observation = result.summary
        completed.append(step)
        observations.append({"stepIndex": index, "tool": step.tool_name, "result": result.to_dict()})

        memory = state.get("memory") or self.memory
        memory.add("executor", "observation", result.summary, result.to_dict())
        result_payload = result.to_dict()
        events.append(
            {
                "type": "observation",
                "agent": "executor",
                "stepIndex": index,
                "tool": step.tool_name,
                "args": step.args,
                "durationMs": duration_ms,
                "result": result_payload,
            }
        )
        events.append({"type": "step_observed", "agent": "executor", "stepIndex": index, "durationMs": duration_ms, "result": result_payload})

        return {
            "remaining": remaining,
            "completed": completed,
            "observations": observations,
            "currentStepIndex": index,
            "activeStep": step,
            "lastResult": result,
            "pendingApproval": False,
            "events": events,
            "memory": memory,
        }

    async def _approval_node(self, state: OpsGraphState) -> dict[str, Any]:
        """Approval 节点：写操作只产出审批事件并阻塞自动执行。"""

        step = state.get("activeStep")
        completed = list(state.get("completed") or [])
        observations = list(state.get("observations") or [])
        index = int(state.get("currentStepIndex") or len(completed))
        if not step:
            result = ToolCallResult(success=False, summary="审批步骤缺失", error="approval_step_missing")
            return {"lastResult": result, "pendingApproval": True, "events": []}

        spec = self.registry.tools.get(step.tool_name).spec if step.tool_name in self.registry.tools else None
        started = time.perf_counter()
        step.status = StepStatus.BLOCKED
        result = ToolCallResult(
            success=False,
            summary=f"工具需要审批：{step.tool_name}",
            error="approval_required",
            risk_level=spec.risk_level if spec else "write",
            requires_approval=True,
            source=spec.source if spec else "builtin",
            category=spec.category if spec else "ops",
        )
        completed.append(step)
        observations.append({"stepIndex": index, "tool": step.tool_name, "result": result.to_dict()})
        return {
            "completed": completed,
            "observations": observations,
            "lastResult": result,
            "pendingApproval": True,
            "events": [
                {
                    "type": "approval_required",
                    "agent": "executor",
                    "stepIndex": index,
                    "tool": step.tool_name,
                    "args": step.args,
                    "riskLevel": result.risk_level,
                    "durationMs": self._elapsed_ms(started),
                }
            ],
        }

    async def _replanner_node(self, state: OpsGraphState) -> dict[str, Any]:
        """Replanner 节点：根据观察结果决定继续、完成、阻塞或修订计划。"""

        task = state["message"]
        completed = list(state.get("completed") or [])
        remaining = list(state.get("remaining") or [])
        result = state.get("lastResult")
        events: list[dict[str, Any]] = []
        replan_started = time.perf_counter()

        if not isinstance(result, ToolCallResult):
            from app.agents.orchestrator import ReplanDecision

            decision = ReplanDecision("complete", "没有可用的执行结果，结束本次运维流程。")
            should_call_replanner = False
        else:
            should_call_replanner = self.orchestrator._should_call_replanner(result, remaining)
            if should_call_replanner:
                decision = await self.replanner.decide(task, completed, remaining, result)
            else:
                from app.agents.orchestrator import ReplanDecision

                decision = ReplanDecision("continue", "规则继续执行：只读工具成功，按既定计划执行剩余步骤。")

        if getattr(decision, "action", "") == "revise" and getattr(decision, "new_steps", None):
            revised_remaining = [step.to_agent_step() for step in decision.new_steps]
            remaining = self._preserve_approval_steps(revised_remaining, remaining)

        # 若原计划中仍有写操作审批步骤，不能因为前置只读工具失败而静默跳过审批边界。
        if getattr(decision, "action", "") in {"complete", "blocked"} and self._has_approval_step(remaining):
            from app.agents.orchestrator import ReplanDecision

            decision = ReplanDecision("continue", "仍有高风险操作需要进入审批流程，继续推进到审批节点。")

        events.append(
            {
                "type": "replan_decision",
                "agent": "replanner",
                "action": decision.action,
                "reason": decision.reason,
                "durationMs": self._elapsed_ms(replan_started),
                "llmSkipped": not should_call_replanner,
                "remaining": [self._step_to_dict(item) for item in remaining],
            }
        )
        return {"decision": decision, "remaining": remaining, "events": events}

    async def _final_node(self, state: OpsGraphState) -> dict[str, Any]:
        """Final 节点：生成最终报告并输出收尾事件。"""

        from app.agents.orchestrator import ReplanDecision

        task = state["message"]
        completed = list(state.get("completed") or [])
        decision = state.get("decision") or ReplanDecision("complete", "计划执行结束。")
        final_started = time.perf_counter()
        final_report = self.orchestrator._build_report(task, completed, decision)
        duration_ms = self._elapsed_ms(final_started)
        memory = state.get("memory") or self.memory
        return {
            "finalReport": final_report,
            "events": [
                {"type": "report", "agent": self.orchestrator.name, "content": final_report, "memory": memory.to_dict()},
                {"type": "final_answer", "agent": self.orchestrator.name, "durationMs": duration_ms, "content": final_report},
                {"type": "done", "agent": self.orchestrator.name, "status": "completed", "content": final_report},
            ],
        }

    def _route_after_planner(self, state: OpsGraphState) -> str:
        """Planner 后根据是否有计划决定执行或直接收尾。"""

        return "execute" if state.get("remaining") else "final"

    def _route_after_executor(self, state: OpsGraphState) -> str:
        """Executor 后把审批和普通执行分流。"""

        return "approval" if state.get("pendingApproval") else "replan"

    def _route_after_replanner(self, state: OpsGraphState) -> str:
        """Replanner 后根据决策决定继续执行或收尾。"""

        decision = state.get("decision")
        action = getattr(decision, "action", "")
        completed_count = len(state.get("completed") or [])
        if action in {"complete", "blocked"}:
            return "final"
        if completed_count >= int(state.get("maxSteps") or self.max_steps):
            return "final"
        return "execute" if state.get("remaining") else "final"

    def _has_approval_step(self, steps: list[AgentStep]) -> bool:
        """判断剩余计划中是否还有需要审批的写操作。"""

        for step in steps:
            tool = self.registry.tools.get(step.tool_name)
            if tool and tool.spec.requires_approval:
                return True
        return False

    def _preserve_approval_steps(self, revised: list[AgentStep], original_remaining: list[AgentStep]) -> list[AgentStep]:
        """重规划时保留原计划中的审批步骤，避免 LLM 删除安全边界事件。"""

        existing = {(step.tool_name, repr(sorted(step.args.items()))) for step in revised}
        merged = list(revised)
        for step in original_remaining:
            tool = self.registry.tools.get(step.tool_name)
            key = (step.tool_name, repr(sorted(step.args.items())))
            if tool and tool.spec.requires_approval and key not in existing:
                merged.append(step)
                existing.add(key)
        return merged

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        """把真实耗时转换为毫秒。"""

        return max(1, int((time.perf_counter() - started) * 1000))

    @staticmethod
    def _step_to_dict(step: AgentStep) -> dict[str, Any]:
        """将计划步骤转换为可序列化字典。"""

        data = step.__dict__.copy()
        data["status"] = step.status.value if isinstance(step.status, StepStatus) else str(step.status)
        return data
