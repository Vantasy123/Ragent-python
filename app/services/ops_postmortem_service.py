"""运维 Agent 审计复盘服务，把一次运行整理成可追溯的 SRE 复盘报告。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.time_utils import to_shanghai_iso
from app.domain.models import AgentApproval, AgentCollaboration, AgentRun, AgentStep, AgentToolCall, TraceRun, TraceSpan, User


class OpsPostmortemService:
    """基于已落库的运行、工具、审批、协作和 Trace 数据生成审计复盘。"""

    SENSITIVE_MARKERS = ("password", "token", "secret", "authorization", "apikey", "api_key", "ak", "sk")
    WRITE_RISK_LEVELS = {"write", "danger", "high"}

    def __init__(self, db: Session) -> None:
        self.db = db

    def build(self, run_id: str) -> dict[str, Any]:
        """生成一次运维运行的复盘报告，供审计页和事故复盘使用。"""

        run = self.db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="运行记录不存在")

        steps = self.db.query(AgentStep).filter(AgentStep.run_id == run.id).order_by(AgentStep.step_index.asc()).all()
        tool_calls = self.db.query(AgentToolCall).filter(AgentToolCall.run_id == run.id).order_by(AgentToolCall.created_at.asc()).all()
        approvals = self.db.query(AgentApproval).filter(AgentApproval.run_id == run.id).order_by(AgentApproval.created_at.asc()).all()
        collaborations = (
            self.db.query(AgentCollaboration).filter(AgentCollaboration.run_id == run.id).order_by(AgentCollaboration.created_at.asc()).all()
        )
        trace = self.db.query(TraceRun).filter(TraceRun.id == run.trace_id).first() if run.trace_id else None
        spans = self.db.query(TraceSpan).filter(TraceSpan.trace_id == run.trace_id).order_by(TraceSpan.created_at.asc()).all() if run.trace_id else []
        users = self._users_by_id({run.user_id or "", *[item.requested_by or "" for item in approvals], *[item.approved_by or "" for item in approvals]})

        timeline = self._timeline(run, steps, tool_calls, approvals, collaborations, spans, users)
        compliance = self._compliance_checks(tool_calls, approvals, collaborations, spans)
        metrics = self._metrics(run, steps, tool_calls, approvals, collaborations, trace)
        findings = self._findings(compliance, tool_calls, approvals, collaborations)
        improvements = self._improvements(compliance, metrics, findings)

        return {
            "runId": run.id,
            "traceId": run.trace_id,
            "message": run.message,
            "status": run.status,
            "operator": self._user_name(users.get(run.user_id or ""), run.user_id),
            "createdAt": to_shanghai_iso(run.created_at),
            "updatedAt": to_shanghai_iso(run.updated_at),
            "summary": self._summary(metrics, compliance),
            "metrics": metrics,
            "timeline": timeline,
            "complianceChecks": compliance,
            "findings": findings,
            "improvementActions": improvements,
            "finalReportExcerpt": (run.final_report or "")[:1200],
        }

    def _timeline(
        self,
        run: AgentRun,
        steps: list[AgentStep],
        tool_calls: list[AgentToolCall],
        approvals: list[AgentApproval],
        collaborations: list[AgentCollaboration],
        spans: list[TraceSpan],
        users: dict[str, User],
    ) -> list[dict[str, Any]]:
        """把多张审计表合并成统一时间线。"""

        events: list[dict[str, Any]] = [
            {
                "time": run.created_at,
                "eventType": "run_created",
                "actor": self._user_name(users.get(run.user_id or ""), run.user_id),
                "summary": f"创建运维 Agent 运行：{run.message}",
                "status": run.status,
                "riskLevel": "read",
            }
        ]
        for step in steps:
            events.append(
                {
                    "time": step.created_at,
                    "eventType": "plan_step",
                    "actor": step.assigned_agent or "planner",
                    "summary": f"计划步骤 {step.step_index + 1}：{step.title}",
                    "status": step.status,
                    "toolName": step.tool_name,
                    "riskLevel": "read",
                }
            )
        for call in tool_calls:
            events.append(
                {
                    "time": call.created_at,
                    "eventType": "tool_call",
                    "actor": "executor",
                    "summary": f"工具 {call.tool_name}：{call.status}",
                    "status": call.status,
                    "toolName": call.tool_name,
                    "riskLevel": call.risk_level,
                    "approvalStatus": call.approval_status,
                    "durationMs": call.duration_ms,
                }
            )
        for approval in approvals:
            events.append(
                {
                    "time": approval.decided_at or approval.created_at,
                    "eventType": "approval",
                    "actor": self._user_name(users.get(approval.approved_by or approval.requested_by or ""), approval.approved_by or approval.requested_by),
                    "summary": f"审批 {approval.tool_name}：{approval.status}",
                    "status": approval.status,
                    "toolName": approval.tool_name,
                    "riskLevel": "write",
                    "comment": approval.comment or "",
                }
            )
        for item in collaborations:
            events.append(
                {
                    "time": item.created_at,
                    "eventType": item.event_type,
                    "actor": item.from_agent,
                    "summary": item.content,
                    "status": item.data.get("eventType") if isinstance(item.data, dict) else item.event_type,
                    "toAgent": item.to_agent,
                    "riskLevel": item.data.get("riskLevel") if isinstance(item.data, dict) else "",
                }
            )
        for span in spans:
            if span.operation not in {"verification", "approval_required"}:
                continue
            events.append(
                {
                    "time": span.created_at,
                    "eventType": f"trace_{span.operation}",
                    "actor": (span.metadata_json or {}).get("context", {}).get("agent", "trace"),
                    "summary": f"Trace {span.operation}：{span.status}",
                    "status": span.status,
                    "toolName": (span.metadata_json or {}).get("context", {}).get("toolName", ""),
                    "riskLevel": (span.metadata_json or {}).get("context", {}).get("riskLevel", ""),
                    "durationMs": span.duration_ms,
                }
            )
        return [self._serialize_event(item) for item in sorted(events, key=lambda item: item.get("time") or datetime.min)]

    def _compliance_checks(
        self,
        tool_calls: list[AgentToolCall],
        approvals: list[AgentApproval],
        collaborations: list[AgentCollaboration],
        spans: list[TraceSpan],
    ) -> list[dict[str, str]]:
        """检查审批门禁、验证闭环、人工接管和敏感信息脱敏是否满足要求。"""

        checks: list[dict[str, str]] = []
        risky_calls = [item for item in tool_calls if item.risk_level in self.WRITE_RISK_LEVELS or item.approval_status in {"pending", "approved", "rejected"}]
        risky_without_gate = [item for item in risky_calls if item.status == "success" and item.approval_status != "approved"]
        checks.append(
            self._check(
                "approval_gate",
                not risky_without_gate,
                "高风险工具均经过审批后执行" if not risky_without_gate else f"{len(risky_without_gate)} 个高风险工具缺少 approved 审批状态",
                "critical",
            )
        )

        approved = [item for item in approvals if item.status == "approved"]
        verification_exists = any(item.operation == "verification" and item.status == "success" for item in spans) or any(
            item.approval_status == "not_required" and item.status == "success" and item.tool_name.endswith("_check") for item in tool_calls
        )
        checks.append(
            self._check(
                "post_verification",
                not approved or verification_exists,
                "审批后的写操作已记录只读验证" if not approved or verification_exists else "审批后的写操作缺少只读验证记录",
                "warning",
            )
        )

        blocked_or_failed = [item for item in tool_calls if item.status in {"blocked", "failed"}]
        handoff_exists = any(item.event_type == "handoff" for item in collaborations)
        checks.append(
            self._check(
                "human_handoff",
                not blocked_or_failed or handoff_exists,
                "阻塞或失败场景已记录人工接管" if not blocked_or_failed or handoff_exists else "阻塞或失败工具缺少人工接管记录",
                "warning",
            )
        )

        unsafe_payloads = [item.tool_name for item in tool_calls if self._contains_unredacted_sensitive(item.args) or self._contains_unredacted_sensitive(item.result)]
        checks.append(
            self._check(
                "sensitive_redaction",
                not unsafe_payloads,
                "工具入参和结果未发现未脱敏敏感信息" if not unsafe_payloads else f"疑似未脱敏工具：{', '.join(unsafe_payloads[:3])}",
                "critical",
            )
        )
        return checks

    def _metrics(
        self,
        run: AgentRun,
        steps: list[AgentStep],
        tool_calls: list[AgentToolCall],
        approvals: list[AgentApproval],
        collaborations: list[AgentCollaboration],
        trace: TraceRun | None,
    ) -> dict[str, Any]:
        """生成复盘指标，作为 MTTR 和自动化率的代理数据。"""

        duration_ms = trace.total_duration_ms if trace and trace.total_duration_ms else self._duration_ms(run.created_at, run.updated_at)
        read_calls = [item for item in tool_calls if item.risk_level == "read"]
        write_calls = [item for item in tool_calls if item.risk_level in self.WRITE_RISK_LEVELS]
        successful_tools = [item for item in tool_calls if item.status == "success"]
        return {
            "durationMs": duration_ms,
            "stepCount": len(steps),
            "toolCallCount": len(tool_calls),
            "successfulToolCallCount": len(successful_tools),
            "approvalCount": len(approvals),
            "approvedCount": len([item for item in approvals if item.status == "approved"]),
            "rejectedCount": len([item for item in approvals if item.status == "rejected"]),
            "handoffCount": len([item for item in collaborations if item.event_type == "handoff"]),
            "readOnlyAutomationRate": round(len(read_calls) / len(tool_calls), 4) if tool_calls else 0,
            "writeToolCount": len(write_calls),
        }

    def _findings(
        self,
        compliance: list[dict[str, str]],
        tool_calls: list[AgentToolCall],
        approvals: list[AgentApproval],
        collaborations: list[AgentCollaboration],
    ) -> list[str]:
        """生成审计结论，优先暴露不合规和高风险点。"""

        findings: list[str] = []
        for item in compliance:
            if item["status"] != "passed":
                findings.append(f"{item['severity']}：{item['message']}")
        if approvals:
            findings.append(f"本次运行产生 {len(approvals)} 条审批记录，审批状态可追溯")
        if any(item.event_type == "handoff" for item in collaborations):
            findings.append("本次运行包含人工接管事件，适合纳入事故复盘")
        if tool_calls and not findings:
            findings.append("本次运行工具调用、审批和验证记录完整，未发现明显审计缺口")
        return findings or ["暂无工具和审批记录，仅能复盘运行基础信息"]

    def _improvements(self, compliance: list[dict[str, str]], metrics: dict[str, Any], findings: list[str]) -> list[str]:
        """根据复盘结论生成改进项。"""

        actions: list[str] = []
        failed_codes = {item["code"] for item in compliance if item["status"] != "passed"}
        if "approval_gate" in failed_codes:
            actions.append("修正工具风险等级或审批策略，确保写操作不能绕过审批")
        if "post_verification" in failed_codes:
            actions.append("为所有写操作补充执行后只读验证工具，形成执行-验证闭环")
        if "human_handoff" in failed_codes:
            actions.append("工具失败或阻塞时自动写入人工接管事件，便于 SRE 追溯")
        if "sensitive_redaction" in failed_codes:
            actions.append("扩大敏感字段脱敏规则，重新检查工具入参和结果审计副本")
        if metrics.get("handoffCount", 0) > 0:
            actions.append("把人工接管原因沉淀为 Runbook 或自动化只读诊断步骤")
        if not actions:
            actions.append("持续沉淀高频故障的 Runbook、验证指标和审批模板，降低后续 MTTR")
        return actions

    def _summary(self, metrics: dict[str, Any], compliance: list[dict[str, str]]) -> str:
        """生成复盘摘要。"""

        failed = [item for item in compliance if item["status"] != "passed"]
        status = "存在审计风险" if failed else "审计闭环完整"
        return (
            f"{status}：执行 {metrics['stepCount']} 个步骤、{metrics['toolCallCount']} 次工具调用、"
            f"{metrics['approvalCount']} 次审批、{metrics['handoffCount']} 次人工接管"
        )

    def _users_by_id(self, user_ids: set[str]) -> dict[str, User]:
        """批量读取用户，避免时间线序列化时反复查询。"""

        ids = {item for item in user_ids if item}
        if not ids:
            return {}
        return {row.id: row for row in self.db.query(User).filter(User.id.in_(ids)).all()}

    def _check(self, code: str, passed: bool, message: str, severity: str) -> dict[str, str]:
        """构造统一合规检查项。"""

        return {"code": code, "status": "passed" if passed else "failed", "severity": severity, "message": message}

    def _serialize_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """序列化时间线事件，隐藏 datetime 对象。"""

        return {**event, "time": to_shanghai_iso(event.get("time"))}

    def _duration_ms(self, started: datetime | None, ended: datetime | None) -> int:
        """根据运行开始和更新时间估算耗时。"""

        if not started or not ended:
            return 0
        return max(0, int((ended - started).total_seconds() * 1000))

    def _user_name(self, user: User | None, fallback: str | None) -> str:
        """获取用户展示名。"""

        if user:
            return user.username or user.nickname or user.id
        return fallback or "system"

    def _contains_unredacted_sensitive(self, value: Any) -> bool:
        """粗粒度检查审计 payload 是否含未脱敏敏感字段。"""

        if isinstance(value, dict):
            for key, item in value.items():
                key_text = str(key).lower()
                if any(marker in key_text for marker in self.SENSITIVE_MARKERS):
                    text = str(item)
                    if text and text != "<redacted>":
                        return True
                if self._contains_unredacted_sensitive(item):
                    return True
            return False
        if isinstance(value, list):
            return any(self._contains_unredacted_sensitive(item) for item in value)
        return False
