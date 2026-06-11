from __future__ import annotations

from app.services.remediation_plan_service import RemediationPlanService


def test_build_plan_marks_restart_and_rollback_as_approval_gated() -> None:
    """重启和回滚类动作必须被标记为高风险审批动作。"""

    plan = RemediationPlanService().build_plan(
        task="订单服务故障",
        facts=["- 订单服务告警"],
        impact=["受影响服务：order-api"],
        rca_hints=["近期发布后错误率升高"],
        recommended_actions=["查看 order-api 最近日志", "重启 order-api 服务"],
        rollback_candidates=["如确认变更导致故障，回滚到上一稳定版本"],
    )

    assert plan["summary"].startswith("生成")
    assert any(item["action"] == "重启 order-api 服务" and item["riskLevel"] == "high" for item in plan["repairActions"])
    assert all(item["requiresApproval"] for item in plan["rollbackPlan"])
    assert any("审批后才允许执行" in item for item in plan["approvalGates"])
    assert any("告警状态" in item or "影响面恢复" in item for item in plan["verificationPlan"])


def test_build_plan_keeps_readonly_actions_automatable() -> None:
    """只读核对和验证动作应进入自动化候选，不需要审批。"""

    plan = RemediationPlanService().build_plan(
        task="接口慢",
        rca_hints=["Trace 慢 span 指向 llm"],
        recommended_actions=["查看 Trace trace-1", "验证后端健康检查"],
    )

    assert all(not item["requiresApproval"] for item in plan["repairActions"])
    assert any("查看 Trace" in item for item in plan["automationCandidates"])
    assert plan["riskAssessment"][0]["level"] == "low"
