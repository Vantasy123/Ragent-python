from __future__ import annotations

import asyncio
import threading
import time
import unittest
from datetime import datetime
from types import SimpleNamespace

from app.rag.retrieval import keyword_bm25
from app.rag.retrieval.keyword_bm25 import KeywordBM25Retriever


class FakeBM25:
    """测试用 BM25 替身，只统计构建次数并按词重叠打分。"""

    build_count = 0

    def __init__(self, corpus_tokens: list[list[str]]) -> None:
        FakeBM25.build_count += 1
        self.corpus_tokens = corpus_tokens

    def get_scores(self, query_tokens: list[str]) -> list[float]:
        """按查询词和语料词的交集数量返回稳定分数。"""

        query_set = set(query_tokens)
        return [float(len(query_set.intersection(tokens))) for tokens in self.corpus_tokens]


class KeywordBM25CacheTest(unittest.IsolatedAsyncioTestCase):
    """验证 BM25 缓存复用和并发构建互斥。"""

    def setUp(self) -> None:
        """隔离全局缓存和可选依赖，避免测试之间互相污染。"""

        self.old_bm25 = keyword_bm25.BM25Okapi
        self.old_jieba = keyword_bm25.jieba
        keyword_bm25.BM25Okapi = FakeBM25
        keyword_bm25.jieba = None
        KeywordBM25Retriever._cache = {}
        KeywordBM25Retriever._locks = {}
        FakeBM25.build_count = 0

    def tearDown(self) -> None:
        """恢复模块级依赖。"""

        keyword_bm25.BM25Okapi = self.old_bm25
        keyword_bm25.jieba = self.old_jieba

    async def test_empty_cache_entry_is_reused_until_data_changes(self) -> None:
        """没有可用分块时也要缓存空结果，避免每次查询都打数据库。"""

        retriever = KeywordBM25Retriever()
        load_count = 0

        def load_chunks(_kb_id: str | None):
            nonlocal load_count
            load_count += 1
            return []

        retriever._load_chunks = load_chunks  # type: ignore[method-assign]
        retriever._get_latest_update_time = lambda _kb_id: None  # type: ignore[method-assign]

        self.assertEqual(await retriever.retrieve("alpha", kb_id="kb-1"), [])
        self.assertEqual(await retriever.retrieve("alpha", kb_id="kb-1"), [])
        self.assertEqual(load_count, 1)

    async def test_concurrent_cache_miss_builds_index_once(self) -> None:
        """多个请求同时命中缓存失效时，只允许一个协程重建索引。"""

        retriever = KeywordBM25Retriever()
        latest_update = datetime(2026, 6, 1, 23, 30)
        load_count = 0
        load_lock = threading.Lock()
        row = SimpleNamespace(
            content="alpha beta",
            meta_data={},
            id="chunk-1",
            kb_id="kb-1",
            doc_id="doc-1",
            chunk_index=0,
        )

        def load_chunks(_kb_id: str | None):
            nonlocal load_count
            time.sleep(0.05)
            with load_lock:
                load_count += 1
            return [row]

        retriever._load_chunks = load_chunks  # type: ignore[method-assign]
        retriever._get_latest_update_time = lambda _kb_id: latest_update  # type: ignore[method-assign]

        results = await asyncio.gather(*[retriever.retrieve("alpha", kb_id="kb-1") for _ in range(5)])

        self.assertEqual(load_count, 1)
        self.assertEqual(FakeBM25.build_count, 1)
        self.assertTrue(all(items and items[0].metadata["chunk_id"] == "chunk-1" for items in results))


if __name__ == "__main__":
    unittest.main()
