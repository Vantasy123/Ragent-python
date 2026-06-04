from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base
from app.domain.models import EvaluationDataset, EvaluationCase, TraceRun
from app.services.evaluation_service import EvaluationService


class LangSmithIntegrationTest(unittest.IsolatedAsyncioTestCase):
    """验证 LangSmith 数据集同步、指标回传和 Run ID 捕捉功能。"""

    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        
        self.dataset = EvaluationDataset(
            name="内置运维与 RAG 核心评估集",
            description="测试描述"
        )
        self.case1 = EvaluationCase(
            dataset=self.dataset,
            question="用例问题 1",
            expected_answer="参考答案 1",
            expected_keywords=["关键词1"],
            enabled=True
        )
        self.case2 = EvaluationCase(
            dataset=self.dataset,
            question="用例问题 2",
            expected_answer="参考答案 2",
            expected_keywords=["关键词2"],
            enabled=True
        )
        self.db.add_all([self.dataset, self.case1, self.case2])
        self.db.commit()

        self.old_tracing = settings.LANGCHAIN_TRACING_V2
        self.old_key = settings.LANGCHAIN_API_KEY
        settings.LANGCHAIN_TRACING_V2 = True
        settings.LANGCHAIN_API_KEY = "ls-test-api-key"

    def tearDown(self) -> None:
        settings.LANGCHAIN_TRACING_V2 = self.old_tracing
        settings.LANGCHAIN_API_KEY = self.old_key
        self.db.close()

    @patch("langsmith.Client")
    def test_sync_to_langsmith_dataset_creates_dataset_and_examples(self, mock_client_class) -> None:
        """测试 LangSmith 数据集与用例在不存在和部分存在时的增量同步逻辑。"""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # 1. 模拟 LangSmith 中没有该数据集
        mock_client.has_dataset.return_value = False
        mock_dataset = MagicMock()
        mock_dataset.id = "ls-ds-uuid"
        mock_client.create_dataset.return_value = mock_dataset
        mock_client.list_examples.return_value = []
        
        service = EvaluationService(self.db)
        ds_id = service._sync_to_langsmith_dataset(self.dataset)
        
        self.assertEqual(ds_id, "ls-ds-uuid")
        mock_client.create_dataset.assert_called_once_with(
            dataset_name=self.dataset.name,
            description=self.dataset.description
        )
        # 应为 2 个用例都创建 example
        self.assertEqual(mock_client.create_example.call_count, 2)

        # 2. 模拟增量同步：LangSmith 已存在该数据集，且已包含其中一个用例的 question
        mock_client.reset_mock()
        mock_client.has_dataset.return_value = True
        mock_client.read_dataset.return_value = mock_dataset
        
        existing_example = MagicMock()
        existing_example.inputs = {"question": "用例问题 1"}
        mock_client.list_examples.return_value = [existing_example]
        
        ds_id = service._sync_to_langsmith_dataset(self.dataset)
        self.assertEqual(ds_id, "ls-ds-uuid")
        mock_client.create_dataset.assert_not_called()
        mock_client.read_dataset.assert_called_once_with(dataset_name=self.dataset.name)
        # 仅为“用例问题 2”创建 example，所以 create_example 调用次数为 1
        mock_client.create_example.assert_called_once()
        args, kwargs = mock_client.create_example.call_args
        self.assertEqual(kwargs["inputs"]["question"], "用例问题 2")

    @patch("langsmith.Client")
    def test_upload_metrics_to_langsmith(self, mock_client_class) -> None:
        """测试指标回传 LangSmith 作为 Feedback 的流程。"""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        metrics = {
            "hit_at_k": {"label": "命中率", "score": 1.0, "reason": "测试通过", "status": "completed"},
            "faithfulness": {"label": "忠实度", "score": None, "reason": "跳过", "status": "skipped"}
        }
        
        service = EvaluationService(self.db)
        service._upload_metrics_to_langsmith("ls-run-uuid", metrics)
        
        # 只为 completed 的指标回传 feedback，跳过 skipped
        mock_client.create_feedback.assert_called_once_with(
            run_id="ls-run-uuid",
            key="hit_at_k",
            score=1.0,
            comment="测试通过"
        )

    @patch("app.services.chat_service.stream_chat")
    async def test_execute_case_captures_langchain_run_id(self, mock_stream_chat) -> None:
        """验证使用 collect_runs 收集并返回内部 stream_chat 触发的第一个 Root Run ID。"""
        
        # 模拟 stream_chat 返回事件
        async def mock_generator(*args, **kwargs):
            yield {"type": "token", "content": "回答内容"}
            yield {"type": "final_answer", "content": "最终的参考回答"}
            yield {"traceId": "db-trace-uuid"}
            
        mock_stream_chat.side_effect = mock_generator
        
        # 模拟 collect_runs 上下文管理器
        from langchain_core.tracers.context import collect_runs
        
        # 为了测试，我们在 evaluate 运行时手动注入一个 fake run 到 collect_runs 收集器
        # 我们模拟一个 collect_runs 的上下文环境，并在其中调用 _execute_case
        service = EvaluationService(self.db)
        
        # 1. 模拟 collect_runs 返回的 Run
        class FakeRun:
            def __init__(self, id_str):
                import uuid
                self.id = uuid.UUID(id_str)
                
        fake_run = FakeRun("12345678-1234-5678-1234-567812345678")
        
        # 2. 用 patch 来模拟 collect_runs 在 with context 中的 cb 对象的 traced_runs
        class FakeCallback:
            def __init__(self):
                self.traced_runs = [fake_run]
                
            def __enter__(self):
                return self
                
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass
                
        with patch("langchain_core.tracers.context.collect_runs", return_value=FakeCallback()):
            # 模拟数据库中已存有 trace_run
            trace = TraceRun(id="db-trace-uuid", status="success")
            self.db.add(trace)
            self.db.commit()
            
            result = await service._execute_case(self.case1, "test-user-id", self.db)
            
            self.assertEqual(result["answer"], "最终的参考回答")
            self.assertEqual(result["traceId"], "db-trace-uuid")
            self.assertEqual(result["langchainRunId"], "12345678-1234-5678-1234-567812345678")


if __name__ == "__main__":
    unittest.main()
