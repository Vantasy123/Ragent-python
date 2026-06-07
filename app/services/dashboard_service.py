"""模块导读：本文件位于 app/services/dashboard_service.py，属于服务层。

主要职责：承接路由层请求，组织数据库、缓存、Trace、Agent 和外部组件完成业务流程。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

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
    """DashboardService 服务类：集中处理一类业务流程，让路由层不需要直接操作数据库、缓存或外部组件。"""
    def __init__(self, db: Session):
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
        self.db = db

    def overview(self) -> dict:
        """overview 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
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
        """performance 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
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
        """_average_span_duration 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        rows = self.db.query(TraceSpan).filter(TraceSpan.operation == operation).all()
        durations = [row.duration_ms for row in rows if row.duration_ms]
        return round(sum(durations) / len(durations), 2) if durations else 0

    def trends(self) -> dict:
        # 仪表盘趋势按东八区自然日统计，避免 UTC 口径把凌晨数据切到前一天。
        """trends 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
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

    def finops_stats(self) -> dict:
        """finops_stats 函数：聚合大模型 Token 消费及算力成本统计，用于后台商业计费看板展示。"""
        from sqlalchemy import func

        # 1. 汇总总体用量和费用
        total_stats = self.db.query(
            func.sum(TraceRun.prompt_tokens),
            func.sum(TraceRun.completion_tokens),
            func.sum(TraceRun.total_tokens),
            func.sum(TraceRun.cost)
        ).first()

        prompt_tokens = int(total_stats[0] or 0)
        completion_tokens = int(total_stats[1] or 0)
        total_tokens = int(total_stats[2] or 0)
        total_cost = float(total_stats[3] or 0.0)

        # 2. 汇总今日和昨日消费
        now = shanghai_now()
        today_start, today_end, _ = shanghai_day_utc_range(now, 0)
        yesterday_start, yesterday_end, _ = shanghai_day_utc_range(now, 1)

        today_cost = float(self.db.query(func.sum(TraceRun.cost)).filter(TraceRun.created_at >= today_start, TraceRun.created_at < today_end).scalar() or 0.0)
        yesterday_cost = float(self.db.query(func.sum(TraceRun.cost)).filter(TraceRun.created_at >= yesterday_start, TraceRun.created_at < yesterday_end).scalar() or 0.0)

        # 3. 最近 7 天的每日消费折线
        points = []
        for offset in range(6, -1, -1):
            day_start, day_end, label = shanghai_day_utc_range(now, offset)
            day_data = self.db.query(
                func.sum(TraceRun.cost),
                func.sum(TraceRun.total_tokens)
            ).filter(TraceRun.created_at >= day_start, TraceRun.created_at < day_end).first()
            points.append({
                "date": label,
                "cost": round(float(day_data[0] or 0.0), 6),
                "tokens": int(day_data[1] or 0)
            })

        # 4. 不同大模型的消费占比 (分析最近 1000 条消费 Span 结构)
        spans_with_cost = self.db.query(TraceSpan).filter(TraceSpan.cost > 0).order_by(TraceSpan.created_at.desc()).limit(1000).all()
        model_costs = {}
        for span in spans_with_cost:
            model_name = "unknown"
            meta = span.metadata_json or {}
            for source in [meta.get("context"), meta.get("output"), meta.get("input")]:
                if not source:
                    continue
                if "model" in source:
                    model_name = source["model"]
                    break
                if "model_name" in source:
                    model_name = source["model_name"]
                    break
            
            if model_name == "unknown":
                if span.operation == "embedding":
                    model_name = "text-embedding-v3"
                else:
                    model_name = "qwen-plus"
                    
            model_costs[model_name] = model_costs.get(model_name, 0.0) + (span.cost or 0.0)

        model_distribution = [
            {"model": name, "cost": round(cost, 6)}
            for name, cost in model_costs.items()
        ]

        return {
            "totalCost": round(total_cost, 6),
            "totalTokens": total_tokens,
            "promptTokens": prompt_tokens,
            "completionTokens": completion_tokens,
            "todayCost": round(today_cost, 6),
            "yesterdayCost": round(yesterday_cost, 6),
            "points": points,
            "modelDistribution": model_distribution
        }


