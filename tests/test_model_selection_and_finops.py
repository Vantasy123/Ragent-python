from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.domain.models import Conversation, ConversationMessage, TraceRun, TraceSpan, User
from app.services.trace_service import CostEstimator, TraceService
from app.services.dashboard_service import DashboardService
from app.api.routers.unified_chat import PRESET_MODELS, UnifiedChatRequest


class ModelSelectionAndFinOpsTest(unittest.TestCase):
    """测试多模型选择能力、单价矩阵与 FinOps 计费审计机制。"""

    def setUp(self) -> None:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()

    def tearDown(self) -> None:
        self.db.close()

    def test_cost_estimator_pricing_matrix(self) -> None:
        """验证各主流模型的 Token 计费单价估算准确性。"""
        # 1. DeepSeek R1: input 0.004/1k, output 0.016/1k
        cost_r1 = CostEstimator.estimate_cost("deepseek-ai/DeepSeek-R1", 1000, 1000)
        self.assertAlmostEqual(cost_r1, 0.020, places=4)

        # 2. DeepSeek V3: input 0.002/1k, output 0.008/1k
        cost_v3 = CostEstimator.estimate_cost("deepseek-ai/DeepSeek-V3", 2000, 1000)
        self.assertAlmostEqual(cost_v3, 0.012, places=4)

        # 3. Qwen 2.5 14B: input 0.002/1k, output 0.004/1k
        cost_qwen14b = CostEstimator.estimate_cost("Qwen/Qwen2.5-14B-Instruct", 1000, 2000)
        self.assertAlmostEqual(cost_qwen14b, 0.010, places=4)

        # 4. Qwen 2.5 72B: input 0.004/1k, output 0.012/1k
        cost_qwen72b = CostEstimator.estimate_cost("Qwen/Qwen2.5-72B-Instruct", 1000, 1000)
        self.assertAlmostEqual(cost_qwen72b, 0.016, places=4)

        # 5. BGE-M3 (Embedding): input 0.0005/1k, output 0.0
        cost_bge = CostEstimator.estimate_cost("BAAI/bge-m3", 10000, 0)
        self.assertAlmostEqual(cost_bge, 0.005, places=4)

    def test_preset_models_metadata_completeness(self) -> None:
        """验证预置模型列表包含完整元数据与合理的计费标签。"""
        self.assertGreaterEqual(len(PRESET_MODELS), 8)
        model_ids = {m["id"] for m in PRESET_MODELS}
        self.assertIn("Qwen/Qwen2.5-14B-Instruct", model_ids)
        self.assertIn("deepseek-ai/DeepSeek-R1", model_ids)
        self.assertIn("deepseek-ai/DeepSeek-V3", model_ids)

        for m in PRESET_MODELS:
            self.assertTrue(m.get("name"))
            self.assertTrue(m.get("provider"))
            self.assertTrue(m.get("pricingTag"))
            self.assertGreater(m.get("inputPrice", 0), 0)
            self.assertGreater(m.get("outputPrice", 0), 0)

    def test_unified_chat_request_accepts_model(self) -> None:
        """验证聊天请求体正确解析与校验 model 参数。"""
        req = UnifiedChatRequest(
            message="帮我修改简历",
            mode="job",
            model="deepseek-ai/DeepSeek-R1",
        )
        self.assertEqual(req.model, "deepseek-ai/DeepSeek-R1")

    def test_finops_stats_aggregates_custom_models(self) -> None:
        """验证后台 FinOps 看板能正确按不同模型聚合算力成本。"""
        run = TraceRun(id="run-1", prompt_tokens=2000, completion_tokens=1000, total_tokens=3000, cost=0.02, status="success")
        self.db.add(run)

        span_r1 = TraceSpan(
            id="span-1",
            trace_id="run-1",
            operation="generation",
            cost=0.016,
            metadata_json={"input": {"model": "deepseek-ai/DeepSeek-R1"}},
        )
        span_bge = TraceSpan(
            id="span-2",
            trace_id="run-1",
            operation="embedding",
            cost=0.004,
            metadata_json={"input": {"model": "BAAI/bge-m3"}},
        )
        self.db.add_all([span_r1, span_bge])
        self.db.commit()

        stats = DashboardService(self.db).finops_stats()
        self.assertAlmostEqual(stats["totalCost"], 0.02, places=4)
        self.assertEqual(stats["totalTokens"], 3000)

        distribution = {item["model"]: item["cost"] for item in stats["modelDistribution"]}
        self.assertIn("deepseek-ai/DeepSeek-R1", distribution)
        self.assertAlmostEqual(distribution["deepseek-ai/DeepSeek-R1"], 0.016, places=4)
        self.assertIn("BAAI/bge-m3", distribution)
        self.assertAlmostEqual(distribution["BAAI/bge-m3"], 0.004, places=4)


if __name__ == "__main__":
    unittest.main()
