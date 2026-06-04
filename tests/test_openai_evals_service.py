from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base
from app.domain.models import EvaluationBatchRun, EvaluationCase, EvaluationCaseResult, EvaluationDataset
from app.services.openai_evals_service import OpenAIEvalsService


class FakeOpenAIEvalsService(OpenAIEvalsService):
    """用内存响应替代真实 OpenAI 网络请求，保持测试稳定。"""

    def __init__(self, db):
        """保存请求记录，便于断言服务调用顺序。"""

        super().__init__(db)
        self.calls: list[tuple[str, str, dict | None]] = []

    def _request_json(self, method: str, path: str, payload: dict | None = None) -> dict:
        """根据请求路径返回模拟的 OpenAI Evals 响应。"""

        self.calls.append((method, path, payload))
        if method == "POST" and path == "/evals":
            return {"id": "eval_123"}
        if method == "POST" and path == "/evals/eval_123/runs":
            return {"id": "run_123", "status": "queued", "result_counts": {"total": 1}}
        if method == "GET" and path == "/evals/eval_123/runs/run_123":
            return {"id": "run_123", "status": "completed", "report_url": "https://platform.openai.com/evals/run_123"}
        return {}


class OpenAIEvalsServiceTest(unittest.TestCase):
    """验证 OpenAI Evals 适配层的 payload、开关和状态同步逻辑。"""

    def setUp(self) -> None:
        """创建独立数据库和一条已完成的本地批次结果。"""

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.dataset = EvaluationDataset(name="线上验收集")
        self.case = EvaluationCase(
            dataset=self.dataset,
            question="如何判断服务是否恢复？",
            expected_answer="检查健康探针和错误率",
            expected_keywords=["健康探针", "错误率"],
        )
        self.batch = EvaluationBatchRun(dataset=self.dataset, status="completed", total_cases=1, completed_cases=1)
        self.result = EvaluationCaseResult(
            batch_run=self.batch,
            case=self.case,
            status="completed",
            question=self.case.question,
            answer="服务已经恢复，健康探针正常，错误率回落。",
            expected_answer=self.case.expected_answer,
            overall_score=0.9,
        )
        self.db.add_all([self.dataset, self.case, self.batch, self.result])
        self.db.commit()
        self.old_enabled = settings.OPENAI_EVALS_ENABLED
        self.old_key = settings.OPENAI_EVALS_API_KEY

    def tearDown(self) -> None:
        """恢复全局配置并关闭数据库。"""

        settings.OPENAI_EVALS_ENABLED = self.old_enabled
        settings.OPENAI_EVALS_API_KEY = self.old_key
        self.db.close()

    def test_preview_builds_custom_eval_payload_without_remote_call(self) -> None:
        """预览应生成 custom eval 和 jsonl run 数据源，但不要求启用 OpenAI Evals。"""

        service = OpenAIEvalsService(self.db)

        preview = service.preview_batch_payload(self.batch.id)

        self.assertFalse(preview["enabled"])
        self.assertEqual(preview["itemCount"], 1)
        self.assertEqual(preview["evalPayload"]["data_source_config"]["type"], "custom")
        item = preview["runPayload"]["data_source"]["source"]["content"][0]["item"]
        self.assertEqual(item["question"], self.case.question)
        self.assertEqual(item["answer"], self.result.answer)

    def test_start_requires_feature_flag_and_api_key(self) -> None:
        """未开启远程开关时，启动 OpenAI Evals 应给出明确错误。"""

        settings.OPENAI_EVALS_ENABLED = False
        settings.OPENAI_EVALS_API_KEY = "test-key"

        with self.assertRaisesRegex(ValueError, "未启用"):
            OpenAIEvalsService(self.db).start_batch_eval(self.batch.id)

    def test_start_and_sync_write_remote_state_to_batch(self) -> None:
        """启动和同步应把 eval id、run id、状态和报告信息写回本地批次。"""

        settings.OPENAI_EVALS_ENABLED = True
        settings.OPENAI_EVALS_API_KEY = "test-key"
        service = FakeOpenAIEvalsService(self.db)

        started = service.start_batch_eval(self.batch.id)
        synced = service.sync_batch_eval(self.batch.id)

        self.assertEqual(started["evalId"], "eval_123")
        self.assertEqual(started["runId"], "run_123")
        self.assertEqual(synced["status"], "completed")
        self.assertEqual(synced["report"]["reportUrl"], "https://platform.openai.com/evals/run_123")
        self.assertEqual([call[1] for call in service.calls], ["/evals", "/evals/eval_123/runs", "/evals/eval_123/runs/run_123"])


if __name__ == "__main__":
    unittest.main()
