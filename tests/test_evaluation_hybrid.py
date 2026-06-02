from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base
from app.domain.models import EvaluationBatchRun, EvaluationCase, EvaluationCaseResult, EvaluationDataset
from app.services.evaluation_service import EvaluationService


class HybridEvaluationMetricTest(unittest.IsolatedAsyncioTestCase):
    """验证离线混合评估指标和批次聚合逻辑。"""

    def setUp(self) -> None:
        """为每个测试创建独立内存数据库，避免污染本地开发数据。"""

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.dataset = EvaluationDataset(name="回归评估集")
        self.case = EvaluationCase(
            dataset=self.dataset,
            question="如何提升检索相关性？",
            expected_answer="使用重排模型提升相关性",
            expected_chunk_ids=["chunk-2"],
            expected_keywords=["重排"],
        )
        self.db.add_all([self.dataset, self.case])
        self.db.commit()

    def tearDown(self) -> None:
        """关闭测试数据库连接。"""

        self.db.close()

    async def test_retrieval_metrics_use_expected_chunk_ids_and_keywords(self) -> None:
        """检索命中、召回、MRR 和上下文指标应按期望片段与关键词计算。"""

        service = EvaluationService(self.db)
        metrics, issues, score = await service.evaluate_case_metrics(
            self.case,
            "可以通过重排模型提升相关性。",
            [
                {"chunkId": "chunk-1", "preview": "普通召回片段"},
                {"chunkId": "chunk-2", "preview": "重排模型可以提升相关性"},
            ],
            trace=None,
        )

        self.assertEqual(metrics["hit_at_k"]["score"], 1.0)
        self.assertEqual(metrics["recall_at_k"]["score"], 1.0)
        self.assertEqual(metrics["mrr"]["score"], 0.5)
        self.assertEqual(metrics["context_precision"]["score"], 0.5)
        self.assertGreater(score, 0.0)
        self.assertTrue(any(issue["issueKey"] == "low_trace_success" for issue in issues))

    async def test_missing_expected_chunk_ids_skips_chunk_based_metrics(self) -> None:
        """未配置期望片段时，chunkId 指标应跳过且不参与归一化。"""

        self.case.expected_chunk_ids = []
        service = EvaluationService(self.db)

        metrics, _, score = await service.evaluate_case_metrics(self.case, "答案提到了重排。", [], trace=None)

        self.assertEqual(metrics["hit_at_k"]["status"], "skipped")
        self.assertEqual(metrics["mrr"]["status"], "skipped")
        self.assertGreaterEqual(score, 0.0)

    async def test_invalid_judge_response_is_skipped(self) -> None:
        """裁判模型返回非法 JSON 时应降级为 skipped，而不是让评估失败。"""

        old_openai_key = settings.OPENAI_API_KEY
        old_siliconflow_key = settings.SILICONFLOW_API_KEY
        settings.OPENAI_API_KEY = "test-key"
        settings.SILICONFLOW_API_KEY = ""
        service = EvaluationService(self.db)
        async def mock_call(*_args, **_kwargs):
            return "不是 JSON"
        service._call_judge_model = mock_call  # type: ignore[method-assign]
        try:
            metrics, issues, _ = await service.evaluate_case_metrics(self.case, "答案", [], trace=None)
        finally:
            settings.OPENAI_API_KEY = old_openai_key
            settings.SILICONFLOW_API_KEY = old_siliconflow_key

        self.assertEqual(metrics["faithfulness"]["status"], "skipped")
        self.assertTrue(any(issue["issueKey"] == "judge_skipped" for issue in issues))

    def test_batch_with_failed_case_becomes_completed_with_errors(self) -> None:
        """批次存在失败用例时，最终状态应明确标记为部分失败。"""

        batch = EvaluationBatchRun(dataset=self.dataset, total_cases=2)
        ok = EvaluationCaseResult(batch_run=batch, case=self.case, status="completed", overall_score=0.8, metrics={"hit_at_k": {"status": "completed", "score": 1.0}})
        failed = EvaluationCaseResult(batch_run=batch, case=self.case, status="failed", error_message="boom")
        self.db.add_all([batch, ok, failed])
        self.db.commit()

        service = EvaluationService(self.db)
        service._finalize_batch(batch)

        self.assertEqual(batch.status, "completed_with_errors")
        self.assertEqual(batch.completed_cases, 1)
        self.assertEqual(batch.failed_cases, 1)
        self.assertEqual(batch.overall_score, 0.8)


if __name__ == "__main__":
    unittest.main()
