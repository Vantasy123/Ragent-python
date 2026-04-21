from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from models import Conversation, IngestionTask, KnowledgeBase, TraceRun, User


class DashboardService:
    def __init__(self, db: Session):
        self.db = db

    def overview(self) -> dict:
        return {
            "users": self.db.query(User).count(),
            "knowledgeBases": self.db.query(KnowledgeBase).count(),
            "conversations": self.db.query(Conversation).count(),
            "ingestionTasks": self.db.query(IngestionTask).count(),
            "traceRuns": self.db.query(TraceRun).count(),
        }

    def performance(self) -> dict:
        runs = self.db.query(TraceRun).all()
        durations = [row.total_duration_ms for row in runs if row.total_duration_ms]
        avg = sum(durations) / len(durations) if durations else 0
        success = sum(1 for row in runs if row.status == "success")
        total = len(runs)
        return {
            "avgTraceDurationMs": round(avg, 2),
            "successRate": round((success / total) * 100, 2) if total else 0,
            "completedTasks": self.db.query(IngestionTask).filter(IngestionTask.status == "completed").count(),
        }

    def trends(self) -> dict:
        now = datetime.utcnow()
        days = []
        for offset in range(6, -1, -1):
            day_start = (now - timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            days.append(
                {
                    "date": day_start.strftime("%Y-%m-%d"),
                    "conversations": self.db.query(Conversation).filter(Conversation.created_at >= day_start, Conversation.created_at < day_end).count(),
                    "traceRuns": self.db.query(TraceRun).filter(TraceRun.created_at >= day_start, TraceRun.created_at < day_end).count(),
                }
            )
        return {"points": days}
