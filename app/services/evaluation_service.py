"""模块导读：本文件位于 app/services/evaluation_service.py，属于服务层。

主要职责：承接路由层请求，组织数据库、缓存、Trace、Agent 和外部组件完成业务流程。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from statistics import median
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time_utils import to_shanghai_iso
from app.domain.models import (
    ConversationMessage,
    EvaluationBatchRun,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationDataset,
    EvaluationIssue,
    EvaluationMetric,
    EvaluationRun,
    MessageFeedback,
    TraceRun,
    TraceSpan,
)


MAX_BATCH_CASES = 50
SCORE_WEIGHTS = {
    "retrieval_quality": 0.30,
    "faithfulness": 0.25,
    "answer_relevancy": 0.20,
    "answer_correctness": 0.20,
    "system_quality": 0.05,
}


def _metadata(value: dict[str, Any] | None) -> dict[str, Any]:
    """_metadata 函数：计算或整理一段辅助数据，让主流程保持清晰。"""
    value = value or {}
    if set(value.keys()) == {"metadata"} and isinstance(value["metadata"], dict):
        return value["metadata"]
    return value


def _span_part(meta: dict[str, Any], key: str) -> dict[str, Any]:
    """读取新 trace 结构中的 input/output/context，旧结构下返回空字典。"""

    value = meta.get(key)
    return value if isinstance(value, dict) else {}


def _normalize_list(value: Any) -> list:
    """把接口输入统一整理成列表，兼容逗号分隔字符串和 JSON 数组。"""

    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
        return [item.strip() for item in text.split(",") if item.strip()]
    return [value]


def _tokens(text: str) -> list[str]:
    """用轻量分词计算答案重合度，避免离线评估必须依赖额外 NLP 包。"""

    return re.findall(r"[\w\u4e00-\u9fff]+", (text or "").lower())


def _safe_score(value: Any) -> float:
    """把任意分值收敛到 0-1 区间，避免异常裁判输出污染聚合分。"""

    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(max(0.0, min(1.0, score)), 4)


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

    def list_datasets(self, page_no: int, page_size: int) -> tuple[list[EvaluationDataset], int]:
        """查询评估数据集列表。"""

        query = self.db.query(EvaluationDataset).order_by(EvaluationDataset.created_at.desc())
        total = query.count()
        rows = query.offset((page_no - 1) * page_size).limit(page_size).all()
        return rows, total

    def create_dataset(self, payload: dict[str, Any], user_id: str | None = None) -> EvaluationDataset:
        """创建评估数据集。"""

        row = EvaluationDataset(
            name=str(payload.get("name") or "未命名数据集")[:255],
            description=str(payload.get("description") or ""),
            kb_id=payload.get("kbId") or payload.get("kb_id") or None,
            tags=_normalize_list(payload.get("tags")),
            enabled=bool(payload.get("enabled", True)),
            created_by=user_id,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_dataset(self, dataset_id: str, payload: dict[str, Any]) -> EvaluationDataset:
        """更新评估数据集，找不到时抛出 ValueError。"""

        row = self.get_dataset(dataset_id)
        if not row:
            raise ValueError("评估数据集不存在")
        if "name" in payload:
            row.name = str(payload.get("name") or row.name)[:255]
        if "description" in payload:
            row.description = str(payload.get("description") or "")
        if "kbId" in payload or "kb_id" in payload:
            row.kb_id = payload.get("kbId") or payload.get("kb_id") or None
        if "tags" in payload:
            row.tags = _normalize_list(payload.get("tags"))
        if "enabled" in payload:
            row.enabled = bool(payload.get("enabled"))
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_dataset(self, dataset_id: str) -> bool:
        """删除评估数据集及其用例、批次结果。"""

        row = self.get_dataset(dataset_id)
        if not row:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    def get_dataset(self, dataset_id: str) -> EvaluationDataset | None:
        """按 ID 读取评估数据集。"""

        return self.db.query(EvaluationDataset).filter(EvaluationDataset.id == dataset_id).first()

    def list_cases(self, dataset_id: str, page_no: int, page_size: int) -> tuple[list[EvaluationCase], int]:
        """查询数据集下的评估用例。"""

        query = (
            self.db.query(EvaluationCase)
            .filter(EvaluationCase.dataset_id == dataset_id)
            .order_by(EvaluationCase.created_at.asc())
        )
        total = query.count()
        rows = query.offset((page_no - 1) * page_size).limit(page_size).all()
        return rows, total

    def create_case(self, dataset_id: str, payload: dict[str, Any]) -> EvaluationCase:
        """创建单条评估用例。"""

        dataset = self.get_dataset(dataset_id)
        if not dataset:
            raise ValueError("评估数据集不存在")
        row = EvaluationCase(
            dataset_id=dataset_id,
            question=str(payload.get("question") or "").strip(),
            expected_answer=str(payload.get("expectedAnswer") or payload.get("expected_answer") or ""),
            expected_chunk_ids=[str(item) for item in _normalize_list(payload.get("expectedChunkIds") or payload.get("expected_chunk_ids"))],
            expected_keywords=[str(item) for item in _normalize_list(payload.get("expectedKeywords") or payload.get("expected_keywords"))],
            kb_id=payload.get("kbId") or payload.get("kb_id") or dataset.kb_id,
            tags=_normalize_list(payload.get("tags")),
            enabled=bool(payload.get("enabled", True)),
            meta_data=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
        )
        if not row.question:
            raise ValueError("评估问题不能为空")
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_case(self, case_id: str, payload: dict[str, Any]) -> EvaluationCase:
        """更新单条评估用例。"""

        row = self.get_case(case_id)
        if not row:
            raise ValueError("评估用例不存在")
        if "question" in payload:
            row.question = str(payload.get("question") or "").strip()
        if "expectedAnswer" in payload or "expected_answer" in payload:
            row.expected_answer = str(payload.get("expectedAnswer") or payload.get("expected_answer") or "")
        if "expectedChunkIds" in payload or "expected_chunk_ids" in payload:
            row.expected_chunk_ids = [str(item) for item in _normalize_list(payload.get("expectedChunkIds") or payload.get("expected_chunk_ids"))]
        if "expectedKeywords" in payload or "expected_keywords" in payload:
            row.expected_keywords = [str(item) for item in _normalize_list(payload.get("expectedKeywords") or payload.get("expected_keywords"))]
        if "kbId" in payload or "kb_id" in payload:
            row.kb_id = payload.get("kbId") or payload.get("kb_id") or None
        if "tags" in payload:
            row.tags = _normalize_list(payload.get("tags"))
        if "enabled" in payload:
            row.enabled = bool(payload.get("enabled"))
        if "metadata" in payload:
            row.meta_data = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        if not row.question:
            raise ValueError("评估问题不能为空")
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_case(self, case_id: str) -> EvaluationCase | None:
        """按 ID 读取评估用例。"""

        return self.db.query(EvaluationCase).filter(EvaluationCase.id == case_id).first()

    def delete_case(self, case_id: str) -> bool:
        """删除单条评估用例。"""

        row = self.get_case(case_id)
        if not row:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    def import_cases(self, dataset_id: str, rows: list[dict[str, Any]]) -> list[EvaluationCase]:
        """批量导入评估用例，跳过空问题行。"""

        created: list[EvaluationCase] = []
        for item in rows:
            if not str(item.get("question") or "").strip():
                continue
            created.append(self.create_case(dataset_id, item))
        return created

    def create_batch_run(self, dataset_id: str, user_id: str | None = None) -> EvaluationBatchRun:
        """创建批量评估任务；真正执行由后台任务触发。"""

        dataset = self.get_dataset(dataset_id)
        if not dataset:
            raise ValueError("评估数据集不存在")
        cases = (
            self.db.query(EvaluationCase)
            .filter(EvaluationCase.dataset_id == dataset_id, EvaluationCase.enabled.is_(True))
            .order_by(EvaluationCase.created_at.asc())
            .all()
        )
        if not cases:
            raise ValueError("数据集中没有启用的评估用例")
        if len(cases) > MAX_BATCH_CASES:
            raise ValueError(f"单批次最多支持 {MAX_BATCH_CASES} 条用例")
        row = EvaluationBatchRun(
            dataset_id=dataset_id,
            status="pending",
            total_cases=len(cases),
            completed_cases=0,
            failed_cases=0,
            created_by=user_id,
            summary="评估批次已创建，等待后台执行。",
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def list_batch_runs(self, dataset_id: str | None, page_no: int, page_size: int) -> tuple[list[EvaluationBatchRun], int]:
        """查询批量评估运行记录。"""

        query = self.db.query(EvaluationBatchRun)
        if dataset_id:
            query = query.filter(EvaluationBatchRun.dataset_id == dataset_id)
        query = query.order_by(EvaluationBatchRun.created_at.desc())
        total = query.count()
        rows = query.offset((page_no - 1) * page_size).limit(page_size).all()
        return rows, total

    def get_batch_run(self, batch_id: str) -> EvaluationBatchRun | None:
        """按 ID 读取批量评估运行记录。"""

        return self.db.query(EvaluationBatchRun).filter(EvaluationBatchRun.id == batch_id).first()

    def list_case_results(self, batch_id: str, page_no: int, page_size: int) -> tuple[list[EvaluationCaseResult], int]:
        """查询批次下的单用例评估结果。"""

        query = (
            self.db.query(EvaluationCaseResult)
            .filter(EvaluationCaseResult.batch_run_id == batch_id)
            .order_by(EvaluationCaseResult.created_at.asc())
        )
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
            "datasetCount": self.db.query(EvaluationDataset).count(),
            "caseCount": self.db.query(EvaluationCase).count(),
            "batchRunCount": self.db.query(EvaluationBatchRun).count(),
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

    @staticmethod
    def dataset_to_dict(dataset: EvaluationDataset, include_cases: bool = False) -> dict[str, Any]:
        """把评估数据集转换成前端可直接消费的字典。"""

        data = {
            "id": dataset.id,
            "name": dataset.name,
            "description": dataset.description,
            "kbId": dataset.kb_id,
            "tags": dataset.tags or [],
            "enabled": dataset.enabled,
            "caseCount": len(dataset.cases),
            "createdAt": to_shanghai_iso(dataset.created_at),
            "updatedAt": to_shanghai_iso(dataset.updated_at),
        }
        if include_cases:
            data["cases"] = [EvaluationService.case_to_dict(case) for case in dataset.cases]
        return data

    @staticmethod
    def case_to_dict(case: EvaluationCase) -> dict[str, Any]:
        """把评估用例转换成前端可直接消费的字典。"""

        return {
            "id": case.id,
            "datasetId": case.dataset_id,
            "question": case.question,
            "expectedAnswer": case.expected_answer,
            "expectedChunkIds": case.expected_chunk_ids or [],
            "expectedKeywords": case.expected_keywords or [],
            "kbId": case.kb_id,
            "tags": case.tags or [],
            "enabled": case.enabled,
            "metadata": case.meta_data or {},
            "createdAt": to_shanghai_iso(case.created_at),
            "updatedAt": to_shanghai_iso(case.updated_at),
        }

    @staticmethod
    def batch_to_dict(batch: EvaluationBatchRun, include_results: bool = False) -> dict[str, Any]:
        """把批量评估运行记录转换成前端可直接消费的字典。"""

        data = {
            "id": batch.id,
            "datasetId": batch.dataset_id,
            "datasetName": batch.dataset.name if batch.dataset else "",
            "status": batch.status,
            "totalCases": batch.total_cases,
            "completedCases": batch.completed_cases,
            "failedCases": batch.failed_cases,
            "overallScore": batch.overall_score,
            "metricSummary": batch.metric_summary or {},
            "summary": batch.summary,
            "errorMessage": batch.error_message,
            "createdAt": to_shanghai_iso(batch.created_at),
            "updatedAt": to_shanghai_iso(batch.updated_at),
        }
        if include_results:
            data["results"] = [EvaluationService.case_result_to_dict(result) for result in batch.results]
        return data

    @staticmethod
    def case_result_to_dict(result: EvaluationCaseResult) -> dict[str, Any]:
        """把单条用例结果转换成前端可直接消费的字典。"""

        return {
            "id": result.id,
            "batchRunId": result.batch_run_id,
            "caseId": result.case_id,
            "traceId": result.trace_id,
            "status": result.status,
            "question": result.question,
            "answer": result.answer,
            "expectedAnswer": result.expected_answer,
            "retrievedContexts": result.retrieved_contexts or [],
            "metrics": result.metrics or {},
            "overallScore": result.overall_score,
            "issueSummary": result.issue_summary or [],
            "errorMessage": result.error_message,
            "createdAt": to_shanghai_iso(result.created_at),
            "updatedAt": to_shanghai_iso(result.updated_at),
        }

    async def process_batch_run(self, batch_id: str, user_id: str | None = None) -> EvaluationBatchRun | None:
        """执行离线批量评估；单条失败只记录结果，不中断整个批次。"""

        batch = self.get_batch_run(batch_id)
        if not batch:
            return None
        cases = (
            self.db.query(EvaluationCase)
            .filter(EvaluationCase.dataset_id == batch.dataset_id, EvaluationCase.enabled.is_(True))
            .order_by(EvaluationCase.created_at.asc())
            .limit(MAX_BATCH_CASES)
            .all()
        )
        batch.status = "running"
        batch.total_cases = len(cases)
        batch.summary = "评估批次执行中。"
        self.db.commit()

        for case in cases:
            result = EvaluationCaseResult(
                batch_run_id=batch.id,
                case_id=case.id,
                status="running",
                question=case.question,
                expected_answer=case.expected_answer,
            )
            self.db.add(result)
            self.db.commit()
            self.db.refresh(result)
            try:
                execution = await self._execute_case(case, user_id)
                metrics, issues, score = self.evaluate_case_metrics(
                    case,
                    execution["answer"],
                    execution["retrievedContexts"],
                    execution.get("trace"),
                )
                result.trace_id = execution.get("traceId")
                result.answer = execution["answer"]
                result.retrieved_contexts = execution["retrievedContexts"]
                result.metrics = metrics
                result.issue_summary = issues
                result.overall_score = score
                result.status = "completed"
                batch.completed_cases += 1
            except Exception as exc:  # pragma: no cover - 真实模型和检索链路失败时走这里。
                result.status = "failed"
                result.error_message = str(exc)
                result.issue_summary = [{"severity": "high", "message": str(exc), "issueKey": "case_execution_failed"}]
                batch.failed_cases += 1
            self.db.commit()

        self._finalize_batch(batch)
        self.db.commit()
        self.db.refresh(batch)
        return batch

    async def _execute_case(self, case: EvaluationCase, user_id: str | None) -> dict[str, Any]:
        """通过项目真实聊天链路执行单条评估用例，并收集回答与 Trace。"""

        from app.services.chat_service import ConversationService, stream_chat

        conversation = ConversationService(self.db).create_conversation(user_id, f"评估：{case.question[:28]}")
        final_answer = ""
        token_parts: list[str] = []
        trace_id = ""
        async for event in stream_chat(
            self.db,
            conversation.id,
            case.question,
            task_id=f"eval-{case.id}",
            deep_thinking=False,
        ):
            if event.get("traceId"):
                trace_id = str(event["traceId"])
            if event.get("type") == "final_answer":
                final_answer = str(event.get("content") or "")
            elif event.get("type") == "token" and not final_answer:
                token_parts.append(str(event.get("content") or ""))
            elif event.get("type") == "error":
                raise RuntimeError(str(event.get("content") or "评估用例执行失败"))

        answer = final_answer or "".join(token_parts)
        trace = self.db.query(TraceRun).filter(TraceRun.id == trace_id).first() if trace_id else None
        return {
            "answer": answer,
            "traceId": trace_id or None,
            "trace": trace,
            "retrievedContexts": self._retrieved_contexts(trace) if trace else [],
        }

    def evaluate_case_metrics(
        self,
        case: EvaluationCase,
        answer: str,
        retrieved_contexts: list[dict[str, Any]],
        trace: TraceRun | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], float]:
        """计算单条离线评估用例的混合指标。"""

        metrics: dict[str, Any] = {}
        issues: list[dict[str, Any]] = []
        metrics.update(self._retrieval_case_metrics(case, retrieved_contexts))
        metrics.update(self._answer_case_metrics(case, answer))
        metrics.update(self._system_case_metrics(trace))
        judge_metrics, judge_issues = self._judge_case_metrics(case, answer, retrieved_contexts)
        metrics.update(judge_metrics)
        issues.extend(judge_issues)

        for key, metric in metrics.items():
            if metric.get("status") == "completed" and metric.get("score", 1.0) < 0.5:
                issues.append(
                    {
                        "severity": "medium",
                        "issueKey": f"low_{key}",
                        "message": f"{metric.get('label', key)}低于阈值",
                        "evidence": metric.get("evidence", {}),
                    }
                )
        return metrics, issues, self._weighted_case_score(metrics)

    def _retrieval_case_metrics(self, case: EvaluationCase, contexts: list[dict[str, Any]]) -> dict[str, Any]:
        """计算检索命中率、召回率、MRR 和上下文相关性指标。"""

        expected_ids = {str(item) for item in (case.expected_chunk_ids or []) if str(item)}
        retrieved_ids = [str(item.get("chunkId") or "") for item in contexts if item.get("chunkId")]
        previews = [str(item.get("preview") or item.get("content") or "") for item in contexts]
        expected_keywords = [str(item) for item in (case.expected_keywords or []) if str(item)]
        expected_terms = set(_tokens(case.expected_answer) + [keyword.lower() for keyword in expected_keywords])

        metrics: dict[str, Any] = {}
        if expected_ids:
            hits = [chunk_id for chunk_id in retrieved_ids if chunk_id in expected_ids]
            first_hit = next((index for index, chunk_id in enumerate(retrieved_ids, start=1) if chunk_id in expected_ids), None)
            metrics["hit_at_k"] = self._case_metric("检索命中率", 1.0 if hits else 0.0, "期望片段是否出现在召回结果中", {"expected": list(expected_ids), "retrieved": retrieved_ids})
            metrics["recall_at_k"] = self._case_metric("检索召回率", len(set(hits)) / max(len(expected_ids), 1), "召回结果覆盖期望片段的比例", {"hits": hits})
            metrics["mrr"] = self._case_metric("MRR", 1.0 / first_hit if first_hit else 0.0, "首个命中片段的倒数排名", {"firstHitRank": first_hit})
        else:
            for key, label in {"hit_at_k": "检索命中率", "mrr": "MRR"}.items():
                metrics[key] = self._skipped_metric(label, "未配置期望片段，跳过基于 chunkId 的指标")

        if expected_terms:
            relevant_contexts = [
                preview
                for preview in previews
                if any(term and term in preview.lower() for term in expected_terms)
            ]
            covered_terms = {term for term in expected_terms if any(term and term in preview.lower() for preview in previews)}
            metrics["context_precision"] = self._case_metric(
                "上下文精确率",
                len(relevant_contexts) / max(len(previews), 1),
                "召回上下文中含有期望词的比例",
                {"relevantContexts": len(relevant_contexts), "totalContexts": len(previews)},
            )
            metrics["context_recall"] = self._case_metric(
                "上下文召回率",
                len(covered_terms) / max(len(expected_terms), 1),
                "召回上下文覆盖期望答案词和关键词的比例",
                {"coveredTerms": sorted(covered_terms), "expectedTerms": sorted(expected_terms)},
            )
        else:
            metrics["context_precision"] = self._skipped_metric("上下文精确率", "未配置期望答案或关键词")
            metrics["context_recall"] = self._skipped_metric("上下文召回率", "未配置期望答案或关键词")
        return metrics

    def _answer_case_metrics(self, case: EvaluationCase, answer: str) -> dict[str, Any]:
        """计算答案长度、关键词覆盖和参考答案 token F1。"""

        expected_keywords = [str(item) for item in (case.expected_keywords or []) if str(item)]
        answer_lower = answer.lower()
        covered_keywords = [keyword for keyword in expected_keywords if keyword.lower() in answer_lower]
        answer_tokens = _tokens(answer)
        expected_tokens = _tokens(case.expected_answer)
        common = 0
        if answer_tokens and expected_tokens:
            remaining = list(answer_tokens)
            for token in expected_tokens:
                if token in remaining:
                    common += 1
                    remaining.remove(token)
        precision = common / len(answer_tokens) if answer_tokens else 0.0
        recall = common / len(expected_tokens) if expected_tokens else 0.0
        f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
        return {
            "answer_non_empty": self._case_metric("答案有效长度", 1.0 if len(answer.strip()) >= 20 else 0.2, "答案是否达到可用长度", {"length": len(answer)}),
            "keyword_coverage": self._case_metric(
                "关键词覆盖率",
                len(covered_keywords) / max(len(expected_keywords), 1) if expected_keywords else 1.0,
                "答案覆盖期望关键词的比例",
                {"coveredKeywords": covered_keywords, "expectedKeywords": expected_keywords},
            ),
            "reference_token_f1": (
                self._case_metric("参考答案 F1", f1, "答案与参考答案的 token F1", {"precision": precision, "recall": recall})
                if expected_tokens
                else self._skipped_metric("参考答案 F1", "未配置期望答案")
            ),
        }

    def _system_case_metrics(self, trace: TraceRun | None) -> dict[str, Any]:
        """计算离线用例对应 Trace 的系统稳定性指标。"""

        if not trace:
            return {
                "trace_success": self._case_metric("Trace 成功率", 0.0, "用例未生成 Trace", {}),
                "total_latency": self._skipped_metric("总耗时", "无 Trace，无法计算耗时"),
            }
        return {
            "trace_success": self._case_metric("Trace 成功率", 1.0 if trace.status == "success" else 0.0, "Trace 是否成功完成", {"status": trace.status}),
            "total_latency": self._case_metric("总耗时", self._latency_score(trace.total_duration_ms), "Trace 总耗时折算分", {"totalDurationMs": trace.total_duration_ms}),
        }

    def _judge_case_metrics(
        self,
        case: EvaluationCase,
        answer: str,
        contexts: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """调用裁判模型计算忠实度、相关性和正确性；配置缺失时跳过。"""

        if not (settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY):
            return {
                "faithfulness": self._skipped_metric("忠实度", "未配置裁判模型 API Key"),
                "answer_relevancy": self._skipped_metric("答案相关性", "未配置裁判模型 API Key"),
                "answer_correctness": self._skipped_metric("答案正确性", "未配置裁判模型 API Key"),
            }, []

        try:
            raw = self._call_judge_model(case, answer, contexts)
            parsed = self._parse_judge_response(raw)
        except Exception as exc:
            skipped = {
                "faithfulness": self._skipped_metric("忠实度", f"裁判模型不可用：{exc}"),
                "answer_relevancy": self._skipped_metric("答案相关性", f"裁判模型不可用：{exc}"),
                "answer_correctness": self._skipped_metric("答案正确性", f"裁判模型不可用：{exc}"),
            }
            return skipped, [{"severity": "low", "issueKey": "judge_skipped", "message": str(exc)}]

        labels = {"faithfulness": "忠实度", "answer_relevancy": "答案相关性", "answer_correctness": "答案正确性"}
        return {
            key: self._case_metric(
                label,
                _safe_score((parsed.get(key) or {}).get("score")),
                str((parsed.get(key) or {}).get("reason") or "裁判模型评分"),
                {"judge": parsed.get(key) or {}},
            )
            for key, label in labels.items()
        }, []

    def _call_judge_model(self, case: EvaluationCase, answer: str, contexts: list[dict[str, Any]]) -> str:
        """调用当前主模型充当裁判，要求返回可解析 JSON。"""

        from app.rag.workflow import build_primary_llm

        context_text = "\n".join(f"[{index + 1}] {item.get('preview') or item.get('content') or ''}" for index, item in enumerate(contexts[:5]))
        prompt = f"""
