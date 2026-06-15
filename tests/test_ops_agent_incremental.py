from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers.ops_agent import router as ops_agent_router
from app.agents.base import AgentStep, ToolSpec
from app.agents.ops_graph import OpsLangGraphRunner
from app.agents.orchestrator import AGENT_REGISTRY, OrchestratorAgent, PlannerAgent, ReplanDecision, StepExecutorAgent
from app.agents.tool_registry import ToolCallRequest, ToolCallResult, UnifiedTool, UnifiedToolRegistry
from app.agents.tools import OpsToolkit
from app.core.database import Base, get_db
from app.domain.models import AgentApproval, AgentCollaboration, AgentRun, AgentToolCall, EvaluationRun, TraceRun, TraceSpan, User
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

    def test_agent_registry_exposes_verification_and_audit_agents(self) -> None:
        """运维 Agent 团队应显式暴露验证 Agent 和审计 Agent。"""

        self.assertIn("verification", AGENT_REGISTRY)
        self.assertIn("audit", AGENT_REGISTRY)
        self.assertIn("验证", AGENT_REGISTRY["verification"]["name"])
        self.assertIn("审计", AGENT_REGISTRY["audit"]["name"])

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

    async def test_safe_command_rejects_sensitive_args_before_approval(self) -> None:
        """命令模板参数不能携带 token、password 等凭证字段，避免 LLM 把密钥送入执行器。"""

        toolkit = OpsToolkit()
        toolkit.executor_enabled = True
        captured: list[list[str]] = []
        toolkit._run_docker = lambda args, timeout=20: captured.append(args) or {"success": True, "summary": "ok", "data": {}, "error": ""}  # type: ignore[method-assign]
        registry = UnifiedToolRegistry(include_ops=True, toolkit=toolkit)
        request = ToolCallRequest("safe_command", {"commandId": "docker_logs", "args": {"service": "ragent-api", "apiToken": "secret-token"}})

        risk_level, requires_approval = registry.tools["safe_command"].policy_for(request.args)
        result = await registry.call(request, skip_approval=True)

        self.assertEqual(risk_level, "danger")
        self.assertFalse(requires_approval)
        self.assertFalse(result.success)
        self.assertEqual(result.error, "command_not_allowed")
        self.assertIn("敏感凭证字段", result.summary)
        self.assertEqual(captured, [])

    async def test_safe_command_rejects_sensitive_command_text(self) -> None:
        """命令文本里出现凭证参数时，即使命中白名单命令也应拒绝。"""

        toolkit = OpsToolkit()
        toolkit.executor_enabled = True
        registry = UnifiedToolRegistry(include_ops=True, toolkit=toolkit)

        result = await registry.call(ToolCallRequest("safe_command", {"command": "docker ps --token secret-token"}), skip_approval=True)

        self.assertFalse(result.success)
        self.assertEqual(result.error, "command_not_allowed")
        self.assertEqual(result.risk_level, "danger")
        self.assertFalse(result.requires_approval)

    def test_docker_output_is_redacted_before_tool_result(self) -> None:
        """Docker stdout/stderr 返回给 Agent 前就应脱敏，避免日志凭证进入 SSE。"""

        class CompletedProcessStub:
            returncode = 0
            stdout = "Authorization: Bearer secret-token\npassword=secret-password\nurl=https://user:pass@example.com/api?token=url-token"
            stderr = "api_key=secret-api-key"

        toolkit = OpsToolkit()
        toolkit.executor_enabled = True

        with patch("app.agents.tools.subprocess.run", return_value=CompletedProcessStub()):
            result = toolkit._run_docker(["container", "logs", "container-1"])

        text = str(result)
        self.assertTrue(result["success"])
        self.assertIn("<redacted>", text)
        self.assertNotIn("secret-token", text)
        self.assertNotIn("secret-password", text)
        self.assertNotIn("secret-api-key", text)
        self.assertNotIn("url-token", text)
        self.assertNotIn("user:pass", text)

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

    async def test_release_evidence_tool_is_readonly_and_callable(self) -> None:
        """Git 与 CI/CD 发布证据应作为只读工具暴露给运维 Agent。"""

        toolkit = OpsToolkit()

        async def fake_release_evidence(limit: int = 10) -> dict:
            return {
                "success": True,
                "summary": f"分析最近 {limit} 个提交，识别 1 条发布风险",
                "data": {"repo": {"branch": "main", "headSha": "abc1234"}, "riskSignals": [{"type": "dirty_worktree"}]},
                "error": "",
            }

        toolkit.release_evidence = fake_release_evidence  # type: ignore[method-assign]
        toolkit._tools["release_evidence"] = toolkit.release_evidence
        registry = UnifiedToolRegistry(include_ops=True, toolkit=toolkit)

        metadata = next(tool for tool in registry.list_tools("admin") if tool["name"] == "release_evidence")
        result = await registry.call(ToolCallRequest("release_evidence", {"limit": 5}))

        self.assertTrue(metadata["isReadOnly"])
        self.assertFalse(metadata["requiresApproval"])
        self.assertTrue(result.success)
        self.assertEqual(result.risk_level, "read")
        self.assertFalse(result.requires_approval)
        self.assertEqual(result.data["repo"]["branch"], "main")

    async def test_kubernetes_events_tool_is_readonly_and_callable(self) -> None:
        """Kubernetes 事件分析应作为只读工具暴露给运维 Agent。"""

        toolkit = OpsToolkit()

        async def fake_tool_kubernetes_events() -> dict:
            return {
                "success": True,
                "summary": "识别 1 个 Kubernetes 事件线索",
                "data": {"eventCount": 1, "events": [{"reason": "CrashLoopBackOff"}]},
                "error": "",
            }

        toolkit.monitoring_service.tool_kubernetes_events = fake_tool_kubernetes_events  # type: ignore[method-assign]
        registry = UnifiedToolRegistry(include_ops=True, toolkit=toolkit)

        metadata = next(tool for tool in registry.list_tools("admin") if tool["name"] == "kubernetes_events")
        result = await registry.call(ToolCallRequest("kubernetes_events"))

        self.assertTrue(metadata["isReadOnly"])
        self.assertFalse(metadata["requiresApproval"])
        self.assertTrue(result.success)
        self.assertEqual(result.risk_level, "read")
        self.assertFalse(result.requires_approval)
        self.assertEqual(result.data["eventCount"], 1)

    async def test_trace_analysis_tool_is_readonly_and_callable(self) -> None:
        """Trace 分析应作为只读工具暴露给运维 Agent。"""

        toolkit = OpsToolkit()

        async def fake_trace_analysis(limit: int = 20, slowThresholdMs: int = 1000) -> dict:
            return {
                "success": True,
                "summary": f"分析 {limit} 条 Trace，慢阈值 {slowThresholdMs} ms",
                "data": {"runCount": limit, "slowThresholdMs": slowThresholdMs, "slowSpans": [{"operation": "llm"}]},
                "error": "",
            }

        toolkit.trace_analysis = fake_trace_analysis  # type: ignore[method-assign]
        toolkit._tools["trace_analysis"] = toolkit.trace_analysis
        registry = UnifiedToolRegistry(include_ops=True, toolkit=toolkit)

        metadata = next(tool for tool in registry.list_tools("admin") if tool["name"] == "trace_analysis")
        result = await registry.call(ToolCallRequest("trace_analysis", {"limit": 5, "slowThresholdMs": 800}))

        self.assertTrue(metadata["isReadOnly"])
        self.assertFalse(metadata["requiresApproval"])
        self.assertTrue(result.success)
        self.assertEqual(result.risk_level, "read")
        self.assertFalse(result.requires_approval)
        self.assertEqual(result.data["runCount"], 5)

    async def test_database_middleware_health_tool_is_readonly_and_callable(self) -> None:
        """数据库与中间件健康分析应作为只读工具暴露给运维 Agent。"""

        toolkit = OpsToolkit()

        async def fake_tool_database_middleware_health() -> dict:
            return {
                "success": True,
                "summary": "发现 1 个异常组件",
                "data": {"components": [{"key": "mysql", "status": "critical"}]},
                "error": "",
            }

        toolkit.monitoring_service.tool_database_middleware_health = fake_tool_database_middleware_health  # type: ignore[method-assign]
        registry = UnifiedToolRegistry(include_ops=True, toolkit=toolkit)

        metadata = next(tool for tool in registry.list_tools("admin") if tool["name"] == "database_middleware_health")
        result = await registry.call(ToolCallRequest("database_middleware_health"))

        self.assertTrue(metadata["isReadOnly"])
        self.assertFalse(metadata["requiresApproval"])
        self.assertTrue(result.success)
        self.assertEqual(result.risk_level, "read")
        self.assertFalse(result.requires_approval)
        self.assertEqual(result.data["components"][0]["key"], "mysql")

    async def test_cloud_resource_evidence_tool_is_readonly_and_callable(self) -> None:
        """云平台资源证据应作为只读工具暴露给运维 Agent。"""

        toolkit = OpsToolkit()

        async def fake_cloud_resource_evidence() -> dict:
            return {
                "success": True,
                "summary": "识别 1 个云资源配置、1 条云资源告警、1 条风险信号",
                "data": {"resources": [{"resourceId": "ecs-order-01"}], "cloudAlerts": [{"alertName": "CloudInstanceDown"}]},
                "error": "",
            }

        toolkit.cloud_resource_evidence = fake_cloud_resource_evidence  # type: ignore[method-assign]
        toolkit._tools["cloud_resource_evidence"] = toolkit.cloud_resource_evidence
        registry = UnifiedToolRegistry(include_ops=True, toolkit=toolkit)

        metadata = next(tool for tool in registry.list_tools("admin") if tool["name"] == "cloud_resource_evidence")
        result = await registry.call(ToolCallRequest("cloud_resource_evidence"))

        self.assertTrue(metadata["isReadOnly"])
        self.assertFalse(metadata["requiresApproval"])
        self.assertTrue(result.success)
        self.assertEqual(result.risk_level, "read")
        self.assertFalse(result.requires_approval)
        self.assertEqual(result.data["resources"][0]["resourceId"], "ecs-order-01")

    async def test_service_topology_tool_is_readonly_and_callable(self) -> None:
        """服务拓扑分析应作为只读工具暴露给运维 Agent。"""

        toolkit = OpsToolkit()

        async def fake_tool_service_topology() -> dict:
            return {
                "success": True,
                "summary": "识别 1 个直接异常节点",
                "data": {"affectedNodeIds": ["payment-service"], "impactedNodeIds": ["order-service", "payment-service"]},
                "error": "",
            }

        toolkit.monitoring_service.tool_service_topology = fake_tool_service_topology  # type: ignore[method-assign]
        registry = UnifiedToolRegistry(include_ops=True, toolkit=toolkit)

        metadata = next(tool for tool in registry.list_tools("admin") if tool["name"] == "service_topology")
        result = await registry.call(ToolCallRequest("service_topology"))

        self.assertTrue(metadata["isReadOnly"])
        self.assertFalse(metadata["requiresApproval"])
        self.assertTrue(result.success)
        self.assertEqual(result.risk_level, "read")
        self.assertFalse(result.requires_approval)
        self.assertEqual(result.data["affectedNodeIds"], ["payment-service"])

    async def test_metric_anomalies_tool_is_readonly_and_callable(self) -> None:
        """指标异常检测应作为只读工具暴露给运维 Agent。"""

        toolkit = OpsToolkit()

        async def fake_tool_metric_anomalies(metric: str = "cpu_percent", minutes: int = 30) -> dict:
            return {
                "success": True,
                "summary": f"{metric} 检测到 1 个异常信号",
                "data": {"metric": metric, "minutes": minutes, "anomalies": [{"type": "spike"}]},
                "error": "",
            }

        toolkit.monitoring_service.tool_metric_anomalies = fake_tool_metric_anomalies  # type: ignore[method-assign]
        registry = UnifiedToolRegistry(include_ops=True, toolkit=toolkit)

        metadata = next(tool for tool in registry.list_tools("admin") if tool["name"] == "metric_anomalies")
        result = await registry.call(ToolCallRequest("metric_anomalies", {"metric": "cpu_percent", "minutes": 30}))

        self.assertTrue(metadata["isReadOnly"])
        self.assertFalse(metadata["requiresApproval"])
        self.assertTrue(result.success)
        self.assertEqual(result.risk_level, "read")
        self.assertFalse(result.requires_approval)
        self.assertEqual(result.data["anomalies"][0]["type"], "spike")

    async def test_knowledge_search_alias_is_readonly_and_available(self) -> None:
        """知识 Agent 检索 Runbook、历史事故和架构文档时只能走只读 MCP 别名。"""

        registry = UnifiedToolRegistry(include_ops=True, toolkit=OpsToolkit())

        metadata = next(tool for tool in registry.list_tools("admin") if tool["name"] == "knowledge_search")

        self.assertTrue(metadata["isReadOnly"])
        self.assertFalse(metadata["requiresApproval"])
        self.assertEqual(metadata["riskLevel"], "read")
        self.assertEqual(metadata["category"], "knowledge")

    async def test_deterministic_plan_uses_alert_correlations_for_alert_task(self) -> None:
        """告警类任务应优先生成告警关联分析步骤，降低重复告警噪声。"""

        registry = UnifiedToolRegistry(include_ops=True, toolkit=OpsToolkit())
        planner = PlannerAgent(registry)

        steps = await planner.create_plan("订单服务出现 critical 告警，需要定位根因")

        self.assertEqual(steps[1].tool_name, "alert_correlations")
        self.assertEqual(steps[2].tool_name, "knowledge_search")
        self.assertEqual(steps[2].assigned_agent, "knowledge")
        self.assertEqual(steps[3].tool_name, "kubernetes_events")
        self.assertEqual(steps[4].tool_name, "trace_analysis")
        self.assertEqual(steps[5].tool_name, "database_middleware_health")
        self.assertEqual(steps[6].tool_name, "cloud_resource_evidence")
        self.assertEqual(steps[7].tool_name, "service_topology")
        self.assertEqual(steps[8].tool_name, "release_evidence")
        self.assertEqual(steps[9].tool_name, "change_correlations")
        self.assertTrue(any(step.tool_name == "metric_anomalies" for step in steps))
        self.assertIn("影响面", steps[1].reasoning)
        self.assertIn("Runbook", steps[2].reasoning)
        self.assertIn("Pod", steps[3].reasoning)
        self.assertIn("span", steps[4].reasoning)
        self.assertIn("Redis", steps[5].reasoning)
        self.assertIn("云主机", steps[6].reasoning)
        self.assertIn("拓扑", steps[7].reasoning)
        self.assertIn("HEAD", steps[8].reasoning)
        self.assertIn("变更", steps[9].reasoning)

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

    def test_final_report_includes_knowledge_context(self) -> None:
        """最终报告应把 Runbook、历史事故和架构文档检索线索纳入 RCA 与修复建议。"""

        orchestrator = OrchestratorAgent(OpsToolkit())
        step = AgentStep(
            title="检索 Runbook 与历史事故知识",
            tool_name="knowledge_search",
            status="success",
            observation="检索到 2 条知识库线索",
            result={
                "success": True,
                "summary": "检索到 2 条知识库线索",
                "data": {
                    "value": [
                        {
                            "content": "订单服务故障 Runbook：先检查错误率，必要时回滚到上一稳定版本，回滚后验证健康检查",
                            "metadata": {"source": "runbooks/order.md"},
                        },
                        {
                            "content": "历史事故复盘：2026-06-01 支付依赖超时导致订单失败，需核对调用链和依赖状态",
                            "metadata": {"source": "incidents/2026-06-01.md"},
                        },
                    ]
                },
            },
        )

        report = orchestrator._build_report("订单服务故障根因定位", [step], ReplanDecision("complete", "完成"))

        self.assertIn("### 知识库线索", report)
        self.assertIn("Runbook：runbooks/order.md", report)
        self.assertIn("历史事故：incidents/2026-06-01.md", report)
        self.assertIn("知识库命中 Runbook", report)
        self.assertIn("参考 Runbook runbooks/order.md", report)
        self.assertIn("### 修复方案与风险评估", report)

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
        self.assertIn("### 回滚与人工接管", report)
        self.assertIn("疑似相关变更 2026.06.11.1", report)
        self.assertIn("高置信变更候选", report)
        self.assertIn("回滚 Runbook", report)
        self.assertIn("### 修复方案与风险评估", report)
        self.assertIn("审批门禁", report)
        self.assertIn("验证计划", report)

    def test_final_report_builds_remediation_plan_with_risk_assessment(self) -> None:
        """最终报告应把建议动作整理成可审批的修复方案和风险评估。"""

        orchestrator = OrchestratorAgent(OpsToolkit())
        step = AgentStep(
            title="分析数据库与中间件健康",
            tool_name="database_middleware_health",
            status="success",
            observation="发现 1 个异常组件",
            result={
                "success": True,
                "summary": "发现 1 个异常组件",
                "data": {
                    "components": [{"key": "redis", "name": "Redis", "status": "critical", "message": "Redis down"}],
                    "rootCauseHints": ["Redis 健康异常，优先检查实例存活、Exporter、网络和连接池"],
                    "recommendedNextSteps": ["查看 Redis 日志和连接池指标", "重启 Redis 连接异常的应用服务"],
                },
            },
        )

        report = orchestrator._build_report("Redis 异常导致接口失败", [step], ReplanDecision("complete", "完成"))

        self.assertIn("### 修复方案与风险评估", report)
        self.assertIn("修复步骤", report)
        self.assertIn("重启 Redis 连接异常的应用服务 [风险=high, 审批=是]", report)
        self.assertIn("风险评估：high", report)
        self.assertIn("审批后才允许执行", report)

    def test_final_report_includes_release_evidence_context(self) -> None:
        """最终报告应把 Git 与 CI/CD 发布证据结构化呈现。"""

        orchestrator = OrchestratorAgent(OpsToolkit())
        step = AgentStep(
            title="分析 Git 与 CI/CD 发布证据",
            tool_name="release_evidence",
            status="success",
            observation="当前分支 main@abc1234，github_actions，识别 1 条发布风险信号",
            result={
                "success": True,
                "summary": "当前分支 main@abc1234，github_actions，识别 1 条发布风险信号",
                "data": {
                    "repo": {"branch": "main", "headSha": "abc1234", "upstream": "origin/main", "ahead": 1, "behind": 0, "dirty": True},
                    "ci": {"provider": "github_actions", "runId": "99", "sha": "abc1234", "ref": "main"},
                    "recentCommits": [{"sha": "abc1234", "date": "2026-06-11T10:00:00+08:00", "subject": "fix: repair deploy config"}],
                    "riskSignals": [{"severity": "medium", "type": "dirty_worktree", "message": "工作区存在未提交改动，发布前需要确认是否混入未审计变更"}],
                    "rootCauseHints": ["当前 HEAD abc1234 最近提交：fix: repair deploy config"],
                    "recommendedNextSteps": ["把告警首次触发时间与最近提交时间、CI/CD 部署时间做时间线对齐"],
                    "dataGaps": [],
                },
            },
        )

        report = orchestrator._build_report("发布后接口异常", [step], ReplanDecision("complete", "完成"))

        self.assertIn("### Git 与 CI/CD", report)
        self.assertIn("仓库状态：main@abc1234", report)
        self.assertIn("流水线：github_actions", report)
        self.assertIn("发布风险：medium 工作区存在未提交改动", report)
        self.assertIn("### RCA 初筛线索", report)
        self.assertIn("时间线对齐", report)

    def test_final_report_includes_service_topology_context(self) -> None:
        """最终报告应把拓扑影响路径和依赖边结构化呈现。"""

        orchestrator = OrchestratorAgent(OpsToolkit())
        step = AgentStep(
            title="分析服务拓扑和影响传播",
            tool_name="service_topology",
            status="success",
            observation="识别 1 个直接异常节点，可能影响 2 个拓扑节点",
            result={
                "success": True,
                "summary": "识别 1 个直接异常节点，可能影响 2 个拓扑节点",
                "data": {
                    "nodes": [
                        {"id": "payment-service", "name": "支付服务", "impactStatus": "affected"},
                        {"id": "order-service", "name": "订单服务", "impactStatus": "impacted"},
                    ],
                    "edges": [{"source": "order-service", "target": "payment-service"}],
                    "impactPaths": [{"summary": "支付服务 -> 订单服务"}],
                    "recommendedNextSteps": ["优先检查直接异常节点 支付服务 的日志、指标和最近变更"],
                },
            },
        )

        report = orchestrator._build_report("支付服务故障影响订单", [step], ReplanDecision("complete", "完成"))

        self.assertIn("### 服务拓扑", report)
        self.assertIn("直接异常节点：支付服务", report)
        self.assertIn("可能受波及节点：订单服务", report)
        self.assertIn("影响传播路径：支付服务 -> 订单服务", report)
        self.assertIn("优先检查直接异常节点 支付服务", report)

    def test_final_report_includes_kubernetes_event_context(self) -> None:
        """最终报告应把 Kubernetes 事件线索结构化呈现。"""

        orchestrator = OrchestratorAgent(OpsToolkit())
        step = AgentStep(
            title="分析 Kubernetes 事件线索",
            tool_name="kubernetes_events",
            status="success",
            observation="识别 1 个 Kubernetes 事件线索",
            result={
                "success": True,
                "summary": "识别 1 个 Kubernetes 事件线索",
                "data": {
                    "affectedNamespaces": ["prod"],
                    "affectedWorkloads": ["order-api"],
                    "events": [
                        {
                            "summary": "prod/order-api-7f9c 出现 CrashLoopBackOff：order-api 反复重启",
                            "reason": "CrashLoopBackOff",
                        }
                    ],
                    "rootCauseHints": ["Pod 反复重启，优先检查 previous logs、启动探针、配置变更和依赖可达性"],
                    "recommendedNextSteps": ["查看 prod/order-api-7f9c 的 Kubernetes Events 和 previous logs"],
                },
            },
        )

        report = orchestrator._build_report("订单服务 Pod 重启", [step], ReplanDecision("complete", "完成"))

        self.assertIn("### Kubernetes 事件", report)
        self.assertIn("受影响命名空间：prod", report)
        self.assertIn("受影响工作负载：order-api", report)
        self.assertIn("CrashLoopBackOff", report)
        self.assertIn("previous logs", report)

    def test_final_report_includes_trace_analysis_context(self) -> None:
        """最终报告应把 Trace 慢节点和失败节点结构化呈现。"""

        orchestrator = OrchestratorAgent(OpsToolkit())
        step = AgentStep(
            title="分析 Trace 调用链证据",
            tool_name="trace_analysis",
            status="success",
            observation="分析 1 条 Trace、3 个 span，发现 1 个失败 span 和 1 个慢 span",
            result={
                "success": True,
                "summary": "分析 1 条 Trace、3 个 span，发现 1 个失败 span 和 1 个慢 span",
                "data": {
                    "errorSpans": [{"traceId": "trace-1", "operation": "tool_call", "status": "failed", "errorMessage": "connection refused"}],
                    "slowSpans": [{"traceId": "trace-1", "operation": "llm", "durationMs": 1800}],
                    "topOperations": [{"operation": "llm", "count": 1, "totalDurationMs": 1800, "errorCount": 0}],
                    "rootCauseHints": ["模型调用耗时靠前，优先检查模型响应时间"],
                    "recommendedNextSteps": ["打开 Trace trace-1，查看失败节点 tool_call 的 input/output"],
                },
            },
        )

        report = orchestrator._build_report("后端请求慢", [step], ReplanDecision("complete", "完成"))

        self.assertIn("### Trace 调用链", report)
        self.assertIn("失败 span：tool_call", report)
        self.assertIn("慢 span：llm", report)
        self.assertIn("耗时热点：llm", report)
        self.assertIn("模型调用耗时靠前", report)
        self.assertIn("打开 Trace trace-1", report)

    def test_final_report_includes_database_middleware_context(self) -> None:
        """最终报告应把数据库和中间件健康信号结构化呈现。"""

        orchestrator = OrchestratorAgent(OpsToolkit())
        step = AgentStep(
            title="分析数据库与中间件健康",
            tool_name="database_middleware_health",
            status="success",
            observation="发现 1 个异常组件和 1 条数据库/中间件告警信号",
            result={
                "success": True,
                "summary": "发现 1 个异常组件和 1 条数据库/中间件告警信号",
                "data": {
                    "components": [
                        {"key": "mysql", "name": "MySQL", "status": "critical", "message": "MySQL 采集目标不可用或实例 down"},
                        {"key": "redis", "name": "Redis", "status": "healthy", "message": "Redis up=1"},
                    ],
                    "alertSignals": [
                        {"component": "mysql", "signalType": "latency", "summary": "MySQL slow query latency high"}
                    ],
                    "rootCauseHints": ["MySQL 存在慢查询或延迟信号，优先关联 Trace 慢 span、慢 SQL 和连接池等待"],
                    "recommendedNextSteps": ["围绕 mysql 的 latency 告警，关联同一时间窗口的应用日志、Trace 慢 span 和发布变更"],
                },
            },
        )

        report = orchestrator._build_report("数据库慢查询告警", [step], ReplanDecision("complete", "完成"))

        self.assertIn("### 数据库与中间件", report)
        self.assertIn("组件状态：MySQL critical", report)
        self.assertIn("告警信号：mysql latency", report)
        self.assertIn("异常数据库/中间件：MySQL", report)
        self.assertIn("Trace 慢 span", report)

    def test_final_report_includes_cloud_resource_context(self) -> None:
        """最终报告应把云平台资源证据结构化呈现。"""

        orchestrator = OrchestratorAgent(OpsToolkit())
        step = AgentStep(
            title="分析云平台资源证据",
            tool_name="cloud_resource_evidence",
            status="success",
            observation="识别 1 个云资源配置、1 条云资源告警、1 条风险信号",
            result={
                "success": True,
                "summary": "识别 1 个云资源配置、1 条云资源告警、1 条风险信号",
                "data": {
                    "matchedResources": [
                        {
                            "resourceId": "ecs-order-01",
                            "name": "订单服务云主机",
                            "provider": "aliyun",
                            "region": "cn-hangzhou",
                            "service": "order-service",
                            "alertCount": 1,
                        }
                    ],
                    "cloudAlerts": [{"alertName": "CloudInstanceDown", "severity": "critical", "summary": "订单服务云主机不可用"}],
                    "riskSignals": [{"severity": "high", "type": "cloud_alert", "message": "云资源告警 CloudInstanceDown：订单服务云主机不可用"}],
                    "rootCauseHints": ["优先核对 cn-hangzhou ecs-order-01 的云监控、实例事件、网络 ACL/安全组和资源配额"],
                    "recommendedNextSteps": ["在云控制台核对 ecs-order-01 的实例事件、资源利用率、网络安全组和最近变更"],
                    "dataGaps": [],
                },
            },
        )

        report = orchestrator._build_report("订单服务云主机告警", [step], ReplanDecision("complete", "完成"))

        self.assertIn("### 云平台资源", report)
        self.assertIn("云资源受影响：订单服务云主机", report)
        self.assertIn("云告警：CloudInstanceDown", report)
        self.assertIn("云资源风险：high", report)
        self.assertIn("### 影响面", report)
        self.assertIn("云监控", report)

    def test_final_report_includes_metric_anomaly_context(self) -> None:
        """最终报告应把指标异常信号结构化呈现。"""

        orchestrator = OrchestratorAgent(OpsToolkit())
        step = AgentStep(
            title="检测 CPU 指标异常",
            tool_name="metric_anomalies",
            status="success",
            observation="CPU 使用率 检测到 1 个异常信号",
            result={
                "success": True,
                "summary": "CPU 使用率 检测到 1 个异常信号",
                "data": {
                    "metricLabel": "CPU 使用率",
                    "anomalies": [
                        {"type": "high_watermark", "severity": "critical", "summary": "最大值 95.00% 超过 90% 高水位"}
                    ],
                    "recommendedNextSteps": ["将 CPU 使用率 异常窗口与活跃告警、服务拓扑和最近变更做时间线对齐"],
                },
            },
        )

        report = orchestrator._build_report("后端 CPU 异常", [step], ReplanDecision("complete", "完成"))

        self.assertIn("### 指标异常", report)
        self.assertIn("CPU 使用率 critical high_watermark", report)
        self.assertIn("### RCA 初筛线索", report)
        self.assertIn("时间线对齐", report)


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

    async def test_final_node_emits_audit_checkpoint(self) -> None:
        """每轮运维运行结束前应由审计 Agent 输出结构化审计检查点。"""

        registry = FakeRegistry()

        events = await self._run(registry, [AgentStep("读取状态", "read_tool")], True)

        audit_events = [event for event in events if event["type"] == "audit_checkpoint"]
        self.assertEqual(audit_events[0]["agent"], "audit")
        self.assertEqual(audit_events[0]["result"]["data"]["metrics"]["plannedStepCount"], 1)
        self.assertEqual(audit_events[0]["result"]["data"]["checks"][0]["code"], "plan_recorded")


