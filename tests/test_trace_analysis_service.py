from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.domain.models import TraceRun, TraceSpan
from app.services.trace_analysis_service import TraceAnalysisService


class TraceAnalysisServiceTest(unittest.TestCase):
    """验证 Trace 分析服务能从调用链中提取慢节点、失败节点和 RCA 线索。"""

    def setUp(self) -> None:
        """创建内存数据库，避免影响真实环境 Trace 数据。"""

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()

    def tearDown(self) -> None:
        """关闭测试数据库会话。"""

        self.db.close()

    def test_analyze_recent_extracts_slow_and_failed_spans(self) -> None:
        """最近 Trace 分析应输出慢 span、失败 span、Top operation 和建议动作。"""

        run = TraceRun(id="trace-1", status="failed", total_duration_ms=4200, total_tokens=1000, cost=0.02)
        self.db.add(run)
        self.db.add_all(
            [
                TraceSpan(
                    id="span-1",
                    trace_id="trace-1",
                    operation="retrieval",
                    status="success",
                    duration_ms=1800,
                    metadata_json={"input": {"query": "订单服务告警"}, "output": {"chunks": ["a", "b"]}},
                ),
                TraceSpan(
                    id="span-2",
                    trace_id="trace-1",
                    operation="tool_call",
                    status="failed",
                    duration_ms=300,
                    error_message="connection refused",
                    metadata_json={"context": {"tool": "api_health_check"}},
                ),
                TraceSpan(
                    id="span-3",
                    trace_id="trace-1",
                    operation="llm",
                    status="success",
                    duration_ms=2100,
                    metadata_json={"input": {"model": "qwen-plus"}, "output": {"answerPreview": "分析结果"}},
                ),
            ]
        )
        self.db.commit()

        result = TraceAnalysisService(self.db).analyze_recent(limit=10, slow_threshold_ms=1000)

        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["data"]["runCount"], 1)
        self.assertEqual(result["data"]["spanCount"], 3)
        self.assertEqual(result["data"]["errorSpans"][0]["operation"], "tool_call")
        slow_operations = {item["operation"] for item in result["data"]["slowSpans"]}
        self.assertIn("retrieval", slow_operations)
        self.assertIn("llm", slow_operations)
        self.assertTrue(any(item["operation"] == "llm" for item in result["data"]["topOperations"]))
        self.assertTrue(any("失败 span" in item for item in result["data"]["rootCauseHints"]))
        self.assertTrue(any("Trace trace-1" in item for item in result["data"]["recommendedNextSteps"]))

    def test_analyze_recent_returns_data_gap_when_empty(self) -> None:
        """没有 Trace 数据时应返回健康降级提示，而不是抛异常。"""

        result = TraceAnalysisService(self.db).analyze_recent()

        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["data"]["runCount"], 0)
        self.assertIn("暂无 TraceRun 数据", result["data"]["dataGaps"])


if __name__ == "__main__":
    unittest.main()
