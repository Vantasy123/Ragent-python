from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

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
    """验证模型重排和词项回退排序。"""

    def test_model_rerank_sorts_by_model_score(self) -> None:
        module = fake_flag_embedding_module([0.1, 0.9, 0.4])
        with patch.dict(sys.modules, {"FlagEmbedding": module}):
            result = RerankerService().rerank_with_threshold(
                "数据库连接失败",
                ["网络正常", "数据库连接超时", "登录失败"],
                threshold=0.0,
            )

        self.assertEqual([item["index"] for item in result], [1, 2, 0])
        self.assertTrue(all(item["source"] == "model" for item in result))

    def test_lexical_fallback_prefers_query_overlap(self) -> None:
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
