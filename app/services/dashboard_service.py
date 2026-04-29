"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.domain.models import (
    Conversation,
    ConversationMessage,
    IngestionPipeline,
    IngestionTask,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
    TraceRun,
    TraceSpan,
    User,
)
from app.core.time_utils import shanghai_day_utc_range, shanghai_now
from app.services.evaluation_service import EvaluationService


class DashboardService:
    def __init__(self, db: Session):
        self.db = db

    def overview(self) -> dict:
        trace_runs = self.db.query(TraceRun).count()
        return {
            "users": self.db.query(User).count(),
            "adminUsers": self.db.query(User).filter(User.role == "admin").count(),
            "knowledgeBases": self.db.query(KnowledgeBase).count(),
            "documents": self.db.query(KnowledgeDocument).count(),
            "chunks": self.db.query(KnowledgeChunk).count(),
            "conversations": self.db.query(Conversation).count(),
            "messages": self.db.query(ConversationMessage).count(),
            "ingestionTasks": self.db.query(IngestionTask).count(),
            "ingestionPipelines": self.db.query(IngestionPipeline).count(),
            "traces": trace_runs,
            "traceRuns": trace_runs,
            "traceSpans": self.db.query(TraceSpan).count(),
        }

    def performance(self) -> dict:
        runs = self.db.query(TraceRun).all()
        durations = [row.total_duration_ms for row in runs if row.total_duration_ms]
        avg = sum(durations) / len(durations) if durations else 0
        success = sum(1 for row in runs if row.status == "success")
        total = len(runs)
        evaluation = EvaluationService(self.db).overview()
        error_count = sum(1 for row in runs if row.status != "success")
        return {
            "avgResponseMs": round(avg, 2),
            "avgRetrievalMs": self._average_span_duration("retrieval"),
            "avgTraceDurationMs": round(avg, 2),
            "successRate": round((success / total) * 100, 2) if total else 0,
            "errorCount": error_count,
            "completedTasks": self.db.query(IngestionTask).filter(IngestionTask.status == "completed").count(),
            "evaluation": evaluation,
            "avgEvaluationScore": evaluation["avgScore"],
            "feedbackSatisfactionRate": evaluation["feedbackSatisfactionRate"],
            "lowScoreRuns": evaluation["lowScoreRuns"],
        }

    def _average_span_duration(self, operation: str) -> float:
        rows = self.db.query(TraceSpan).filter(TraceSpan.operation == operation).all()
        durations = [row.duration_ms for row in rows if row.duration_ms]
        return round(sum(durations) / len(durations), 2) if durations else 0

    def trends(self) -> dict:
        # 仪表盘趋势按东八区自然日统计，避免 UTC 口径把凌晨数据切到前一天。
        now = shanghai_now()
        days = []
        for offset in range(6, -1, -1):
            day_start, day_end, label = shanghai_day_utc_range(now, offset)
            days.append(
                {
                    "date": label,
                    "conversations": self.db.query(Conversation).filter(Conversation.created_at >= day_start, Conversation.created_at < day_end).count(),
                    "traceRuns": self.db.query(TraceRun).filter(TraceRun.created_at >= day_start, TraceRun.created_at < day_end).count(),
                }
            )
        return {"points": days}