class FakeToolkit:
    """审批测试用的受控工具箱。"""

    def __init__(self) -> None:
        self.called = False
        self.read_called = False
        self.read_calls: list[str] = []
        self.fail_metric = ""
        self._tools = {
            "write_tool": self.write_tool,
            "read_tool": self.read_tool,
            "compose_restart_service": self.compose_restart_service,
            "api_health_check": self.api_health_check,
            "frontend_health_check": self.frontend_health_check,
            "nginx_proxy_check": self.nginx_proxy_check,
            "metric_trend": self.metric_trend,
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
            ToolSpec("frontend_health_check", "检查前端入口"),
            ToolSpec("nginx_proxy_check", "检查前端代理"),
            ToolSpec("metric_trend", "查看指标趋势", {"metric": "string", "minutes": "integer"}),
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
        self.read_calls.append("api_health_check")
        return {"success": True, "summary": "后端健康", "data": {"statusCode": 200}}

    async def frontend_health_check(self) -> dict:
        self.read_called = True
        self.read_calls.append("frontend_health_check")
        return {"success": True, "summary": "前端入口健康", "data": {"statusCode": 200}}

    async def nginx_proxy_check(self) -> dict:
        self.read_called = True
        self.read_calls.append("nginx_proxy_check")
        return {"success": True, "summary": "前端代理健康", "data": {"statusCode": 200}}

    async def metric_trend(self, metric: str = "cpu_percent", minutes: int = 30) -> dict:
        self.read_called = True
        self.read_calls.append(f"metric_trend:{metric}")
        if metric == self.fail_metric:
            return {"success": False, "summary": f"{metric} 指标查询失败", "error": "monitoring_query_failed"}
        return {"success": True, "summary": f"{metric} 最近 {minutes} 分钟趋势正常", "data": {"metric": metric, "minutes": minutes}}


class FakeReadinessService:
    """审批门禁测试用的 AIOps 就绪检查桩。"""

    def __init__(self, status: str = "degraded") -> None:
        self.status = status

    def build(self) -> dict:
        return {
            "status": self.status,
            "summary": "测试就绪状态",
            "nextSteps": ["配置 monitoring.enabled、prometheus_url 和 alertmanager_url"],
        }


class OpsApprovalAndTraceTest(unittest.IsolatedAsyncioTestCase):
    """验证审批执行链路和新 trace 结构。"""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(id="user-1", username="admin", nickname="管理员", password_hash="x", role="admin")
        self.approver = User(id="user-2", username="sre", nickname="值班 SRE", password_hash="x", role="admin")
        self.viewer = User(id="user-3", username="viewer", nickname="观察员", password_hash="x", role="user")
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
        self.db.add_all([self.user, self.approver, self.viewer, self.trace, self.run, self.tool_call, self.approval])
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    async def test_approval_uses_unified_registry_and_writes_trace(self) -> None:
        service = OpsAgentService(self.db)
        toolkit = FakeToolkit()
        service.toolkit = toolkit

        result = await service.approve(self.run.id, self.approval.id, True, "同意", self.approver)

        self.assertEqual(result["status"], "approved")
        self.assertTrue(toolkit.called)
        self.db.refresh(self.tool_call)
        self.assertEqual(self.tool_call.status, "success")
        self.assertEqual(self.tool_call.approval_status, "approved")
        span = self.db.query(TraceSpan).filter(TraceSpan.trace_id == self.trace.id, TraceSpan.operation == "tool_call").first()
        self.assertEqual(span.metadata_json["context"]["toolName"], "write_tool")
        self.assertNotEqual(span.metadata_json["input"], span.metadata_json["output"])

    async def test_approval_blocks_self_approved_high_risk_write(self) -> None:
        """申请人不能批准自己发起的高风险写操作，必须交给非申请人复核。"""

        service = OpsAgentService(self.db)
        toolkit = FakeToolkit()
        service.toolkit = toolkit

        with self.assertRaises(HTTPException) as context:
            await service.approve(self.run.id, self.approval.id, True, "自己同意", self.user)

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("不能由申请人本人审批", context.exception.detail)
        self.assertFalse(toolkit.called)
        self.db.refresh(self.approval)
        self.db.refresh(self.tool_call)
        self.assertEqual(self.approval.status, "pending")
        self.assertIsNone(self.approval.approved_by)
        self.assertEqual(self.tool_call.status, "blocked")
        handoff = self.db.query(AgentCollaboration).filter(AgentCollaboration.run_id == self.run.id).one()
        self.assertEqual(handoff.data["eventType"], "approval_separation_blocked")
        self.assertEqual(handoff.data["attemptedApprover"], self.user.id)
        self.assertEqual(handoff.data["requiredAction"], "four_eyes_approval")

    async def test_non_admin_cannot_approve_ops_write(self) -> None:
        """服务层应拒绝非管理员直接审批生产写操作，避免绕过路由 RBAC。"""

        service = OpsAgentService(self.db)
        toolkit = FakeToolkit()
        service.toolkit = toolkit

        with self.assertRaises(HTTPException) as context:
            await service.approve(self.run.id, self.approval.id, True, "越权同意", self.viewer)

        self.assertEqual(context.exception.status_code, 403)
        self.assertIn("管理员权限", context.exception.detail)
        self.assertFalse(toolkit.called)
        self.db.refresh(self.approval)
        self.db.refresh(self.tool_call)
        self.assertEqual(self.approval.status, "pending")
        self.assertIsNone(self.approval.approved_by)
        self.assertEqual(self.tool_call.status, "blocked")

    async def test_approval_blocks_write_when_aiops_readiness_blocked(self) -> None:
        """AIOps 生产就绪检查阻塞时，即使人工批准也不能执行写操作。"""

        service = OpsAgentService(self.db)
        toolkit = FakeToolkit()
        service.toolkit = toolkit
        service.readiness_service = FakeReadinessService("blocked")  # type: ignore[assignment]

        with self.assertRaises(HTTPException) as context:
            await service.approve(self.run.id, self.approval.id, True, "同意", self.approver)

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("生产就绪检查未通过", str(context.exception.detail))
        self.assertFalse(toolkit.called)
        self.db.refresh(self.approval)
        self.db.refresh(self.tool_call)
        self.assertEqual(self.approval.status, "pending")
        self.assertEqual(self.tool_call.status, "blocked")
        handoff = self.db.query(AgentCollaboration).filter(AgentCollaboration.run_id == self.run.id).one()
        self.assertEqual(handoff.data["eventType"], "aiops_readiness_blocked")
        self.assertEqual(handoff.data["toolName"], "write_tool")

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

        result = await service.approve(self.run.id, self.approval.id, True, "同意", self.approver)

        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["verification"]["toolName"], "api_health_check")
        self.assertEqual(result["verification"]["status"], "success")
        self.assertEqual(result["verification"]["successCount"], 3)
        self.assertEqual(result["verification"]["total"], 3)
        self.assertTrue(toolkit.called)
        self.assertTrue(toolkit.read_called)
        self.assertEqual(toolkit.read_calls, ["api_health_check", "metric_trend:cpu_percent", "metric_trend:memory_percent"])
        verification_calls = (
            self.db.query(AgentToolCall)
            .filter(AgentToolCall.run_id == self.run.id, AgentToolCall.approval_status == "not_required")
            .all()
        )
        self.assertEqual(len(verification_calls), 3)
        self.assertTrue(all(item.status == "success" for item in verification_calls))
        spans = self.db.query(TraceSpan).filter(TraceSpan.trace_id == self.trace.id, TraceSpan.operation == "verification").all()
        self.assertEqual(len(spans), 3)
        self.assertTrue(all(span.metadata_json["context"]["sourceTool"] == "compose_restart_service" for span in spans))
        self.assertTrue(all(span.metadata_json["output"]["result"]["success"] for span in spans))

    async def test_post_verification_failure_records_handoff(self) -> None:
        """审批后只读验证失败时，应记录人工复核事件，避免误判修复完成。"""

        self.approval.tool_name = "compose_restart_service"
        self.approval.args = {"service": "ragent-api"}
        self.tool_call.tool_name = "compose_restart_service"
        self.tool_call.args = {"service": "ragent-api"}
        self.db.commit()
        service = OpsAgentService(self.db)
        toolkit = FakeToolkit()
        toolkit.fail_metric = "memory_percent"
        service.toolkit = toolkit

        result = await service.approve(self.run.id, self.approval.id, True, "同意", self.approver)

        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["verification"]["status"], "partial")
        self.assertEqual(result["verification"]["successCount"], 2)
        self.assertEqual(result["verification"]["total"], 3)
        failed_call = (
            self.db.query(AgentToolCall)
            .filter(AgentToolCall.run_id == self.run.id, AgentToolCall.tool_name == "metric_trend", AgentToolCall.status == "failed")
            .one()
        )
        self.assertEqual(failed_call.error_message, "monitoring_query_failed")
        handoff = self.db.query(AgentCollaboration).filter(AgentCollaboration.run_id == self.run.id).one()
        self.assertEqual(handoff.from_agent, "verification")
        self.assertEqual(handoff.data["eventType"], "post_approval_verification_failed")
        self.assertEqual(handoff.data["toolName"], "metric_trend")
        self.assertTrue(handoff.data["rollbackRequired"])
        self.assertTrue(handoff.data["approvalRequired"])
        self.assertTrue(any("回滚" in item for item in handoff.data["rollbackCandidates"]))

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

    def test_persist_failed_observation_records_handoff(self) -> None:
        """工具执行失败时应记录人工接管协作事件，供审计复盘查询。"""

        service = OpsAgentService(self.db)
        tool_event = {
            "type": "tool_call",
            "tool": "write_tool",
            "stepIndex": 0,
            "args": {"service": "api"},
            "status": "running",
        }
        service._persist_event(self.run, tool_event, self.user)
        observation = {
            "type": "observation",
            "agent": "executor",
            "tool": "write_tool",
            "stepIndex": 0,
            "durationMs": 3,
            "result": {"success": False, "summary": "执行失败", "error": "boom"},
        }

        service._persist_event(self.run, observation, self.user)

        row = self.db.query(AgentCollaboration).filter(AgentCollaboration.run_id == self.run.id).one()
        self.assertEqual(row.event_type, "handoff")
        self.assertEqual(row.to_agent, "human_sre")
        self.assertEqual(row.data["eventType"], "tool_failure")
        self.assertIn("人工复核", row.content)

    def test_audit_checkpoint_writes_trace_span(self) -> None:
        """审计检查点应写入 Trace，便于回放计划、执行和审批完整性。"""

        service = OpsAgentService(self.db)
        trace_service = TraceService(self.db)
        event = {
            "type": "audit_checkpoint",
            "agent": "audit",
            "status": "passed",
            "result": {
                "success": True,
                "summary": "审计检查完成",
                "data": {"metrics": {"plannedStepCount": 1}, "checks": [{"code": "plan_recorded", "status": "passed"}]},
            },
        }

        service._persist_trace_event(trace_service, self.trace.id, event)

        span = self.db.query(TraceSpan).filter(TraceSpan.trace_id == self.trace.id, TraceSpan.operation == "audit").one()
        self.assertEqual(span.metadata_json["context"]["agent"], "audit")
        self.assertEqual(span.metadata_json["output"]["result"]["data"]["metrics"]["plannedStepCount"], 1)

    def test_approval_required_records_handoff_and_run_detail(self) -> None:
        """高风险审批阻塞应进入人工接管审计，并在运行详情中返回。"""

        service = OpsAgentService(self.db)
        event = {
            "type": "approval_required",
            "agent": "executor",
            "tool": "compose_restart_service",
            "stepIndex": 0,
            "args": {"service": "ragent-api"},
            "riskLevel": "write",
        }

        service._persist_event(self.run, event, self.user)

        row = self.db.query(AgentCollaboration).filter(AgentCollaboration.run_id == self.run.id).one()
        self.assertEqual(row.event_type, "handoff")
        self.assertEqual(row.data["eventType"], "approval_required")
        self.assertEqual(row.data["toolName"], "compose_restart_service")
        detail = service.get_run(self.run.id)
        self.assertEqual(detail["collaborations"][0]["eventType"], "handoff")
        self.assertEqual(detail["collaborations"][0]["toAgent"], "human_sre")

    def test_stop_records_manual_handoff_and_run_detail(self) -> None:
        """管理员手动停止运维运行时，应记录人工接管审计事件。"""

        service = OpsAgentService(self.db)

        result = service.stop(self.run.id, self.user)

        self.assertEqual(result["status"], "stopped")
        self.db.refresh(self.run)
        self.assertEqual(self.run.status, "stopped")
        row = self.db.query(AgentCollaboration).filter(AgentCollaboration.run_id == self.run.id).one()
        self.assertEqual(row.event_type, "handoff")
        self.assertEqual(row.from_agent, "human_sre")
        self.assertEqual(row.data["eventType"], "manual_stop")
        self.assertEqual(row.data["operatorId"], self.user.id)
        self.assertEqual(row.data["previousStatus"], "running")
        self.assertEqual(row.data["requiredAction"], "human_takeover")
        detail = service.get_run(self.run.id)
        self.assertEqual(detail["collaborations"][0]["data"]["eventType"], "manual_stop")
        self.assertIn("手动停止", detail["collaborations"][0]["content"])

    def test_non_admin_cannot_stop_ops_run(self) -> None:
        """服务层应拒绝非管理员直接停止运维运行。"""

        service = OpsAgentService(self.db)

        with self.assertRaises(HTTPException) as context:
            service.stop(self.run.id, self.viewer)

        self.assertEqual(context.exception.status_code, 403)
        self.assertIn("管理员权限", context.exception.detail)
        self.db.refresh(self.run)
        self.assertEqual(self.run.status, "running")
        self.assertEqual(self.db.query(AgentCollaboration).filter(AgentCollaboration.run_id == self.run.id).count(), 0)

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

        await service.approve(self.run.id, self.approval.id, True, "同意", self.approver)
        toolkit.called = False

        with self.assertRaises(HTTPException) as context:
            await service.approve(self.run.id, self.approval.id, True, "再次同意", self.approver)

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
