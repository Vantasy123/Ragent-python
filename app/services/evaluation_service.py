"""模块导读：本文件位于 app/services/evaluation_service.py，属于服务层。

主要职责：承接路由层请求，组织数据库、缓存、Trace、Agent 和外部组件完成业务流程。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

from statistics import median
from typing import Any

from sqlalchemy.orm import Session

from app.core.time_utils import to_shanghai_iso
from app.domain.models import (
    ConversationMessage,
    EvaluationIssue,
    EvaluationMetric,
    EvaluationRun,
    MessageFeedback,
    TraceRun,
    TraceSpan,
)


def _metadata(value: dict[str, Any] | None) -> dict[str, Any]:
    """_metadata 函数：计算或整理一段辅助数据，让主流程保持清晰。"""
    value = value or {}
    if set(value.keys()) == {"metadata"} and isinstance(value["metadata"], dict):
        return value["metadata"]
    return value


class EvaluationService:
    """EvaluationService 服务类：集中处理一类业务流程，让路由层不需要直接操作数据库、缓存或外部组件。"""
    def __init__(self, db: Session):
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
        self.db = db

    def evaluate_trace(self, trace_id: str) -> EvaluationRun:
        """evaluate_trace 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        trace = self.db.query(TraceRun).filter(TraceRun.id == trace_id).first()
        if not trace:
            raise ValueError("Trace not found")

        for old_run in list(trace.evaluation_runs):
            self.db.delete(old_run)
        self.db.flush()

        assistant_message = self._assistant_message_for_trace(trace)
        run = EvaluationRun(
            trace_id=trace.id,
            conversation_id=trace.session_id,
            message_id=assistant_message.id if assistant_message else None,
            status="completed",
        )
        self.db.add(run)
        self.db.flush()

        metrics: list[EvaluationMetric] = []
        issues: list[EvaluationIssue] = []
        metrics.extend(self._outcome_metrics(run, trace, assistant_message, issues))
        metrics.extend(self._process_metrics(run, trace, issues))
        metrics.extend(self._tool_metrics(run, trace, issues))
        metrics.extend(self._system_metrics(run, trace, issues))

        run.overall_score = round(sum(metric.score for metric in metrics) / max(len(metrics), 1), 4)
        run.summary = self._summary(run.overall_score, issues)
        self.db.add_all(metrics)
        self.db.add_all(issues)
        self.db.commit()
        self.db.refresh(run)
        return run

    def latest_for_trace(self, trace_id: str) -> EvaluationRun | None:
        """latest_for_trace 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        return (
            self.db.query(EvaluationRun)
            .filter(EvaluationRun.trace_id == trace_id)
            .order_by(EvaluationRun.created_at.desc())
            .first()
        )

    def ensure_evaluated(self, trace_id: str) -> EvaluationRun | None:
        """ensure_evaluated 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        existing = self.latest_for_trace(trace_id)
        if existing:
            return existing
        try:
            return self.evaluate_trace(trace_id)
        except ValueError:
            return None

    def list_runs(self, page_no: int, page_size: int) -> tuple[list[EvaluationRun], int]:
        """list_runs 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
        query = self.db.query(EvaluationRun).order_by(EvaluationRun.created_at.desc())
        total = query.count()
        rows = query.offset((page_no - 1) * page_size).limit(page_size).all()
        return rows, total

    def list_issues(self, page_no: int, page_size: int, severity: str | None = None) -> tuple[list[EvaluationIssue], int]:
        """list_issues 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
        query = self.db.query(EvaluationIssue)
        if severity:
            query = query.filter(EvaluationIssue.severity == severity)
        query = query.order_by(EvaluationIssue.created_at.desc())
        total = query.count()
        rows = query.offset((page_no - 1) * page_size).limit(page_size).all()
        return rows, total

    def overview(self) -> dict[str, Any]:
        """overview 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
        runs = self.db.query(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(200).all()
        issues = self.db.query(EvaluationIssue).order_by(EvaluationIssue.created_at.desc()).limit(20).all()
        trace_runs = self.db.query(TraceRun).order_by(TraceRun.created_at.desc()).limit(200).all()
        feedback = self.db.query(MessageFeedback).all()

        scores = [run.overall_score for run in runs]
        durations = [run.total_duration_ms for run in trace_runs if run.total_duration_ms]
        likes = sum(1 for item in feedback if item.feedback_type in {"like", "upvote", "positive"})
        dislikes = sum(1 for item in feedback if item.feedback_type in {"dislike", "downvote", "negative"})

        return {
            "evaluationRuns": len(runs),
            "avgScore": round(sum(scores) / max(len(scores), 1), 4),
            "lowScoreRuns": sum(1 for score in scores if score < 0.7),
            "issueCount": self.db.query(EvaluationIssue).count(),
            "successRate": self._rate(sum(1 for run in trace_runs if run.status == "success"), len(trace_runs)),
            "feedbackSatisfactionRate": self._rate(likes, likes + dislikes),
            "p50TotalMs": self._percentile(durations, 0.5),
            "p95TotalMs": self._percentile(durations, 0.95),
            "recentIssues": [self.issue_to_dict(issue) for issue in issues],
        }

    def run_to_dict(self, run: EvaluationRun, include_details: bool = False) -> dict[str, Any]:
        """run_to_dict 函数：把内部对象转换成普通 dict，便于 JSON 序列化、接口返回或 Trace 记录。"""
        data: dict[str, Any] = {
            "id": run.id,
            "traceId": run.trace_id,
            "conversationId": run.conversation_id,
            "messageId": run.message_id,
            "status": run.status,
            "overallScore": run.overall_score,
            "summary": run.summary,
            "createdAt": to_shanghai_iso(run.created_at),
        }
        if include_details:
            data["metrics"] = [self.metric_to_dict(metric) for metric in run.metrics]
            data["issues"] = [self.issue_to_dict(issue) for issue in run.issues]
        return data

    @staticmethod
    def metric_to_dict(metric: EvaluationMetric) -> dict[str, Any]:
        """metric_to_dict 函数：把内部对象转换成普通 dict，便于 JSON 序列化、接口返回或 Trace 记录。"""
        return {
            "id": metric.id,
            "traceId": metric.trace_id,
            "dimension": metric.dimension,
            "metricKey": metric.metric_key,
            "score": metric.score,
            "reason": metric.reason,
            "evidence": metric.evidence,
            "createdAt": to_shanghai_iso(metric.created_at),
        }

    @staticmethod
    def issue_to_dict(issue: EvaluationIssue) -> dict[str, Any]:
        """issue_to_dict 函数：把内部对象转换成普通 dict，便于 JSON 序列化、接口返回或 Trace 记录。"""
        return {
            "id": issue.id,
            "traceId": issue.trace_id,
            "dimension": issue.dimension,
            "issueKey": issue.issue_key,
            "severity": issue.severity,
            "message": issue.message,
            "evidence": issue.evidence,
            "createdAt": to_shanghai_iso(issue.created_at),
        }

    def _assistant_message_for_trace(self, trace: TraceRun) -> ConversationMessage | None:
        """_assistant_message_for_trace 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        if not trace.session_id:
            return None
        rows = (
            self.db.query(ConversationMessage)
            .filter(ConversationMessage.conversation_id == trace.session_id, ConversationMessage.role == "assistant")
            .order_by(ConversationMessage.created_at.desc())
            .limit(20)
            .all()
        )
        for row in rows:
            if _metadata(row.meta_data).get("traceId") == trace.id:
                return row
        return rows[0] if rows else None

    def _outcome_metrics(
        self,
        run: EvaluationRun,
        trace: TraceRun,
        assistant_message: ConversationMessage | None,
        issues: list[EvaluationIssue],
    ) -> list[EvaluationMetric]:
        """_outcome_metrics 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        metrics: list[EvaluationMetric] = []
        answer = assistant_message.content if assistant_message else ""
        feedback_rows = (
            self.db.query(MessageFeedback).filter(MessageFeedback.message_id == assistant_message.id).all()
            if assistant_message
            else []
        )
        positive = sum(1 for row in feedback_rows if row.feedback_type in {"like", "upvote", "positive"})
        negative = sum(1 for row in feedback_rows if row.feedback_type in {"dislike", "downvote", "negative"})
        feedback_score = 0.5 if positive + negative == 0 else positive / (positive + negative)
        metrics.append(self._metric(run, "outcome", "user_feedback", feedback_score, "User feedback sentiment", {"positive": positive, "negative": negative}))

        answer_score = 1.0 if len(answer.strip()) >= 20 else 0.2
        metrics.append(self._metric(run, "outcome", "answer_non_empty", answer_score, "Assistant answer has usable length", {"length": len(answer)}))
        if answer_score < 0.7:
            issues.append(self._issue(run, "outcome", "empty_or_short_answer", "high", "Assistant answer is empty or too short", {"length": len(answer)}))

        retrieval_span = self._span(trace, "retrieval")
        retrieval_meta = _metadata(retrieval_span.metadata_json) if retrieval_span else {}
        source_count = len(retrieval_meta.get("sources") or [])
        source_score = 1.0 if source_count > 0 else 0.4
        metrics.append(self._metric(run, "outcome", "has_retrieval_source", source_score, "Answer has retrieved sources", {"sourceCount": source_count}))
        if source_count == 0:
            issues.append(self._issue(run, "outcome", "missing_sources", "medium", "RAG answer has no retrieved source metadata", retrieval_meta))
        return metrics

    def _process_metrics(self, run: EvaluationRun, trace: TraceRun, issues: list[EvaluationIssue]) -> list[EvaluationMetric]:
        """_process_metrics 函数：执行一个完整处理步骤，输入上下文并产出可追踪的结果。"""
        metrics: list[EvaluationMetric] = []
        required = ["intent_analysis", "query_rewrite", "retrieval", "generation"]
        spans_by_operation = {span.operation: span for span in trace.spans}
        present = sum(1 for operation in required if operation in spans_by_operation)
        success = sum(1 for operation in required if operation in spans_by_operation and spans_by_operation[operation].status == "success")
        metrics.append(self._metric(run, "process", "required_spans_present", present / len(required), "Required process spans exist", {"required": required, "present": list(spans_by_operation)}))
        metrics.append(self._metric(run, "process", "required_spans_success", success / len(required), "Required process spans succeeded", {"success": success, "requiredCount": len(required)}))
        for operation in required:
            span = spans_by_operation.get(operation)
            if not span:
                issues.append(self._issue(run, "process", f"{operation}_missing", "high", f"Missing required span: {operation}", {}))
            elif span.status != "success":
                issues.append(self._issue(run, "process", f"{operation}_failed", "high", span.error_message or f"{operation} failed", _metadata(span.metadata_json)))

        retrieval = spans_by_operation.get("retrieval")
        retrieval_meta = _metadata(retrieval.metadata_json) if retrieval else {}
        chunks = int(retrieval_meta.get("chunks") or 0)
        metrics.append(self._metric(run, "process", "retrieval_non_empty", 1.0 if chunks > 0 else 0.3, "Retrieval returned chunks", {"chunks": chunks}))
        if chunks == 0:
            issues.append(self._issue(run, "process", "retrieval_empty", "medium", "Retrieval returned zero chunks", retrieval_meta))
        return metrics

    def _tool_metrics(self, run: EvaluationRun, trace: TraceRun, issues: list[EvaluationIssue]) -> list[EvaluationMetric]:
        """_tool_metrics 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        tool_spans = [span for span in trace.spans if span.operation in {"tool_call", "action_call"} or span.operation.startswith("tool")]
        if not tool_spans:
            return [self._metric(run, "tool", "tool_not_required", 1.0, "No tool call was required or recorded", {})]

        success = sum(1 for span in tool_spans if span.status == "success")
        metrics = [self._metric(run, "tool", "tool_success_rate", success / len(tool_spans), "Tool spans succeeded", {"total": len(tool_spans), "success": success})]
        seen: set[str] = set()
        for span in tool_spans:
            meta = _metadata(span.metadata_json)
            tool_name = meta.get("toolName") or meta.get("tool_name") or meta.get("name") or span.operation
            args = meta.get("args") or meta.get("params") or {}
            signature = f"{tool_name}:{args}"
            if not tool_name:
                issues.append(self._issue(run, "tool", "unknown_tool", "high", "Tool span has no tool name", meta))
            if signature in seen:
                issues.append(self._issue(run, "tool", "duplicate_tool_call", "medium", "Repeated same tool call", meta))
            seen.add(signature)
            if span.status != "success":
                issues.append(self._issue(run, "tool", "tool_call_failed", "high", span.error_message or "Tool call failed", meta))
        return metrics

    def _system_metrics(self, run: EvaluationRun, trace: TraceRun, issues: list[EvaluationIssue]) -> list[EvaluationMetric]:
        """_system_metrics 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        metrics = [
            self._metric(run, "system", "trace_success", 1.0 if trace.status == "success" else 0.0, "Trace completed successfully", {"status": trace.status}),
            self._metric(run, "system", "total_latency", self._latency_score(trace.total_duration_ms), "Total trace latency score", {"totalDurationMs": trace.total_duration_ms}),
        ]
        if trace.status != "success":
            issues.append(self._issue(run, "system", "trace_failed", "high", "Trace run did not complete successfully", {"status": trace.status}))
        if trace.total_duration_ms > 15000:
            issues.append(self._issue(run, "system", "slow_trace", "medium", "Trace exceeded 15 seconds", {"totalDurationMs": trace.total_duration_ms}))
        return metrics

    def _metric(self, run: EvaluationRun, dimension: str, key: str, score: float, reason: str, evidence: dict[str, Any]) -> EvaluationMetric:
        """_metric 函数：计算或整理一段辅助数据，让主流程保持清晰。"""
        return EvaluationMetric(evaluation_run_id=run.id, trace_id=run.trace_id, dimension=dimension, metric_key=key, score=round(max(0.0, min(1.0, score)), 4), reason=reason, evidence=evidence)

    def _issue(self, run: EvaluationRun, dimension: str, key: str, severity: str, message: str, evidence: dict[str, Any]) -> EvaluationIssue:
        """_issue 函数：计算或整理一段辅助数据，让主流程保持清晰。"""
        return EvaluationIssue(evaluation_run_id=run.id, trace_id=run.trace_id, dimension=dimension, issue_key=key, severity=severity, message=message, evidence=evidence)

    @staticmethod
    def _span(trace: TraceRun, operation: str) -> TraceSpan | None:
        """_span 函数：计算或整理一段辅助数据，让主流程保持清晰。"""
        return next((span for span in trace.spans if span.operation == operation), None)

    @staticmethod
    def _summary(score: float, issues: list[EvaluationIssue]) -> str:
        """_summary 函数：计算或整理一段辅助数据，让主流程保持清晰。"""
        if not issues and score >= 0.85:
            return "Agent run passed rule-based evaluation."
        high = sum(1 for issue in issues if issue.severity == "high")
        return f"Agent run score={score:.2f}, issues={len(issues)}, highSeverity={high}."

    @staticmethod
    def _latency_score(duration_ms: int) -> float:
        """_latency_score 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        if duration_ms <= 0:
            return 0.5
        if duration_ms <= 5000:
            return 1.0
        if duration_ms <= 15000:
            return 0.7
        if duration_ms <= 30000:
            return 0.4
        return 0.1

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float:
        """_rate 函数：计算或整理一段辅助数据，让主流程保持清晰。"""
        return round(numerator * 100 / denominator, 2) if denominator else 0.0

    @staticmethod
    def _percentile(values: list[int], quantile: float) -> int:
        """_percentile 函数：计算或整理一段辅助数据，让主流程保持清晰。"""
        if not values:
            return 0
        values = sorted(values)
        if quantile == 0.5:
            return int(median(values))
        index = min(len(values) - 1, int(round((len(values) - 1) * quantile)))
        return int(values[index])


