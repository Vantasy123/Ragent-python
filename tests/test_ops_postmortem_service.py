from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers.ops_agent import router as ops_agent_router
from app.core.database import Base, get_db
from app.domain.models import AgentApproval, AgentCollaboration, AgentRun, AgentStep, AgentToolCall, TraceRun, TraceSpan, User
from app.services.dependencies import require_admin
from app.services.ops_postmortem_service import OpsPostmortemService


class OpsPostmortemServiceTest(unittest.TestCase):
    """验证运维 Agent 审计复盘报告。"""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(id="user-1", username="admin", nickname="管理员", password_hash="x", role="admin")
        self.approver = User(id="user-2", username="sre", nickname="值班 SRE", password_hash="x", role="admin")
        self.trace = TraceRun(id="trace-1", status="success", total_duration_ms=1200)
        self.run = AgentRun(id="run-1", trace_id=self.trace.id, user_id=self.user.id, message="重启后端服务", status="completed")
        self.step = AgentStep(
            run=self.run,
            step_index=0,
            title="申请重启服务",
            tool_name="compose_restart_service",
            status="blocked",
            assigned_agent="executor",
        )
        self.blocked_call = AgentToolCall(
            id="tool-call-1",
            run=self.run,
            tool_name="compose_restart_service",
            args={"service": "ragent-api"},
            status="success",
            risk_level="write",
            approval_status="approved",
            duration_ms=30,
            result={"success": True, "summary": "已重启"},
        )
        self.verification_call = AgentToolCall(
            id="tool-call-2",
            run=self.run,
            tool_name="api_health_check",
            args={},
            status="success",
            risk_level="read",
            approval_status="not_required",
            duration_ms=20,
            result={"success": True, "summary": "后端健康"},
        )
        self.alert_call = AgentToolCall(
            id="tool-call-3",
            run=self.run,
            tool_name="alert_correlations",
            args={},
            status="success",
            risk_level="read",
            approval_status="not_required",
            duration_ms=15,
            result={
                "success": True,
                "summary": "聚合 3 条活跃告警为 2 个告警组",
                "data": {"alertCount": 3, "groupCount": 2, "noiseReduction": 1},
            },
        )
        self.approval = AgentApproval(
            id="approval-1",
            run=self.run,
            tool_call_id=self.blocked_call.id,
            tool_name="compose_restart_service",
            args={"service": "ragent-api"},
            status="approved",
            requested_by=self.user.id,
            approved_by=self.approver.id,
            comment="同意",
        )
        self.handoff = AgentCollaboration(
            run=self.run,
            from_agent="executor",
            to_agent="human_sre",
            event_type="handoff",
            content="高风险工具 compose_restart_service 等待人工审批",
            data={"eventType": "approval_required", "toolName": "compose_restart_service", "riskLevel": "write"},
        )
        self.verification_span = TraceSpan(
            trace_id=self.trace.id,
            operation="verification",
            status="success",
            duration_ms=20,
            metadata_json={"context": {"agent": "verification", "toolName": "api_health_check", "sourceTool": "compose_restart_service"}},
        )
        self.audit_span = TraceSpan(
            trace_id=self.trace.id,
            operation="audit",
            status="success",
            duration_ms=5,
            metadata_json={
                "context": {"agent": "audit"},
                "output": {
                    "result": {
                        "success": True,
                        "summary": "审计检查完成：计划 1 步，工具结果 3/3，审批阻塞 1 项",
                        "data": {
                            "status": "passed",
                            "metrics": {
                                "plannedStepCount": 1,
                                "toolCallCount": 3,
                                "recordedToolResultCount": 3,
                                "blockedStepCount": 1,
                            },
                            "checks": [{"code": "plan_recorded", "status": "passed"}],
                        },
                    }
                },
            },
        )
        self.db.add_all(
            [
                self.user,
                self.approver,
                self.trace,
                self.run,
                self.step,
                self.blocked_call,
                self.verification_call,
                self.alert_call,
                self.approval,
                self.handoff,
                self.verification_span,
                self.audit_span,
            ]
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_build_postmortem_summarizes_timeline_and_compliance(self) -> None:
        """复盘报告应包含时间线、审批门禁、验证闭环和改进项。"""

        payload = OpsPostmortemService(self.db).build(self.run.id)

        self.assertEqual(payload["runId"], self.run.id)
        self.assertEqual(payload["metrics"]["approvalCount"], 1)
        self.assertEqual(payload["metrics"]["selfApprovedCount"], 0)
        self.assertEqual(payload["metrics"]["approvalSeparationRate"], 1)
        self.assertEqual(payload["metrics"]["manualTakeoverCount"], 0)
        self.assertEqual(payload["metrics"]["approvalRejectedHandoffCount"], 0)
        self.assertEqual(payload["metrics"]["writeToolCount"], 1)
        self.assertEqual(payload["metrics"]["mttrProxyMs"], 1200)
        self.assertEqual(payload["metrics"]["verificationCount"], 1)
        self.assertEqual(payload["metrics"]["verificationSuccessRate"], 1)
        self.assertEqual(payload["metrics"]["closedLoopCoverageRate"], 1)
        self.assertEqual(payload["metrics"]["alertCount"], 3)
        self.assertEqual(payload["metrics"]["alertGroupCount"], 2)
        self.assertEqual(payload["metrics"]["alertNoiseReductionCount"], 1)
        self.assertEqual(payload["metrics"]["alertNoiseReductionRate"], 0.3333)
        self.assertEqual(payload["metrics"]["auditCheckpointCount"], 1)
        self.assertEqual(payload["metrics"]["auditPlannedStepCount"], 1)
        self.assertEqual(payload["metrics"]["auditRecordedToolResultCount"], 3)
        self.assertTrue(any(item["eventType"] == "approval" for item in payload["timeline"]))
        self.assertTrue(any(item["eventType"] == "trace_verification" for item in payload["timeline"]))
        self.assertTrue(any(item["eventType"] == "trace_audit" for item in payload["timeline"]))
        checks = {item["code"]: item for item in payload["complianceChecks"]}
        self.assertEqual(checks["approval_gate"]["status"], "passed")
        self.assertEqual(checks["approval_separation"]["status"], "passed")
        self.assertEqual(checks["post_verification"]["status"], "passed")
        self.assertEqual(checks["post_verification_quality"]["status"], "passed")
        self.assertEqual(checks["rollback_path"]["status"], "passed")
        self.assertEqual(checks["manual_handoff"]["status"], "passed")
        self.assertEqual(checks["approval_rejection_handoff"]["status"], "passed")
        self.assertEqual(checks["audit_checkpoint"]["status"], "passed")
        self.assertIn("审计闭环完整", payload["summary"])
        self.assertIn("0 个回滚建议", payload["summary"])
        self.assertIn("1 个审计检查点", payload["summary"])
        self.assertIn("告警降噪 1 条", payload["summary"])
        self.assertIn("0 次手动接管", payload["summary"])
        self.assertIn("0 次审批拒绝接管", payload["summary"])
        self.assertIn("0 次同人审批", payload["summary"])
        self.assertTrue(payload["improvementActions"])

    def test_build_postmortem_flags_self_approved_write_operation(self) -> None:
        """申请人本人通过审批时，复盘应标记职责分离风险。"""

        self.approval.approved_by = self.user.id
        self.db.commit()

        payload = OpsPostmortemService(self.db).build(self.run.id)
        checks = {item["code"]: item for item in payload["complianceChecks"]}

        self.assertEqual(checks["approval_separation"]["status"], "failed")
        self.assertEqual(checks["approval_separation"]["severity"], "warning")
        self.assertEqual(payload["metrics"]["selfApprovedCount"], 1)
        self.assertEqual(payload["metrics"]["approvalSeparationRate"], 0)
        self.assertIn("1 次同人审批", payload["summary"])
        self.assertTrue(any("四眼审批" in item or "二次复核" in item for item in payload["improvementActions"]))

    def test_build_postmortem_flags_unapproved_write_tool(self) -> None:
        """写操作如果绕过审批，应在复盘中标记为 critical 风险。"""

        self.blocked_call.approval_status = "not_required"
        self.db.commit()

        payload = OpsPostmortemService(self.db).build(self.run.id)
        checks = {item["code"]: item for item in payload["complianceChecks"]}

        self.assertEqual(checks["approval_gate"]["status"], "failed")
        self.assertEqual(checks["approval_gate"]["severity"], "critical")
        self.assertTrue(any("审批策略" in item for item in payload["improvementActions"]))

    def test_build_postmortem_flags_failed_post_verification(self) -> None:
        """审批后验证失败时，复盘应标记验证质量风险并给出改进动作。"""

        self.verification_span.status = "error"
        rollback_handoff = AgentCollaboration(
            run=self.run,
            from_agent="verification",
            to_agent="human_sre",
            event_type="handoff",
            content="审批后验证失败，需要评估回滚",
            data={
                "eventType": "post_approval_verification_failed",
                "rollbackRequired": True,
                "rollbackCandidates": ["按 Runbook 回滚到上一稳定版本"],
                "approvalRequired": True,
            },
        )
        self.db.add(rollback_handoff)
        self.db.commit()

        payload = OpsPostmortemService(self.db).build(self.run.id)
        checks = {item["code"]: item for item in payload["complianceChecks"]}

        self.assertEqual(checks["post_verification_quality"]["status"], "failed")
        self.assertEqual(checks["post_verification_quality"]["severity"], "warning")
        self.assertEqual(checks["rollback_path"]["status"], "passed")
        self.assertEqual(payload["metrics"]["verificationSuccessRate"], 0)
        self.assertEqual(payload["metrics"]["rollbackRecommendationCount"], 1)
        self.assertTrue(any("验证失败" in item for item in payload["improvementActions"]))

    def test_build_postmortem_flags_missing_rollback_path_after_failed_verification(self) -> None:
        """验证失败但没有回滚候选时，复盘应标记回滚路径风险。"""

        self.verification_span.status = "error"
        self.db.commit()

        payload = OpsPostmortemService(self.db).build(self.run.id)
        checks = {item["code"]: item for item in payload["complianceChecks"]}

        self.assertEqual(checks["rollback_path"]["status"], "failed")
        self.assertEqual(checks["rollback_path"]["severity"], "warning")
        self.assertEqual(payload["metrics"]["rollbackRecommendationCount"], 0)
        self.assertTrue(any("回滚候选" in item for item in payload["improvementActions"]))

    def test_build_postmortem_flags_missing_audit_checkpoint(self) -> None:
        """缺少审计 Agent 检查点时，复盘应标记审计闭环风险。"""

        self.db.delete(self.audit_span)
        self.db.commit()

        payload = OpsPostmortemService(self.db).build(self.run.id)
        checks = {item["code"]: item for item in payload["complianceChecks"]}

        self.assertEqual(checks["audit_checkpoint"]["status"], "failed")
        self.assertEqual(checks["audit_checkpoint"]["severity"], "warning")
        self.assertEqual(payload["metrics"]["auditCheckpointCount"], 0)
        self.assertTrue(any("audit_checkpoint" in item for item in payload["improvementActions"]))

    def test_build_postmortem_tracks_manual_stop_handoff(self) -> None:
        """停止态运行应能在复盘中追踪 manual_stop 人工接管事件。"""

        self.run.status = "stopped"
        manual_handoff = AgentCollaboration(
            run=self.run,
            from_agent="human_sre",
            to_agent="human_sre",
            event_type="handoff",
            content="管理员手动停止运维运行，后续由人工接管",
            data={
                "eventType": "manual_stop",
                "operatorId": self.user.id,
                "operatorName": self.user.username,
                "previousStatus": "running",
                "requiredAction": "human_takeover",
            },
        )
        self.db.add(manual_handoff)
        self.db.commit()

        payload = OpsPostmortemService(self.db).build(self.run.id)
        checks = {item["code"]: item for item in payload["complianceChecks"]}

        self.assertEqual(checks["manual_handoff"]["status"], "passed")
        self.assertEqual(payload["metrics"]["manualTakeoverCount"], 1)
        self.assertTrue(any(item["eventType"] == "handoff" and item["status"] == "manual_stop" for item in payload["timeline"]))
        self.assertIn("1 次手动接管", payload["summary"])

    def test_build_postmortem_flags_stopped_run_without_manual_handoff(self) -> None:
        """停止态运行如果缺少 manual_stop，应在复盘中暴露人工接管审计缺口。"""

        self.run.status = "stopped"
        self.db.commit()

        payload = OpsPostmortemService(self.db).build(self.run.id)
        checks = {item["code"]: item for item in payload["complianceChecks"]}

        self.assertEqual(checks["manual_handoff"]["status"], "failed")
        self.assertEqual(checks["manual_handoff"]["severity"], "warning")
        self.assertEqual(payload["metrics"]["manualTakeoverCount"], 0)
        self.assertTrue(any("manual_stop" in item for item in payload["improvementActions"]))

    def test_build_postmortem_tracks_rejected_approval_handoff(self) -> None:
        """被拒绝审批应在复盘中追踪 approval_rejected 人工接管事件。"""

        self.approval.status = "rejected"
        self.approval.approved_by = self.approver.id
        self.approval.comment = "风险过高"
        self.blocked_call.status = "blocked"
        self.blocked_call.approval_status = "rejected"
        rejection_handoff = AgentCollaboration(
            run=self.run,
            from_agent="approval",
            to_agent="human_sre",
            event_type="handoff",
            content="审批人拒绝高风险工具，后续由人工复核或改写方案",
            data={
                "eventType": "approval_rejected",
                "toolName": "compose_restart_service",
                "approvalId": self.approval.id,
                "toolCallId": self.blocked_call.id,
                "riskLevel": "write",
                "approvedBy": self.approver.id,
                "requiredAction": "revise_plan_or_human_takeover",
            },
        )
        self.db.add(rejection_handoff)
        self.db.commit()

        payload = OpsPostmortemService(self.db).build(self.run.id)
        checks = {item["code"]: item for item in payload["complianceChecks"]}

        self.assertEqual(checks["approval_rejection_handoff"]["status"], "passed")
        self.assertEqual(payload["metrics"]["rejectedCount"], 1)
        self.assertEqual(payload["metrics"]["approvalRejectedHandoffCount"], 1)
        self.assertTrue(any(item["eventType"] == "handoff" and item["status"] == "approval_rejected" for item in payload["timeline"]))
        self.assertIn("1 次审批拒绝接管", payload["summary"])
        self.assertTrue(any("低风险替代步骤" in item for item in payload["improvementActions"]))

    def test_build_postmortem_flags_rejected_approval_without_handoff(self) -> None:
        """被拒绝审批如果缺少接管事件，应在复盘中暴露方案改写缺口。"""

        self.approval.status = "rejected"
        self.approval.approved_by = self.approver.id
        self.blocked_call.status = "blocked"
        self.blocked_call.approval_status = "rejected"
        self.db.commit()

        payload = OpsPostmortemService(self.db).build(self.run.id)
        checks = {item["code"]: item for item in payload["complianceChecks"]}

        self.assertEqual(checks["approval_rejection_handoff"]["status"], "failed")
        self.assertEqual(checks["approval_rejection_handoff"]["severity"], "warning")
        self.assertEqual(payload["metrics"]["approvalRejectedHandoffCount"], 0)
        self.assertTrue(any("approval_rejected" in item for item in payload["improvementActions"]))

    def test_postmortem_router_returns_admin_payload(self) -> None:
        """复盘接口应向管理员返回同一结构化报告。"""

        app = FastAPI()
        app.include_router(ops_agent_router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[require_admin] = lambda: self.user

        response = TestClient(app).get(f"/agent/ops/runs/{self.run.id}/postmortem")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["code"], 200)
        self.assertEqual(body["data"]["runId"], self.run.id)
        self.assertIn("complianceChecks", body["data"])


if __name__ == "__main__":
    unittest.main()
