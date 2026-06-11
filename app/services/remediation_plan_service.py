"""修复方案与风险评估服务，把诊断证据转换为可审批的执行闭环。"""

from __future__ import annotations

from typing import Any


class RemediationPlanService:
    """根据 RCA 线索、影响面和建议动作生成保守的修复/回滚/验证计划。"""

    HIGH_RISK_KEYWORDS = ("重启", "restart", "回滚", "rollback", "删除", "delete", "扩缩容", "scale", "切流", "failover", "执行", "变更")
    MEDIUM_RISK_KEYWORDS = ("发布", "deploy", "release", "配置", "config", "云控制台", "安全组", "配额", "连接池")
    READ_ONLY_KEYWORDS = ("查看", "查询", "核对", "验证", "检查", "打开", "关联", "检索", "观测", "确认")

    def build_plan(
        self,
        task: str,
        facts: list[str] | None = None,
        impact: list[str] | None = None,
        rca_hints: list[str] | None = None,
        recommended_actions: list[str] | None = None,
        rollback_candidates: list[str] | None = None,
        handoff_actions: list[str] | None = None,
        data_gaps: list[str] | None = None,
    ) -> dict[str, Any]:
        """生成结构化修复方案；所有写操作都只给出审批门禁，不直接执行。"""

        facts = facts or []
        impact = impact or []
        rca_hints = self._deduplicate(rca_hints or [])
        recommended_actions = self._deduplicate(recommended_actions or [])
        rollback_candidates = self._deduplicate(rollback_candidates or [])
        handoff_actions = self._deduplicate(handoff_actions or [])
        data_gaps = self._deduplicate(data_gaps or [])

        stabilize_actions = self._stabilize_actions(recommended_actions, rca_hints, data_gaps)
        repair_actions = self._repair_actions(task, recommended_actions, rca_hints)
        rollback_plan = self._rollback_plan(rollback_candidates, rca_hints)
        verification_plan = self._verification_plan(impact, recommended_actions, rollback_plan)
        risk_assessment = self._risk_assessment(repair_actions, rollback_plan, rca_hints, data_gaps)
        approval_gates = self._approval_gates(repair_actions, rollback_plan, risk_assessment)
        automation_candidates = self._automation_candidates(stabilize_actions, recommended_actions)
        handoff_criteria = self._handoff_criteria(handoff_actions, risk_assessment, data_gaps)

        return {
            "summary": self._summary(risk_assessment, repair_actions, rollback_plan),
            "stabilizeActions": stabilize_actions,
            "repairActions": repair_actions,
            "rollbackPlan": rollback_plan,
            "verificationPlan": verification_plan,
            "riskAssessment": risk_assessment,
            "approvalGates": approval_gates,
            "automationCandidates": automation_candidates,
            "handoffCriteria": handoff_criteria,
            "evidenceCount": len(facts),
        }

    def _stabilize_actions(self, recommended_actions: list[str], rca_hints: list[str], data_gaps: list[str]) -> list[str]:
        """优先生成只读止血动作，避免在证据不足时直接写操作。"""

        actions = [item for item in recommended_actions if self._risk_level(item) == "low"]
        if not actions:
            actions.extend(["冻结自动写操作，仅继续采集日志、指标、Trace、告警和变更证据"])
        if data_gaps:
            actions.append("先补齐数据缺口，再评估是否进入自动化修复或回滚")
        if rca_hints:
            actions.append(f"围绕首要 RCA 线索复核：{rca_hints[0]}")
        return self._deduplicate(actions)[:5]

    def _repair_actions(self, task: str, recommended_actions: list[str], rca_hints: list[str]) -> list[dict[str, Any]]:
        """把建议动作转换为带风险等级和审批要求的修复步骤。"""

        source_actions = recommended_actions or rca_hints or [f"根据问题 {task} 继续收集证据并人工制定修复动作"]
        steps: list[dict[str, Any]] = []
        for index, action in enumerate(source_actions[:6], start=1):
            risk = self._risk_level(action)
            steps.append(
                {
                    "step": index,
                    "action": action,
                    "riskLevel": risk,
                    "requiresApproval": risk in {"medium", "high"},
                    "reason": self._risk_reason(action, risk),
                }
            )
        return steps

    def _rollback_plan(self, rollback_candidates: list[str], rca_hints: list[str]) -> list[dict[str, Any]]:
        """生成回滚计划；回滚统一视为高风险审批动作。"""

        candidates = rollback_candidates[:5]
        if not candidates and any("变更" in hint or "发布" in hint or "release" in hint.lower() for hint in rca_hints):
            candidates = ["若确认近期发布引入故障，按服务 Runbook 执行版本回滚或流量切回上一稳定版本"]
        return [
            {
                "action": item,
                "riskLevel": "high",
                "requiresApproval": True,
                "reason": "回滚会改变生产状态，必须确认影响面、依赖服务和恢复窗口",
            }
            for item in candidates
        ]

    def _verification_plan(self, impact: list[str], recommended_actions: list[str], rollback_plan: list[dict[str, Any]]) -> list[str]:
        """生成执行后验证步骤，保证修复不是只执行不闭环。"""

        checks = []
        for item in impact[:3]:
            checks.append(f"验证影响面恢复：{item}")
        checks.extend(action for action in recommended_actions if "验证" in action or "健康" in action or "检查" in action)
        if rollback_plan:
            checks.append("回滚后对比告警状态、核心指标、错误率、Trace 慢 span 和关键业务请求")
        if not checks:
            checks.append("修复后重新采集告警、健康检查、指标趋势和日志错误模式，确认症状消失")
        return self._deduplicate(checks)[:6]

    def _risk_assessment(
        self,
        repair_actions: list[dict[str, Any]],
        rollback_plan: list[dict[str, Any]],
        rca_hints: list[str],
        data_gaps: list[str],
    ) -> list[dict[str, str]]:
        """汇总风险因素，供审批前判断。"""

        risks: list[dict[str, str]] = []
        if any(item.get("riskLevel") == "high" for item in [*repair_actions, *rollback_plan]):
            risks.append({"level": "high", "item": "包含重启、回滚、切流或生产变更动作，必须人工审批后执行"})
        if any(item.get("riskLevel") == "medium" for item in repair_actions):
            risks.append({"level": "medium", "item": "包含配置、发布、云资源或依赖调整，需要 SRE 复核影响面"})
        if data_gaps:
            risks.append({"level": "medium", "item": f"存在 {len(data_gaps)} 个数据缺口，自动修复置信度不足"})
        if not rca_hints:
            risks.append({"level": "medium", "item": "缺少明确 RCA 线索，不建议直接执行写操作"})
        if not risks:
            risks.append({"level": "low", "item": "当前建议以只读核对和验证为主，可自动执行只读工具"})
        return risks

    def _approval_gates(
        self,
        repair_actions: list[dict[str, Any]],
        rollback_plan: list[dict[str, Any]],
        risk_assessment: list[dict[str, str]],
    ) -> list[str]:
        """生成审批门禁说明，和现有 approval_required 事件保持一致。"""

        gates: list[str] = []
        gated_actions = [item["action"] for item in [*repair_actions, *rollback_plan] if item.get("requiresApproval")]
        for action in gated_actions[:5]:
            gates.append(f"审批后才允许执行：{action}")
        if any(item.get("level") == "high" for item in risk_assessment):
            gates.append("高风险审批需确认回滚窗口、负责人、影响面、验证指标和人工接管方式")
        if not gates:
            gates.append("当前无写操作审批门禁，仅允许继续执行只读验证工具")
        return self._deduplicate(gates)

    def _automation_candidates(self, stabilize_actions: list[str], recommended_actions: list[str]) -> list[str]:
        """识别可自动化的只读动作，写操作仍交给审批。"""

        candidates = []
        for action in [*stabilize_actions, *recommended_actions]:
            if self._risk_level(action) == "low":
                candidates.append(action)
        return self._deduplicate(candidates)[:5] or ["自动执行只读健康检查、指标查询、日志分析和 Trace 复核"]

    def _handoff_criteria(
        self,
        handoff_actions: list[str],
        risk_assessment: list[dict[str, str]],
        data_gaps: list[str],
    ) -> list[str]:
        """生成 SRE 人工接管条件。"""

        criteria = list(handoff_actions)
        if any(item.get("level") == "high" for item in risk_assessment):
            criteria.append("出现高风险生产变更或回滚动作时，必须由 SRE 接管审批")
        if data_gaps:
            criteria.append("关键数据源缺失导致 RCA 置信度不足时，暂停自动修复并人工复核")
        return self._deduplicate(criteria)[:5]

    def _risk_level(self, action: str) -> str:
        """按关键词给动作分级，保持可解释和可审计。"""

        text = str(action or "").lower()
        if any(keyword.lower() in text for keyword in self.HIGH_RISK_KEYWORDS):
            return "high"
        if any(keyword.lower() in text for keyword in self.MEDIUM_RISK_KEYWORDS):
            return "medium"
        return "low"

    def _risk_reason(self, action: str, risk: str) -> str:
        """解释动作为什么被划为对应风险等级。"""

        if risk == "high":
            return "动作可能改变生产状态或触发回滚，必须走人工审批"
        if risk == "medium":
            return "动作涉及配置、发布、云资源或依赖复核，需要负责人确认"
        if any(keyword in str(action) for keyword in self.READ_ONLY_KEYWORDS):
            return "动作以只读核对或验证为主，可由 Agent 自动执行"
        return "未发现写操作关键词，默认按低风险只读建议处理"

    def _summary(self, risk_assessment: list[dict[str, str]], repair_actions: list[dict[str, Any]], rollback_plan: list[dict[str, Any]]) -> str:
        """生成一行计划摘要。"""

        highest = "low"
        if any(item.get("level") == "high" for item in risk_assessment):
            highest = "high"
        elif any(item.get("level") == "medium" for item in risk_assessment):
            highest = "medium"
        return f"生成 {len(repair_actions)} 个修复步骤、{len(rollback_plan)} 个回滚候选，最高风险 {highest}"

    def _deduplicate(self, items: list[str]) -> list[str]:
        """按原顺序去重文本列表。"""

        seen: set[str] = set()
        results: list[str] = []
        for item in items:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            results.append(text)
        return results
