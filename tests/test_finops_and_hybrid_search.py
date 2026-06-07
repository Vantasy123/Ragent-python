from __future__ import annotations

import sys
import types

if "pymilvus" not in sys.modules:
    fake_pymilvus = types.ModuleType("pymilvus")
    fake_pymilvus.Collection = object
    fake_pymilvus.CollectionSchema = object
    fake_pymilvus.FieldSchema = object
    fake_pymilvus.connections = object()
    fake_pymilvus.utility = object()
    fake_pymilvus.DataType = types.SimpleNamespace(VARCHAR="VARCHAR", INT64="INT64", FLOAT_VECTOR="FLOAT_VECTOR", JSON="JSON")
    sys.modules["pymilvus"] = fake_pymilvus


import unittest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.domain.models import KnowledgeBase, TraceRun, TraceSpan, User
from app.services.trace_service import CostEstimator, TraceService, TraceSpanHandle
from app.services.dashboard_service import DashboardService
from app.rag.retrieval.multi_channel_retriever import MultiChannelRetriever, RetrievedChunk
from app.api.routers.knowledge import router as knowledge_router
from fastapi.testclient import TestClient
from fastapi import FastAPI
from app.core.database import get_db
from app.services.dependencies import require_admin


class FinOpsAndHybridSearchTest(unittest.TestCase):
    """验证混合检索调参和 FinOps Token 计费与算力审计功能。"""

    def setUp(self) -> None:
        """创建独立的内存 SQLite 数据库用于单测。"""
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        # 初始化测试用管理员
        self.admin = User(id="admin-1", username="admin", password_hash="hash", role="admin", is_active=True)
        self.db.add(self.admin)
        self.db.commit()

    def tearDown(self) -> None:
        """清理连接。"""
        self.db.close()

    def test_cost_estimator_pricing(self) -> None:
        """验证 CostEstimator 对主流模型的算费逻辑符合预设标准。"""
        # qwen-plus: input=0.004/1k, output=0.012/1k
        cost_plus = CostEstimator.estimate_cost("qwen-plus", 2000, 3000)
        self.assertEqual(cost_plus, round(2 * 0.004 + 3 * 0.012, 6))

        # text-embedding-v3: input=0.0007/1k, output=0
        cost_emb = CostEstimator.estimate_cost("text-embedding-v3", 10000, 0)
        self.assertEqual(cost_emb, round(10 * 0.0007, 6))

        # gpt-4o: input=0.035/1k, output=0.105/1k
        cost_gpt = CostEstimator.estimate_cost("gpt-4o", 1000, 1000)
        self.assertEqual(cost_gpt, round(1 * 0.035 + 1 * 0.105, 6))

        # 降级情况：默认降级为 qwen-plus
        cost_unknown = CostEstimator.estimate_cost("unknown-model", 1000, 1000)
        self.assertEqual(cost_unknown, round(1 * 0.004 + 1 * 0.012, 6))

    def test_trace_service_token_parsing_and_redact(self) -> None:
        """验证 TraceService 能够自动解析 Usage 并估算非结构化模型的 Token 消耗。"""
        trace_service = TraceService(self.db)
        
        # 1. 结构化 Usage 解析测试
        handle = TraceSpanHandle(
            trace_id="run-1",
            operation="llm",
            input_data={"query": "test"},
            context_data={"model": "gpt-4o"}
        )
        
        output_data = {"text": "hello", "usage": {"prompt_tokens": 15, "completion_tokens": 25}}
        prompt, completion, model = trace_service._parse_tokens(handle, output_data)
        
        self.assertEqual(prompt, 15)
        self.assertEqual(completion, 25)
        self.assertEqual(model, "gpt-4o")

        # 2. 降级估算测试（无 usage 字段，基于汉字/英文字符估算）
        handle_fallback = TraceSpanHandle(
            trace_id="run-2",
            operation="llm",
            input_data={"query": "你好世界！Hello"},  # 中文 5 字符，英文/标点 5 字符
            context_data={"model": "qwen-plus"}
        )
        output_fallback = {"content": "这是回答文本。It is correct."}  # 中文 7 字符，英文/标点 14 字符
        
        p_est, c_est, model = trace_service._parse_tokens(handle_fallback, output_fallback)
        self.assertTrue(p_est > 0)
        self.assertTrue(c_est > 0)
        self.assertEqual(model, "qwen-plus")

    def test_trace_service_db_persistence(self) -> None:
        """验证 Trace 结束时，Token 用量和费用成本能够聚合落库。"""
        trace_service = TraceService(self.db)
        run = trace_service.start_run(session_id="session-1")

        # 创建并完成第一个 Span (Embedding)
        emb_handle = trace_service.create_span(run.id, "embedding", input_data={"query": "test query"}, metadata={"model": "text-embedding-v3"})
        trace_service.complete_span(emb_handle, output_data={"usage": {"prompt_tokens": 2000, "completion_tokens": 0}})

        # 创建并完成第二个 Span (LLM Chat)
        chat_handle = trace_service.create_span(emb_handle.trace_id, "llm", input_data={"query": "test query"}, metadata={"model": "qwen-plus"})
        trace_service.complete_span(chat_handle, output_data={"usage": {"prompt_tokens": 1000, "completion_tokens": 2000}})

        # 完成此次 Trace
        trace_service.complete_run(run.id, "success")

        # 重新从数据库读取 TraceRun
        db_run = self.db.query(TraceRun).filter(TraceRun.id == run.id).first()
        self.assertEqual(db_run.prompt_tokens, 3000)
        self.assertEqual(db_run.completion_tokens, 2000)
        self.assertEqual(db_run.total_tokens, 5000)
        
        # 成本验证: 2k embedding = 2 * 0.0007 = 0.0014, 
        # 1k input qwen-plus + 2k output = 1 * 0.004 + 2 * 0.012 = 0.028,
        # 总费用应为 0.0294 元
        self.assertAlmostEqual(db_run.cost, 0.0014 + 0.028, places=4)

    def test_knowledge_base_dynamic_config_api(self) -> None:
        """测试知识库接口的混合检索与重排配置参数的创建、修改和读取。"""
        # 创建 FastAPI 应用并挂载知识库路由
        app = FastAPI()
        app.include_router(knowledge_router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[require_admin] = lambda: self.admin

        client = TestClient(app)

        # 1. 测试创建包含动态检索参数的知识库
        payload = {
            "name": "计费与检索调参测试知识库",
            "description": "企业商业测试",
            "embedding_model": "text-embedding-v3",
            "vector_weight": 0.8,
            "bm25_weight": 0.2,
            "rerank_enabled": True,
            "rerank_threshold": 0.35,
            "top_k": 15
        }
        response = client.post("/knowledge-base", json=payload)
        self.assertEqual(response.status_code, 200)
        kb_id = response.json()["data"]["id"]

        # 2. 测试获取详情能正确暴露新字段
        get_response = client.get(f"/knowledge-base/{kb_id}")
        self.assertEqual(get_response.status_code, 200)
        kb_data = get_response.json()["data"]
        self.assertEqual(kb_data["vectorWeight"], 0.8)
        self.assertEqual(kb_data["bm25Weight"], 0.2)
        self.assertEqual(kb_data["rerankEnabled"], True)
        self.assertEqual(kb_data["rerankThreshold"], 0.35)
        self.assertEqual(kb_data["topK"], 15)

        # 3. 测试更新参数字段
        update_payload = {
            "name": "修改后的计费与检索调参测试知识库",
            "vector_weight": 0.3,
            "bm25_weight": 0.7,
            "rerank_threshold": 0.6,
            "top_k": 5
        }
        put_response = client.put(f"/knowledge-base/{kb_id}", json=update_payload)
        self.assertEqual(put_response.status_code, 200)

        # 重新获取详情验证修改
        get_response_2 = client.get(f"/knowledge-base/{kb_id}")
        kb_data_2 = get_response_2.json()["data"]
        self.assertEqual(kb_data_2["vectorWeight"], 0.3)
        self.assertEqual(kb_data_2["bm25Weight"], 0.7)
        self.assertEqual(kb_data_2["rerankThreshold"], 0.6)
        self.assertEqual(kb_data_2["topK"], 5)

    def test_multi_channel_retriever_dynamic_weights(self) -> None:
        """测试 MultiChannelRetriever 能够正确读取数据库特定知识库的动态融合权重。"""
        # 写入知识库配置到内存库
        kb = KnowledgeBase(
            id="kb-test-1",
            name="特定检索测试库",
            collection_name="kb-test-1-collection",
            vector_weight=0.75,
            bm25_weight=0.25,
            top_k=12
        )
        self.db.add(kb)
        self.db.commit()

        retriever = MultiChannelRetriever()
        
        # 1. 验证 _get_kb_config 辅助方法
        cfg = retriever._get_kb_config(self.db, "kb-test-1")
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg["vector_weight"], 0.75)
        self.assertEqual(cfg["bm25_weight"], 0.25)
        self.assertEqual(cfg["top_k"], 12)

        # 2. 验证 _rrf_fuse 融合权重分配
        vector_chunks = [RetrievedChunk("A", 0.9, {"chunk_id": "1"}, "vector")]
        keyword_chunks = [RetrievedChunk("B", 0.8, {"chunk_id": "2"}, "keyword")]
        
        # 使用配置中的 0.75 和 0.25 权重融合
        fused = retriever._rrf_fuse(vector_chunks, keyword_chunks, top_k=2, vector_weight=0.75, bm25_weight=0.25)
        self.assertEqual(len(fused), 2)
        
        # A 排名第一，在 vector 列表中位置是 rank 1，分数为 0.75 * (1 / (60 + 1))
        # B 排名第一，在 keyword 列表中位置是 rank 1，分数为 0.25 * (1 / (60 + 1))
        score_a = fused[0].score if fused[0].content == "A" else fused[1].score
        score_b = fused[0].score if fused[0].content == "B" else fused[1].score
        self.assertAlmostEqual(score_a, 0.75 * (1.0 / (60 + 1)), places=6)
        self.assertAlmostEqual(score_b, 0.25 * (1.0 / (60 + 1)), places=6)

    def test_dashboard_finops_endpoints(self) -> None:
        """验证 DashboardService 的 FinOps 看板统计能精确产出聚合报告。"""
        # 写入一些测试 Trace 记录
        from app.core.time_utils import utc_now_naive
        now = utc_now_naive()
        r1 = TraceRun(id="t-1", prompt_tokens=1000, completion_tokens=2000, total_tokens=3000, cost=0.016, created_at=now)
        r2 = TraceRun(id="t-2", prompt_tokens=2000, completion_tokens=4000, total_tokens=6000, cost=0.032, created_at=now)
        self.db.add(r1)
        self.db.add(r2)
        
        # 写入一条 Span 用来统计模型占比
        s1 = TraceSpan(id="s-1", trace_id="t-1", operation="llm", cost=0.016, metadata_json={"context": {"model": "qwen-plus"}})
        self.db.add(s1)
        self.db.commit()

        service = DashboardService(self.db)
        stats = service.finops_stats()

        self.assertEqual(stats["totalTokens"], 9000)
        self.assertEqual(stats["promptTokens"], 3000)
        self.assertEqual(stats["completionTokens"], 6000)
        self.assertAlmostEqual(stats["totalCost"], 0.048, places=4)
        self.assertEqual(stats["todayCost"], 0.048)

        # 检查大模型用量占比
        self.assertTrue(len(stats["modelDistribution"]) > 0)
        self.assertEqual(stats["modelDistribution"][0]["model"], "qwen-plus")
        self.assertEqual(stats["modelDistribution"][0]["cost"], 0.016)


if __name__ == "__main__":
    unittest.main()
