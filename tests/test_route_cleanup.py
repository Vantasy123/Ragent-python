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
    """验证旧接口已移除，当前统一入口仍保留。"""

    def test_current_api_routes_are_registered(self) -> None:
        self.assertIn("POST", route_methods("/api/agent/chat"))
        self.assertIn("GET", route_methods("/api/conversations"))
        self.assertIn("GET", route_methods("/api/intent-tree"))

    def test_legacy_routes_are_removed(self) -> None:
        self.assertEqual(route_methods("/rag/v3/chat"), set())
        self.assertEqual(route_methods("/api/rag/v3/chat"), set())
        self.assertEqual(route_methods("/api/rag/v3/stop"), set())
        self.assertEqual(route_methods("/api/workflow/chat"), set())
        self.assertEqual(route_methods("/api/sessions"), set())
        self.assertEqual(route_methods("/agent/chat"), set())
        self.assertEqual(route_methods("/intent-tree"), set())
        self.assertEqual(route_methods("/api/intent-tree/trees"), set())


if __name__ == "__main__":
    unittest.main()
