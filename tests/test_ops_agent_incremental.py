from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents.base import AgentStep, ToolSpec
from app.agents.ops_graph import OpsLangGraphRunner
from app.agents.orchestrator import StepExecutorAgent
from app.agents.tool_registry import ToolCallRequest, ToolCallResult, UnifiedTool, UnifiedToolRegistry
from app.core.database import Base
from app.domain.models import AgentApproval, AgentRun, AgentToolCall, EvaluationRun, TraceRun, TraceSpan, User
from app.services.evaluation_service import EvaluationService
from app.services.ops_agent_service import OpsAgentService


class ToolRegistryTest(unittest.IsolatedAsyncioTestCase):
    """验证统一工具注册表的权限边界和输出预算。"""

    async def test_unknown_tool_returns_structured_failure(self) -> None:
        registry = UnifiedToolRegistry(include_ops=False)

        result = await registry.call(ToolCallRequest("missing_tool"))

        self.assertFalse(result.success)
        self.assertEqual(result.error, "unknown_tool")

    async def test_write_tool_requires_approval_unless_explicitly_skipped(self) -> None:
        registry = UnifiedToolRegistry(include_ops=False)
        called = {"value": False}

        def handler() -> dict:
            called["value"] = True
            return {"success": True, "summary": "已执行"}

        registry.tools["danger_write"] = UnifiedTool(
            ToolSpec("danger_write", "危险写操作", risk_level="write", requires_approval=True),
            handler,
        )

        blocked = await registry.call(ToolCallRequest("danger_write"))
        executed = await registry.call(ToolCallRequest("danger_write"), skip_approval=True)

        self.assertEqual(blocked.error, "approval_required")
        self.assertTrue(executed.success)
        self.assertTrue(called["value"])

    async def test_handler_exception_is_normalized(self) -> None:
        registry = UnifiedToolRegistry(include_ops=False)

        def handler() -> dict:
            raise RuntimeError("boom")

        registry.tools["broken"] = UnifiedTool(ToolSpec("broken", "异常工具"), handler)

        result = await registry.call(ToolCallRequest("broken"))

        self.assertFalse(result.success)
        self.assertEqual(result.error, "RuntimeError")
        self.assertIn("boom", result.summary)

    async def test_large_tool_output_is_compacted_in_public_dict(self) -> None:
        registry = UnifiedToolRegistry(include_ops=False)
        registry.tools["logs"] = UnifiedTool(
            ToolSpec("logs", "读取日志"),
            lambda: {"success": True, "summary": "ok", "data": {"stdout": "x" * 3000}},
        )

        result = await registry.call(ToolCallRequest("logs"))
        payload = result.to_dict()

        self.assertTrue(payload["success"])
        self.assertTrue(payload["data"]["stdout"]["truncated"])
        self.assertEqual(payload["data"]["stdout"]["originalLength"], 3000)

    def test_public_tool_metadata_contains_readonly_aliases(self) -> None:
        registry = UnifiedToolRegistry(include_ops=False)
        registry.tools["read"] = UnifiedTool(ToolSpec("read", "只读工具"), lambda: {"success": True})

        item = next(tool for tool in registry.list_tools("admin") if tool["name"] == "read")

        self.assertTrue(item["isReadOnly"])
        self.assertFalse(item["requiresApproval"])


class FakeRegistry:
    """最小工具注册表，用于验证 LangGraph 编排行为。"""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.tools = {
            "knowledge_search": UnifiedTool(ToolSpec("knowledge_search", "知识检索"), lambda: {"success": True}),
            "read_tool": UnifiedTool(ToolSpec("read_tool", "只读检查"), lambda: {"success": True}),
            "write_tool": UnifiedTool(
                ToolSpec("write_tool", "写操作", risk_level="write", requires_approval=True),
                lambda: {"success": True},
            ),
        }

    async def call(self, request: ToolCallRequest, *, skip_approval: bool = False) -> ToolCallResult:
        self.calls.append(request.name)
        tool = self.tools.get(request.name)
        if tool and tool.spec.requires_approval and not skip_approval:
            return ToolCallResult(False, "需要审批", error="approval_required", risk_level="write", requires_approval=True)
        return ToolCallResult(True, f"{request.name} 已执行", data={"tool": request.name})


class FakePlanner:
    def __init__(self, steps: list[AgentStep]) -> None:
        self.steps = steps

    async def create_plan(self, task: str, knowledge: ToolCallResult | None = None) -> list[AgentStep]:
        return self.steps


class FakeReplanner:
    async def decide(self, task: str, completed: list[AgentStep], remaining: list[AgentStep], last_result: ToolCallResult):
        from app.agents.orchestrator import ReplanDecision

        return ReplanDecision("continue" if remaining else "complete", "测试重规划")


class FakeOrchestrator:
    name = "orchestrator"

    def _should_call_replanner(self, result: ToolCallResult, remaining: list[AgentStep]) -> bool:
        return not remaining

    def _build_report(self, task: str, steps: list[AgentStep], decision) -> str:
        return "测试报告"


