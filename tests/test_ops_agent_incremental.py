from __future__ import annotations

import unittest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers.ops_agent import router as ops_agent_router
from app.agents.base import AgentStep, ToolSpec
from app.agents.ops_graph import OpsLangGraphRunner
from app.agents.orchestrator import OrchestratorAgent, PlannerAgent, ReplanDecision, StepExecutorAgent
from app.agents.tool_registry import ToolCallRequest, ToolCallResult, UnifiedTool, UnifiedToolRegistry
from app.agents.tools import OpsToolkit
from app.core.database import Base, get_db
from app.domain.models import AgentApproval, AgentRun, AgentToolCall, EvaluationRun, TraceRun, TraceSpan, User
from app.services.dependencies import require_admin
from app.services.evaluation_service import EvaluationService
from app.services.ops_agent_service import OpsAgentService
from app.services.trace_service import TraceService


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

    async def test_safe_read_command_executes_without_approval(self) -> None:
        """只读命令模板应直接执行，不能进入审批。"""

        toolkit = OpsToolkit()
        toolkit.executor_enabled = True
        captured: list[list[str]] = []

        def fake_run(args: list[str], timeout: int = 20) -> dict:
            captured.append(args)
            return {"success": True, "summary": "ok", "data": {"stdout": "ok", "stderr": "", "returncode": 0}, "error": ""}

        toolkit._run_docker = fake_run  # type: ignore[method-assign]
        registry = UnifiedToolRegistry(include_ops=True, toolkit=toolkit)

        result = await registry.call(ToolCallRequest("safe_command", {"commandId": "docker_ps"}))

        self.assertTrue(result.success)
        self.assertEqual(result.risk_level, "read")
        self.assertFalse(result.requires_approval)
        self.assertEqual(captured[0][0:2], ["container", "ls"])

    async def test_safe_write_command_requires_approval_then_executes(self) -> None:
        """写命令模板应先进入审批，审批通过后才执行。"""

        toolkit = OpsToolkit()
        toolkit.executor_enabled = True
        captured: list[list[str]] = []
        toolkit._resolve_container_id = lambda _service: "container-1"  # type: ignore[method-assign]

        def fake_run(args: list[str], timeout: int = 20) -> dict:
            captured.append(args)
            return {"success": True, "summary": "restarted", "data": {"stdout": "restarted", "stderr": "", "returncode": 0}, "error": ""}

        toolkit._run_docker = fake_run  # type: ignore[method-assign]
        registry = UnifiedToolRegistry(include_ops=True, toolkit=toolkit)
        request = ToolCallRequest("safe_command", {"commandId": "docker_restart", "args": {"service": "ragent-api"}})

        blocked = await registry.call(request)
        executed = await registry.call(request, skip_approval=True)

        self.assertEqual(blocked.error, "approval_required")
        self.assertEqual(blocked.risk_level, "write")
        self.assertTrue(blocked.requires_approval)
        self.assertTrue(executed.success)
        self.assertTrue(executed.requires_approval)
        self.assertEqual(captured[-1], ["restart", "container-1"])

    async def test_unknown_safe_command_is_rejected_without_approval(self) -> None:
        """未知或危险命令不能被审批放行，只能拒绝。"""

        toolkit = OpsToolkit()
        toolkit.executor_enabled = True
        registry = UnifiedToolRegistry(include_ops=True, toolkit=toolkit)

        result = await registry.call(ToolCallRequest("safe_command", {"command": "rm -rf /"}))

        self.assertFalse(result.success)
        self.assertEqual(result.error, "command_not_allowed")
        self.assertEqual(result.risk_level, "danger")
        self.assertFalse(result.requires_approval)

    async def test_alert_correlations_tool_is_readonly_and_callable(self) -> None:
        """告警关联分析应作为只读工具暴露给运维 Agent。"""

        toolkit = OpsToolkit()

        async def fake_tool_alert_correlations() -> dict:
            return {
                "success": True,
                "summary": "聚合 2 条活跃告警为 1 个告警组",
                "data": {"groupCount": 1, "affectedServices": ["order-api"]},
                "error": "",
            }

        toolkit.monitoring_service.tool_alert_correlations = fake_tool_alert_correlations  # type: ignore[method-assign]
        registry = UnifiedToolRegistry(include_ops=True, toolkit=toolkit)

        metadata = next(tool for tool in registry.list_tools("admin") if tool["name"] == "alert_correlations")
        result = await registry.call(ToolCallRequest("alert_correlations"))

        self.assertTrue(metadata["isReadOnly"])
        self.assertFalse(metadata["requiresApproval"])
        self.assertTrue(result.success)
        self.assertEqual(result.risk_level, "read")
        self.assertFalse(result.requires_approval)
        self.assertEqual(result.data["groupCount"], 1)

    async def test_change_correlations_tool_is_readonly_and_callable(self) -> None:
        """变更关联分析应作为只读工具暴露给运维 Agent。"""

        toolkit = OpsToolkit()

        async def fake_tool_change_correlations() -> dict:
            return {
                "success": True,
                "summary": "识别 1 个疑似相关变更",
                "data": {"changeCount": 1, "correlatedChanges": [{"service": "order-api"}]},
                "error": "",
            }

        toolkit.monitoring_service.tool_change_correlations = fake_tool_change_correlations  # type: ignore[method-assign]
        registry = UnifiedToolRegistry(include_ops=True, toolkit=toolkit)

        metadata = next(tool for tool in registry.list_tools("admin") if tool["name"] == "change_correlations")
        result = await registry.call(ToolCallRequest("change_correlations"))

        self.assertTrue(metadata["isReadOnly"])
        self.assertFalse(metadata["requiresApproval"])
        self.assertTrue(result.success)
        self.assertEqual(result.risk_level, "read")
        self.assertFalse(result.requires_approval)
        self.assertEqual(result.data["changeCount"], 1)

    async def test_deterministic_plan_uses_alert_correlations_for_alert_task(self) -> None:
        """告警类任务应优先生成告警关联分析步骤，降低重复告警噪声。"""

        registry = UnifiedToolRegistry(include_ops=True, toolkit=OpsToolkit())
        planner = PlannerAgent(registry)

        steps = await planner.create_plan("订单服务出现 critical 告警，需要定位根因")

        self.assertEqual(steps[1].tool_name, "alert_correlations")
        self.assertEqual(steps[2].tool_name, "change_correlations")
        self.assertIn("影响面", steps[1].reasoning)
        self.assertIn("变更", steps[2].reasoning)

    def test_final_report_includes_alert_impact_and_rca_hints(self) -> None:
        """最终报告应把告警关联工具的影响面和 RCA 线索结构化呈现。"""

        orchestrator = OrchestratorAgent(OpsToolkit())
        step = AgentStep(
            title="分析活跃告警关联与影响面",
            tool_name="alert_correlations",
            status="success",
            observation="聚合 2 条活跃告警为 1 个告警组",
            result={
                "success": True,
                "summary": "聚合 2 条活跃告警为 1 个告警组",
                "data": {
                    "affectedServices": ["order-api"],
                    "groups": [
                        {
                            "summary": "order-api 出现 2 条严重告警，涉及 1 个实例",
                            "rootCauseHints": ["资源饱和风险，优先检查 CPU 使用率"],
                            "recommendedNextSteps": ["查看 order-api 的最近指标趋势"],
                        }
                    ],
                },
            },
        )

        report = orchestrator._build_report("订单服务告警根因定位", [step], ReplanDecision("complete", "完成"))

        self.assertIn("### 影响面", report)
        self.assertIn("受影响服务：order-api", report)
        self.assertIn("### RCA 初筛线索", report)
        self.assertIn("资源饱和风险", report)
        self.assertIn("查看 order-api 的最近指标趋势", report)

    def test_final_report_includes_change_correlation_context(self) -> None:
        """最终报告应把变更关联候选和回滚建议结构化呈现。"""

        orchestrator = OrchestratorAgent(OpsToolkit())
        step = AgentStep(
            title="关联近期发布变更线索",
            tool_name="change_correlations",
            status="success",
            observation="识别 1 个疑似相关变更",
            result={
                "success": True,
                "summary": "识别 1 个疑似相关变更",
                "data": {
                    "correlatedChanges": [
                        {
                            "summary": "订单服务 存在疑似相关变更 2026.06.11.1，关联告警：HighErrorRate",
                            "confidence": "high",
                            "rollbackHint": "如确认变更导致故障，先查阅 订单服务 回滚 Runbook",
                        }
                    ],
                    "recommendedNextSteps": ["核对 订单服务 的发布记录 2026.06.11.1，确认告警是否在发布后出现"],
                },
            },
        )

        report = orchestrator._build_report("订单服务发布后告警", [step], ReplanDecision("complete", "完成"))

        self.assertIn("### 变更关联", report)
        self.assertIn("疑似相关变更 2026.06.11.1", report)
        self.assertIn("高置信变更候选", report)
        self.assertIn("回滚 Runbook", report)


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
        self.read_called = False
        self._tools = {
            "write_tool": self.write_tool,
            "read_tool": self.read_tool,
            "compose_restart_service": self.compose_restart_service,
            "api_health_check": self.api_health_check,
            "nginx_proxy_check": self.nginx_proxy_check,
        }

    @property
    def tools(self) -> dict:
        return self._tools

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec("write_tool", "写操作", risk_level="write", requires_approval=True),
            ToolSpec("read_tool", "只读操作"),
            ToolSpec("compose_restart_service", "重启服务", {"service": "string"}, risk_level="write", requires_approval=True),
            ToolSpec("api_health_check", "检查后端健康接口"),
            ToolSpec("nginx_proxy_check", "检查前端代理"),
        ]

    def write_tool(self, service: str = "api") -> dict:
        self.called = True
        return {"success": True, "summary": f"已处理 {service}", "data": {"service": service}}

    def read_tool(self) -> dict:
        self.read_called = True
        return {"success": True, "summary": "已读取"}

    def compose_restart_service(self, service: str = "ragent-api") -> dict:
        self.called = True
        return {"success": True, "summary": f"已重启 {service}", "data": {"service": service}}

    async def api_health_check(self) -> dict:
        self.read_called = True
        return {"success": True, "summary": "后端健康", "data": {"statusCode": 200}}

    async def nginx_proxy_check(self) -> dict:
        self.read_called = True
        return {"success": True, "summary": "前端代理健康", "data": {"statusCode": 200}}


