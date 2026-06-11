"""Trace 分析服务，把调用链数据转成运维 RCA 可消费的证据。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.time_utils import to_shanghai_iso
from app.domain.models import TraceRun, TraceSpan


class TraceAnalysisService:
    """只读分析 TraceRun 和 TraceSpan，用于发现慢调用、失败节点和高风险链路。"""

    def __init__(self, db: Session):
        """构造函数：接收数据库会话，后续只执行查询，不写入任何 Trace 数据。"""

        self.db = db

    def analyze_recent(self, limit: int = 20, slow_threshold_ms: int = 1000) -> dict[str, Any]:
        """分析最近一批 Trace，输出慢 span、失败 span 和 RCA 初筛线索。"""

        safe_limit = max(1, min(int(limit or 20), 100))
        threshold = max(1, int(slow_threshold_ms or 1000))
        runs = self.db.query(TraceRun).order_by(TraceRun.created_at.desc()).limit(safe_limit).all()
        if not runs:
            return {
                "status": "healthy",
                "displayName": "Trace 调用链分析",
                "summary": "暂无 TraceRun 数据，无法进行调用链分析",
                "data": {
                    "runCount": 0,
                    "spanCount": 0,
                    "slowThresholdMs": threshold,
                    "slowSpans": [],
                    "errorSpans": [],
                    "topOperations": [],
                    "traceSummaries": [],
                    "rootCauseHints": [],
                    "recommendedNextSteps": ["接入 Trace 写入或执行一次运维 Agent 任务后再分析调用链证据"],
                    "dataGaps": ["暂无 TraceRun 数据"],
                },
            }

        spans = [span for run in runs for span in run.spans]
        slow_spans = sorted([span for span in spans if int(span.duration_ms or 0) >= threshold], key=lambda item: int(item.duration_ms or 0), reverse=True)
        error_spans = [span for span in spans if self._span_failed(span)]
        top_operations = self._top_operations(spans)
        status = "critical" if error_spans else "degraded" if slow_spans else "healthy"
        return {
            "status": status,
            "displayName": "Trace 调用链分析",
            "summary": self._summary(len(runs), len(spans), len(error_spans), len(slow_spans)),
            "data": {
                "runCount": len(runs),
                "spanCount": len(spans),
                "slowThresholdMs": threshold,
                "slowSpans": [self._span_to_dict(span) for span in slow_spans[:10]],
                "errorSpans": [self._span_to_dict(span) for span in error_spans[:10]],
                "topOperations": top_operations[:10],
                "traceSummaries": [self._run_to_dict(run) for run in runs[:10]],
                "rootCauseHints": self._root_cause_hints(slow_spans, error_spans, top_operations),
                "recommendedNextSteps": self._recommended_steps(slow_spans, error_spans, top_operations),
                "dataGaps": self._data_gaps(spans),
            },
        }

    def _span_failed(self, span: TraceSpan) -> bool:
        """判断 span 是否失败，兼容 status 和 error_message 两种记录方式。"""

        status = str(span.status or "").lower()
        return status not in {"", "success", "ok", "completed"} or bool(str(span.error_message or "").strip())

    def _span_to_dict(self, span: TraceSpan) -> dict[str, Any]:
        """把 TraceSpan 序列化为报告和工具结果可直接消费的结构。"""

        metadata = span.metadata_json if isinstance(span.metadata_json, dict) else {}
        return {
            "traceId": span.trace_id,
            "spanId": span.id,
            "operation": span.operation,
            "status": span.status,
            "durationMs": int(span.duration_ms or 0),
            "errorMessage": span.error_message or "",
            "createdAt": to_shanghai_iso(span.created_at),
            "promptTokens": span.prompt_tokens or 0,
            "completionTokens": span.completion_tokens or 0,
            "totalTokens": span.total_tokens or 0,
            "cost": span.cost or 0.0,
            "metadataSummary": self._metadata_summary(metadata),
        }

    def _run_to_dict(self, run: TraceRun) -> dict[str, Any]:
        """把 TraceRun 序列化为调用链概览。"""

        return {
            "traceId": run.id,
            "status": run.status,
            "sessionId": run.session_id,
            "taskId": run.task_id,
            "totalDurationMs": run.total_duration_ms,
            "spanCount": len(run.spans),
            "createdAt": to_shanghai_iso(run.created_at),
            "totalTokens": run.total_tokens,
            "cost": run.cost,
        }

    def _metadata_summary(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """提取少量非敏感字段，避免工具结果塞入完整上下文。"""

        summary: dict[str, Any] = {}
        for section in ("input", "output", "context"):
            value = metadata.get(section)
            if isinstance(value, dict):
                summary[section] = {key: self._short_value(value.get(key)) for key in list(value.keys())[:5]}
        if not summary:
            summary = {key: self._short_value(metadata.get(key)) for key in list(metadata.keys())[:5]}
        return summary

    def _short_value(self, value: Any) -> Any:
        """把长文本裁剪到适合报告展示的长度。"""

        if isinstance(value, (int, float, bool)) or value is None:
            return value
        if isinstance(value, (list, tuple)):
            return f"{len(value)} items"
        if isinstance(value, dict):
            return f"{len(value)} keys"
        text = str(value)
        return text if len(text) <= 120 else f"{text[:117]}..."

    def _top_operations(self, spans: list[TraceSpan]) -> list[dict[str, Any]]:
        """按 operation 聚合耗时、失败数和平均耗时。"""

        buckets: dict[str, dict[str, Any]] = {}
        for span in spans:
            operation = str(span.operation or "unknown")
            bucket = buckets.setdefault(operation, {"operation": operation, "count": 0, "errorCount": 0, "totalDurationMs": 0, "maxDurationMs": 0})
            duration = int(span.duration_ms or 0)
            bucket["count"] += 1
            bucket["totalDurationMs"] += duration
            bucket["maxDurationMs"] = max(bucket["maxDurationMs"], duration)
            if self._span_failed(span):
                bucket["errorCount"] += 1
        for bucket in buckets.values():
            bucket["avgDurationMs"] = round(bucket["totalDurationMs"] / max(1, bucket["count"]), 2)
        return sorted(buckets.values(), key=lambda item: (item["errorCount"], item["totalDurationMs"], item["maxDurationMs"]), reverse=True)

    def _root_cause_hints(self, slow_spans: list[TraceSpan], error_spans: list[TraceSpan], top_operations: list[dict[str, Any]]) -> list[str]:
        """根据慢 span 和失败 span 生成 RCA 初筛线索。"""

        hints: list[str] = []
        if error_spans:
            operations = "、".join(sorted({span.operation for span in error_spans[:5]}))
            hints.append(f"调用链存在失败 span，优先复核 {operations} 的错误信息和上下游输入输出")
        if slow_spans:
            operations = "、".join(sorted({span.operation for span in slow_spans[:5]}))
            hints.append(f"调用链存在慢 span，优先定位 {operations} 的耗时来源")
        top_names = {str(item.get("operation") or "").lower() for item in top_operations[:3]}
        if any("retrieval" in name or "search" in name for name in top_names):
            hints.append("检索链路耗时靠前，优先检查向量库、BM25、重排序和知识库过滤条件")
        if any("llm" in name or "generation" in name or "chat" in name for name in top_names):
            hints.append("模型调用耗时靠前，优先检查模型响应时间、上下文长度和流式输出状态")
        if any("tool" in name or "ops" in name for name in top_names):
            hints.append("工具调用耗时或失败靠前，优先检查工具白名单、目标服务连通性和审批状态")
        return self._deduplicate(hints)

    def _recommended_steps(self, slow_spans: list[TraceSpan], error_spans: list[TraceSpan], top_operations: list[dict[str, Any]]) -> list[str]:
        """生成下一步排查建议。"""

        steps: list[str] = []
        for span in error_spans[:3]:
            steps.append(f"打开 Trace {span.trace_id}，查看失败节点 {span.operation} 的 input/output、errorMessage 和相邻 span")
        for span in slow_spans[:3]:
            steps.append(f"对齐 Trace {span.trace_id} 中 {span.operation} 的 {span.duration_ms} ms 耗时与同期指标、日志和告警")
        if top_operations:
            top = top_operations[0]
            steps.append(f"优先优化累计耗时最高的 operation {top['operation']}，当前累计 {top['totalDurationMs']} ms")
        return self._deduplicate(steps) or ["继续采集更多 Trace 样本，并与告警、指标、日志做时间线对齐"]

    def _data_gaps(self, spans: list[TraceSpan]) -> list[str]:
        """指出当前 Trace 数据对 RCA 的不足。"""

        gaps: list[str] = []
        if not spans:
            gaps.append("TraceRun 缺少 TraceSpan，无法定位具体慢节点或失败节点")
        if spans and all(not (span.metadata_json or {}) for span in spans):
            gaps.append("TraceSpan 缺少结构化 metadata，无法查看 input/output 证据")
        if spans and all(not span.error_message for span in spans if self._span_failed(span)):
            gaps.append("失败 span 缺少 error_message，建议补齐异常摘要")
        return gaps

    def _summary(self, run_count: int, span_count: int, error_count: int, slow_count: int) -> str:
        """生成调用链分析摘要。"""

        if error_count:
            return f"分析 {run_count} 条 Trace、{span_count} 个 span，发现 {error_count} 个失败 span 和 {slow_count} 个慢 span"
        if slow_count:
            return f"分析 {run_count} 条 Trace、{span_count} 个 span，发现 {slow_count} 个慢 span"
        return f"分析 {run_count} 条 Trace、{span_count} 个 span，未发现明显慢调用或失败节点"

    def _deduplicate(self, lines: list[str]) -> list[str]:
        """按原顺序去重。"""

        seen: set[str] = set()
        results: list[str] = []
        for line in lines:
            text = str(line or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            results.append(text)
        return results
