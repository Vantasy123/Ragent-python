from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch, MagicMock

from app.core.config import settings
from app.rag.retrieval.reranker import RerankerService


def fake_flag_embedding_module(scores: list[float]) -> types.ModuleType:
    """构造假的 FlagEmbedding 模块，避免测试下载真实模型。"""

    module = types.ModuleType("FlagEmbedding")

    class FakeFlagReranker:
        """模拟 FlagReranker 的 compute_score 行为。"""

        def __init__(self, model_name: str, use_fp16: bool = False) -> None:
            self.model_name = model_name
            self.use_fp16 = use_fp16

        def compute_score(self, pairs, normalize: bool = True):
            return scores

    module.FlagReranker = FakeFlagReranker
    return module


class RerankerServiceTest(unittest.TestCase):
    """验证模型重排、API 重排和词项回退排序。"""

    def test_siliconflow_api_rerank(self) -> None:
        """测试 SiliconFlow 云端 API 重排。"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"index": 0, "relevance_score": 0.1},
                {"index": 1, "relevance_score": 0.95},
                {"index": 2, "relevance_score": 0.4},
            ]
        }

        with patch("requests.post", return_value=mock_response):
            with patch.object(settings, "RERANK_PROVIDER", "siliconflow"):
                with patch.object(settings, "RERANK_API_KEY", "sk-mock-key"):
                    result = RerankerService().rerank_with_threshold(
                        "数据库连接失败",
                        ["网络正常", "数据库连接超时", "登录失败"],
                        threshold=0.0,
                    )

        self.assertEqual([item["index"] for item in result], [1, 2, 0])
        self.assertTrue(all(item["source"] == "siliconflow" for item in result))

    def test_model_rerank_sorts_by_model_score(self) -> None:
        """测试 FlagEmbedding 本地模型重排。"""
        module = fake_flag_embedding_module([0.1, 0.9, 0.4])
        with patch.object(settings, "RERANK_PROVIDER", "flag_embedding"):
            with patch.dict(sys.modules, {"FlagEmbedding": module}):
                result = RerankerService().rerank_with_threshold(
                    "数据库连接失败",
                    ["网络正常", "数据库连接超时", "登录失败"],
                    threshold=0.0,
                )

        self.assertEqual([item["index"] for item in result], [1, 2, 0])
        self.assertTrue(all(item["source"] == "model" for item in result))

    def test_lexical_fallback_prefers_query_overlap(self) -> None:
        """测试词项重排兜底。"""
        with patch.object(settings, "RERANK_PROVIDER", "flag_embedding"):
            with patch.dict(sys.modules, {"FlagEmbedding": None}):
                result = RerankerService().rerank_with_threshold(
                    "数据库连接失败",
                    ["前端页面样式说明", "数据库连接失败排查步骤", "用户登录流程"],
                    threshold=0.7,
                )

        self.assertEqual(result[0]["index"], 1)
        self.assertTrue(all(item["source"] == "lexical" for item in result))


if __name__ == "__main__":
    unittest.main()