class OpsApprovalAndTraceTest(unittest.IsolatedAsyncioTestCase):
    """验证审批执行链路和新 trace 结构。"""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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

    async def test_approved_restart_runs_post_verification_and_writes_trace(self) -> None:
        """重启类写操作审批通过后，应自动执行只读健康验证并写入 trace。"""

        self.approval.tool_name = "compose_restart_service"
        self.approval.args = {"service": "ragent-api"}
        self.tool_call.tool_name = "compose_restart_service"
        self.tool_call.args = {"service": "ragent-api"}
        self.db.commit()
        service = OpsAgentService(self.db)
        toolkit = FakeToolkit()
        service.toolkit = toolkit

        result = await service.approve(self.run.id, self.approval.id, True, "同意", self.user)

        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["verification"]["toolName"], "api_health_check")
        self.assertTrue(toolkit.called)
        self.assertTrue(toolkit.read_called)
        verification_call = (
            self.db.query(AgentToolCall)
            .filter(AgentToolCall.run_id == self.run.id, AgentToolCall.tool_name == "api_health_check")
            .one()
        )
        self.assertEqual(verification_call.status, "success")
        self.assertEqual(verification_call.approval_status, "not_required")
        span = self.db.query(TraceSpan).filter(TraceSpan.trace_id == self.trace.id, TraceSpan.operation == "verification").one()
        self.assertEqual(span.metadata_json["context"]["sourceTool"], "compose_restart_service")
        self.assertTrue(span.metadata_json["output"]["result"]["success"])

    def test_trace_service_redacts_sensitive_payloads(self) -> None:
        """Trace 入库前应递归脱敏，避免回放页面暴露凭证。"""

        trace_service = TraceService(self.db)
        span = trace_service.create_span(
            self.trace.id,
            "tool_call",
            input_data={
                "headers": {"Authorization": "Bearer secret-token"},
                "url": "https://user:pass@example.com/api?token=secret-token&safe=1",
            },
            metadata={"apiKey": "secret-key"},
        )
        trace_service.complete_span(span, output_data={"password": "secret-password", "summary": "ok"})

        row = self.db.query(TraceSpan).filter(TraceSpan.operation == "tool_call").one()
        text = str(row.metadata_json)
        self.assertIn("<redacted>", text)
        self.assertNotIn("secret-token", text)
        self.assertNotIn("secret-key", text)
        self.assertNotIn("secret-password", text)
        self.assertNotIn("user:pass", text)

    def test_persist_event_redacts_tool_args_and_results(self) -> None:
        """运维事件落库和 SSE 事件对象都应使用脱敏后的工具参数与结果。"""

        service = OpsAgentService(self.db)
        tool_event = {
            "type": "tool_call",
            "tool": "write_tool",
            "stepIndex": 0,
            "args": {"service": "api", "apiToken": "secret-token"},
            "status": "running",
        }
        service._persist_event(self.run, tool_event, self.user)
        observation = {
            "type": "observation",
            "tool": "write_tool",
            "stepIndex": 0,
            "durationMs": 3,
            "result": {"success": True, "summary": "ok", "data": {"password": "secret-password"}},
        }
        service._persist_event(self.run, observation, self.user)

        row = self.db.query(AgentToolCall).order_by(AgentToolCall.created_at.desc()).first()
        self.assertEqual(tool_event["args"]["apiToken"], "<redacted>")
        self.assertEqual(row.args["apiToken"], "<redacted>")
        self.assertEqual(observation["result"]["data"]["password"], "<redacted>")
        self.assertEqual(row.result["data"]["password"], "<redacted>")
        self.assertNotIn("secret-token", str(row.args))
        self.assertNotIn("secret-password", str(row.result))

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

    async def test_processed_approval_cannot_be_submitted_again(self) -> None:
        """已处理审批不能重复提交，避免写操作被二次执行。"""

        service = OpsAgentService(self.db)
        toolkit = FakeToolkit()
        service.toolkit = toolkit

        await service.approve(self.run.id, self.approval.id, True, "同意", self.user)
        toolkit.called = False

        with self.assertRaises(HTTPException) as context:
            await service.approve(self.run.id, self.approval.id, True, "再次同意", self.user)

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("重复", context.exception.detail)
        self.assertFalse(toolkit.called)

    async def test_approval_rejects_tool_call_argument_drift(self) -> None:
        """审批记录和原始工具调用参数不一致时，不能继续执行写操作。"""

        self.approval.args = {"service": "api"}
        self.tool_call.args = {"service": "frontend"}
        self.db.commit()
        service = OpsAgentService(self.db)
        toolkit = FakeToolkit()
        service.toolkit = toolkit

        with self.assertRaises(HTTPException) as context:
            await service.approve(self.run.id, self.approval.id, True, "同意", self.user)

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("不一致", context.exception.detail)
        self.assertFalse(toolkit.called)
        self.db.refresh(self.approval)
        self.assertEqual(self.approval.status, "pending")

    async def test_approval_revalidates_current_tool_policy(self) -> None:
        """审批接口只能放行当前仍需要审批的工具调用，不能借审批执行只读工具。"""

        self.approval.tool_name = "read_tool"
        self.approval.args = {}
        self.tool_call.tool_name = "read_tool"
        self.tool_call.args = {}
        self.db.commit()
        service = OpsAgentService(self.db)
        toolkit = FakeToolkit()
        service.toolkit = toolkit

        with self.assertRaises(HTTPException) as context:
            await service.approve(self.run.id, self.approval.id, True, "同意", self.user)

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("不需要审批", context.exception.detail)
        self.assertFalse(toolkit.read_called)
        self.db.refresh(self.approval)
        self.assertEqual(self.approval.status, "pending")

    async def test_approval_audit_lists_operator_and_filters_status(self) -> None:
        """审批审计应能追溯审批人、工具参数和审批状态。"""

        service = OpsAgentService(self.db)
        toolkit = FakeToolkit()
        service.toolkit = toolkit

        await service.approve(self.run.id, self.approval.id, False, "风险过高", self.user)

        payload = service.list_approval_audit_logs(page_no=1, page_size=10, status_filter="rejected")

        self.assertEqual(payload["total"], 1)
        item = payload["items"][0]
        self.assertEqual(item["id"], self.approval.id)
        self.assertEqual(item["runId"], self.run.id)
        self.assertEqual(item["toolName"], "write_tool")
        self.assertEqual(item["args"], {"service": "api"})
        self.assertEqual(item["status"], "rejected")
        self.assertEqual(item["requestedByName"], "admin")
        self.assertEqual(item["approvedByName"], "admin")
        self.assertEqual(item["comment"], "风险过高")
        self.assertEqual(item["message"], "重启服务")
        self.assertTrue(item["decidedAt"])

    def test_approval_audit_router_returns_admin_page(self) -> None:
        """审批审计接口应向管理员返回分页数据。"""

        app = FastAPI()
        app.include_router(ops_agent_router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[require_admin] = lambda: self.user

        response = TestClient(app).get("/agent/ops/approvals/audit", params={"pageNo": 1, "pageSize": 10})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["code"], 200)
        self.assertEqual(body["data"]["total"], 1)
        self.assertEqual(body["data"]["items"][0]["status"], "pending")

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
