from __future__ import annotations

import unittest
import sys
import types

if "pymilvus" not in sys.modules:
    # 路由表测试只需要导入 FastAPI app；这里模拟 Milvus 依赖，避免单测环境必须安装完整向量库客户端。
    fake_pymilvus = types.ModuleType("pymilvus")
    fake_pymilvus.Collection = object
    fake_pymilvus.CollectionSchema = object
    fake_pymilvus.FieldSchema = object
    fake_pymilvus.connections = object()
    fake_pymilvus.utility = object()
    fake_pymilvus.DataType = types.SimpleNamespace(VARCHAR="VARCHAR", INT64="INT64", FLOAT_VECTOR="FLOAT_VECTOR", JSON="JSON")
    sys.modules["pymilvus"] = fake_pymilvus

from app.main import app


def route_methods(path: str) -> set[str]:
    """读取 FastAPI 路由表中指定路径支持的方法，避免真实启动服务。"""

    methods: set[str] = set()
    for route in app.routes:
        if getattr(route, "path", "") == path:
            methods.update(getattr(route, "methods", set()) or set())
    return methods


class RouteCleanupTest(unittest.TestCase):
    """验证求职核心与评估体系接口已注册，旧运维接口已彻底削减。"""

    def test_current_api_routes_are_registered(self) -> None:
        # 求职 Agent 核心路由
        self.assertIn("POST", route_methods("/api/agent/chat"))
        self.assertIn("GET", route_methods("/api/conversations"))
        self.assertIn("GET", route_methods("/api/jobs/resumes"))
        self.assertIn("POST", route_methods("/api/jobs/resumes/parse"))
        self.assertIn("GET", route_methods("/api/jobs/postings"))
        self.assertIn("POST", route_methods("/api/jobs/matching/analyze"))
        self.assertIn("GET", route_methods("/api/jobs/applications"))
        self.assertIn("GET", route_methods("/api/jobs/interviews/sessions"))
        self.assertIn("POST", route_methods("/api/jobs/autofill/payload"))

        # 智能体评估与测评中心（必须保留）
        self.assertIn("GET", route_methods("/api/admin/evaluations/datasets"))
        self.assertIn("POST", route_methods("/api/admin/evaluations/datasets/{dataset_id}/runs"))
        self.assertIn("GET", route_methods("/api/admin/evaluations/batch-runs"))

        # 系统与安全审计
        self.assertIn("GET", route_methods("/api/admin/project-config/status"))
        self.assertIn("PUT", route_methods("/api/admin/project-config/servers"))
        self.assertIn("GET", route_methods("/api/admin/security-audit/events"))

    def test_legacy_routes_are_removed(self) -> None:
        # 验证已删除的旧运维路由与意图树路由返回空
        self.assertEqual(route_methods("/api/admin/monitoring/overview"), set())
        self.assertEqual(route_methods("/api/agent/ops/runs/{run_id}/postmortem"), set())
        self.assertEqual(route_methods("/api/intent-tree"), set())
        self.assertEqual(route_methods("/rag/v3/chat"), set())
        self.assertEqual(route_methods("/api/rag/v3/chat"), set())
        self.assertEqual(route_methods("/api/rag/v3/stop"), set())


if __name__ == "__main__":
    unittest.main()