class OpsGraphRunnerTest(unittest.IsolatedAsyncioTestCase):
    """验证运维图中的自动执行和审批路由。"""

    async def _run(self, registry: FakeRegistry, steps: list[AgentStep], auto_execute_readonly: bool) -> list[dict]:
        runner = OpsLangGraphRunner(
            registry=registry,
            planner=FakePlanner(steps),
            executor=StepExecutorAgent(registry),
            replanner=FakeReplanner(),
            orchestrator=FakeOrchestrator(),
        )
        return [event async for event in runner.run("测试任务", {"autoExecuteReadOnly": auto_execute_readonly})]

    async def test_auto_execute_readonly_true_runs_read_tool(self) -> None:
        registry = FakeRegistry()

        events = await self._run(registry, [AgentStep("读取状态", "read_tool")], True)

        self.assertIn("knowledge_search", registry.calls)
        self.assertIn("read_tool", registry.calls)
        self.assertTrue(any(event["type"] == "observation" and event.get("tool") == "read_tool" for event in events))
        self.assertFalse(any(event["type"] == "agent_plan" for event in events))

    async def test_auto_execute_readonly_false_only_emits_pending_tool_call(self) -> None:
        registry = FakeRegistry()

        events = await self._run(registry, [AgentStep("读取状态", "read_tool")], False)

        self.assertEqual(registry.calls, [])
        pending = [event for event in events if event["type"] == "tool_call" and event.get("tool") == "read_tool"]
        self.assertEqual(pending[0]["status"], "pending")
        self.assertFalse(any(event["type"] == "observation" and event.get("tool") == "read_tool" for event in events))

    async def test_write_tool_always_requires_approval(self) -> None:
        registry = FakeRegistry()

        events = await self._run(registry, [AgentStep("重启服务", "write_tool")], False)

        approvals = [event for event in events if event["type"] == "approval_required"]
        self.assertEqual(approvals[0]["tool"], "write_tool")
        self.assertEqual(registry.calls, [])


class FakeToolkit:
    """审批测试用的受控工具箱。"""

    def __init__(self) -> None:
        self.called = False
        self._tools = {"write_tool": self.write_tool}

    @property
    def tools(self) -> dict:
        return self._tools

    def specs(self) -> list[ToolSpec]:
        return [ToolSpec("write_tool", "写操作", risk_level="write", requires_approval=True)]

    def write_tool(self, service: str = "api") -> dict:
        self.called = True
        return {"success": True, "summary": f"已处理 {service}", "data": {"service": service}}


class OpsApprovalAndTraceTest(unittest.IsolatedAsyncioTestCase):
    """验证审批执行链路和新 trace 结构。"""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(id="user-1", username="admin", nickname="管理员", password_hash="x", role="admin")
        self.trace = TraceRun(id="trace-1", status="running")
        self.run = AgentRun(id="run-1", trace_id=self.trace.id, user_id=self.user.id, message="重启服务", status="running")
        self.tool_call = AgentToolCall(
            id="tool-call-1",
            run=self.run,
            tool_name="write_tool",
            args={"service": "api"},
            status="blocked",
            risk_level="write",
            approval_status="pending",
        )
        self.approval = AgentApproval(
            id="approval-1",
            run=self.run,
            tool_call_id=self.tool_call.id,
            tool_name="write_tool",
            args={"service": "api"},
            status="pending",
            requested_by=self.user.id,
        )
        self.db.add_all([self.user, self.trace, self.run, self.tool_call, self.approval])
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    async def test_approval_uses_unified_registry_and_writes_trace(self) -> None:
        service = OpsAgentService(self.db)
        toolkit = FakeToolkit()
        service.toolkit = toolkit

        result = await service.approve(self.run.id, self.approval.id, True, "同意", self.user)

        self.assertEqual(result["status"], "approved")
        self.assertTrue(toolkit.called)
        self.db.refresh(self.tool_call)
        self.assertEqual(self.tool_call.status, "success")
        self.assertEqual(self.tool_call.approval_status, "approved")
        span = self.db.query(TraceSpan).filter(TraceSpan.trace_id == self.trace.id, TraceSpan.operation == "tool_call").first()
        self.assertEqual(span.metadata_json["context"]["toolName"], "write_tool")
        self.assertNotEqual(span.metadata_json["input"], span.metadata_json["output"])

    async def test_rejected_approval_does_not_execute_tool(self) -> None:
        service = OpsAgentService(self.db)
        toolkit = FakeToolkit()
        service.toolkit = toolkit

        result = await service.approve(self.run.id, self.approval.id, False, "拒绝", self.user)

        self.assertEqual(result["status"], "rejected")
        self.assertFalse(toolkit.called)
        self.db.refresh(self.tool_call)
        self.assertEqual(self.tool_call.approval_status, "rejected")
        self.assertEqual(self.tool_call.error_message, "approval_rejected")

    def test_evaluation_reads_tool_name_from_structured_trace(self) -> None:
        span = TraceSpan(
            trace_id=self.trace.id,
            operation="tool_call",
            status="success",
            duration_ms=5,
            metadata_json={
                "input": {"toolName": "container_logs", "args": {"service": "api"}},
                "output": {"result": {"success": True, "summary": "ok"}},
                "context": {"toolName": "container_logs", "riskLevel": "read"},
            },
        )
        eval_run = EvaluationRun(trace_id=self.trace.id)
        self.db.add_all([span, eval_run])
        self.db.commit()

        issues: list = []
        metrics = EvaluationService(self.db)._tool_metrics(eval_run, self.trace, issues)

        self.assertEqual(metrics[0].metric_key, "tool_success_rate")
        self.assertEqual(metrics[0].score, 1.0)
        self.assertFalse([issue for issue in issues if issue.issue_key == "unknown_tool"])


if __name__ == "__main__":
    unittest.main()
