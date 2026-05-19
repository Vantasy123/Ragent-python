from __future__ import annotations

import unittest

from app.services.chat_service import _build_source_items, _format_sources_block


class FakeChunk:
    """模拟检索命中的片段，避免测试依赖向量库或数据库。"""

    def __init__(self) -> None:
        self.content = "后端服务启动后会注册 RAG 路由，并通过知识库检索补充回答。"
        self.score = 0.87
        self.channel = "hybrid"
        self.metadata = {
            "source": "系统运行手册.md",
            "doc_id": "doc-1",
            "kb_id": "kb-1",
            "chunk_id": "chunk-1",
            "chunkIndex": 2,
        }


class ChatSourceTest(unittest.TestCase):
    """验证普通 RAG 回答能够生成稳定的来源出处。"""

    def test_build_source_items_keeps_display_fields(self) -> None:
        sources = _build_source_items([FakeChunk()])

        self.assertEqual(sources[0]["index"], 1)
        self.assertEqual(sources[0]["title"], "系统运行手册.md")
        self.assertEqual(sources[0]["chunkIndex"], 2)
        self.assertEqual(sources[0]["channel"], "hybrid")
        self.assertIn("后端服务启动", sources[0]["preview"])

    def test_format_sources_block_outputs_user_visible_citations(self) -> None:
        block = _format_sources_block(_build_source_items([FakeChunk()]))

        self.assertIn("来源出处", block)
        self.assertIn("[1] 系统运行手册.md，片段 3，通道：hybrid", block)

    def test_format_sources_block_reports_empty_sources(self) -> None:
        block = _format_sources_block([])

        self.assertIn("来源出处", block)
        self.assertIn("未检索到可用知识库来源", block)


if __name__ == "__main__":
    unittest.main()