你是 RAG 评估裁判。请只输出 JSON，不要输出 Markdown。
按 0 到 1 评分，并给出中文 reason。字段固定为 faithfulness、answer_relevancy、answer_correctness。

问题：{case.question}
参考答案：{case.expected_answer or "未提供"}
检索上下文：
{context_text or "无"}
模型回答：
{answer}

JSON 示例：
{{"faithfulness":{{"score":0.8,"reason":"回答基本受上下文支持"}},"answer_relevancy":{{"score":0.9,"reason":"回答紧扣问题"}},"answer_correctness":{{"score":0.7,"reason":"与参考答案部分一致"}}}}
""".strip()
        response = build_primary_llm(streaming=False).invoke(prompt)
        return str(getattr(response, "content", response))

    def _parse_judge_response(self, raw: str) -> dict[str, Any]:
        """解析裁判模型 JSON，支持模型偶尔包裹解释文本的情况。"""

        text = raw.strip()
        if not text:
            raise ValueError("裁判模型返回为空")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.S)
            if not match:
                raise ValueError("裁判模型未返回 JSON")
            parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("裁判模型 JSON 不是对象")
        return parsed

    def _retrieved_contexts(self, trace: TraceRun) -> list[dict[str, Any]]:
        """从 Trace retrieval span 中提取检索上下文。"""

        retrieval = self._span(trace, "retrieval")
        if not retrieval:
            return []
        meta = _metadata(retrieval.metadata_json)
        output = _span_part(meta, "output") or meta
        sources = output.get("sources") if isinstance(output.get("sources"), list) else []
        previews = output.get("chunkPreview") if isinstance(output.get("chunkPreview"), list) else []
        contexts: list[dict[str, Any]] = []
        for index, source in enumerate(sources):
            source_data = source if isinstance(source, dict) else {}
            contexts.append({**source_data, "preview": source_data.get("preview") or (previews[index] if index < len(previews) else "")})
        if not contexts:
            contexts = [{"preview": str(item)} for item in previews]
        return contexts

    def _weighted_case_score(self, metrics: dict[str, Any]) -> float:
        """按默认权重计算单用例综合分；跳过指标后自动归一化。"""

        retrieval_keys = ["hit_at_k", "recall_at_k", "mrr", "context_precision", "context_recall"]
        system_keys = ["trace_success", "total_latency"]
        answer_correctness = self._completed_score(metrics.get("answer_correctness"))
        if answer_correctness is None:
            answer_correctness = self._completed_score(metrics.get("reference_token_f1"))
        groups = {
            "retrieval_quality": self._average_completed(metrics, retrieval_keys),
            "faithfulness": self._completed_score(metrics.get("faithfulness")),
            "answer_relevancy": self._completed_score(metrics.get("answer_relevancy")),
            "answer_correctness": answer_correctness,
            "system_quality": self._average_completed(metrics, system_keys),
        }
        weighted = 0.0
        total_weight = 0.0
        for key, score in groups.items():
            if score is None:
                continue
            weight = SCORE_WEIGHTS[key]
            weighted += score * weight
            total_weight += weight
        return round(weighted / total_weight, 4) if total_weight else 0.0

    def _finalize_batch(self, batch: EvaluationBatchRun) -> None:
        """聚合批次结果并写回批次状态。"""

        results = self.db.query(EvaluationCaseResult).filter(EvaluationCaseResult.batch_run_id == batch.id).all()
        completed = [result for result in results if result.status == "completed"]
        failed = [result for result in results if result.status == "failed"]
        batch.completed_cases = len(completed)
        batch.failed_cases = len(failed)
        batch.overall_score = round(sum(result.overall_score for result in completed) / max(len(completed), 1), 4)
        batch.metric_summary = self._metric_summary(completed)
        batch.status = "completed_with_errors" if failed else "completed"
        batch.summary = f"批次完成：成功 {len(completed)} 条，失败 {len(failed)} 条，综合评分 {batch.overall_score:.2f}。"

    def _metric_summary(self, results: list[EvaluationCaseResult]) -> dict[str, Any]:
        """按指标名聚合批次均值。"""

        buckets: dict[str, list[float]] = defaultdict(list)
        for result in results:
            for key, metric in (result.metrics or {}).items():
                if isinstance(metric, dict) and metric.get("status") == "completed":
                    buckets[key].append(float(metric.get("score") or 0.0))
        return {key: round(sum(values) / max(len(values), 1), 4) for key, values in buckets.items()}

    @staticmethod
    def _case_metric(label: str, score: float, reason: str, evidence: dict[str, Any]) -> dict[str, Any]:
        """构造单用例指标对象。"""

        return {"label": label, "score": _safe_score(score), "reason": reason, "evidence": evidence, "status": "completed"}

    @staticmethod
    def _skipped_metric(label: str, reason: str) -> dict[str, Any]:
        """构造跳过的指标对象，聚合分会自动忽略。"""

        return {"label": label, "score": None, "reason": reason, "evidence": {}, "status": "skipped"}

    @staticmethod
    def _completed_score(metric: dict[str, Any] | None) -> float | None:
        """读取已完成指标分值。"""

        if not metric or metric.get("status") != "completed":
            return None
        return _safe_score(metric.get("score"))

    def _average_completed(self, metrics: dict[str, Any], keys: list[str]) -> float | None:
        """计算一组已完成指标的均值。"""

        values = [score for key in keys if (score := self._completed_score(metrics.get(key))) is not None]
        return round(sum(values) / len(values), 4) if values else None

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
            input_data = _span_part(meta, "input")
            context_data = _span_part(meta, "context")
            output_data = _span_part(meta, "output")
            tool_name = (
                input_data.get("toolName")
                or input_data.get("tool")
                or context_data.get("toolName")
                or meta.get("toolName")
                or meta.get("tool_name")
                or meta.get("name")
                or span.operation
            )
            args = input_data.get("args") or meta.get("args") or meta.get("params") or {}
            signature = f"{tool_name}:{args}"
            if not tool_name:
                issues.append(self._issue(run, "tool", "unknown_tool", "high", "Tool span has no tool name", meta))
            if signature in seen:
                issues.append(self._issue(run, "tool", "duplicate_tool_call", "medium", "Repeated same tool call", meta))
            seen.add(signature)
            if span.status != "success":
                result = output_data.get("result") if isinstance(output_data.get("result"), dict) else {}
                issues.append(
                    self._issue(
                        run,
                        "tool",
                        "tool_call_failed",
                        "high",
                        span.error_message or result.get("error") or "Tool call failed",
                        meta,
                    )
                )
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
            return "智能体运行通过规则评估，未发现明显质量问题。"
        high = sum(1 for issue in issues if issue.severity == "high")
        return f"智能体运行评分 {score:.2f}，发现问题 {len(issues)} 个，其中高风险问题 {high} 个。"

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


