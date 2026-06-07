from __future__ import annotations

import sys
import types
import unittest

from fastapi.testclient import TestClient

if "pymilvus" not in sys.modules:
    # 分页参数测试只需要导入路由表；这里模拟 Milvus 依赖，避免单测环境必须安装向量库客户端。
    fake_pymilvus = types.ModuleType("pymilvus")
    fake_pymilvus.Collection = object
    fake_pymilvus.CollectionSchema = object
    fake_pymilvus.FieldSchema = object
    fake_pymilvus.connections = object()
    fake_pymilvus.utility = object()
    fake_pymilvus.DataType = types.SimpleNamespace(VARCHAR="VARCHAR", INT64="INT64", FLOAT_VECTOR="FLOAT_VECTOR", JSON="JSON")
    sys.modules["pymilvus"] = fake_pymilvus

from app.core.database import get_db
from app.domain.models import User
from app.main import app
from app.services.dependencies import get_current_user, require_admin


class PaginationLimitTest(unittest.TestCase):
    """验证主要列表接口拒绝超大分页参数。"""

    def setUp(self) -> None:
        """覆盖认证和数据库依赖，让参数校验成为测试焦点。"""

        self.user = User(id="admin-1", username="admin", nickname="管理员", password_hash="hash", role="admin", is_active=True)
        app.dependency_overrides[get_db] = lambda: None
        app.dependency_overrides[get_current_user] = lambda: self.user
        app.dependency_overrides[require_admin] = lambda: self.user
        self.client = TestClient(app)

    def tearDown(self) -> None:
        """清理依赖覆盖，避免影响后续测试。"""

        app.dependency_overrides.clear()

    def test_admin_page_size_is_capped(self) -> None:
        """后台普通列表 pageSize 超过 100 时应直接返回 422。"""

        paths = [
            "/api/users?pageSize=101",
            "/api/ingestion/pipelines?pageSize=101",
            "/api/ingestion/tasks?pageSize=101",
            "/api/knowledge-base?pageSize=101",
            "/api/knowledge-base/kb-1/docs?pageSize=101",
            "/api/rag/traces/runs?pageSize=101",
        ]

        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 422)

    def test_detail_page_size_and_search_limit_are_capped(self) -> None:
        """明细分页和搜索 limit 也应有独立上限。"""

        chunk_response = self.client.get("/api/knowledge-base/docs/doc-1/chunks?pageSize=201")
        search_response = self.client.get("/api/knowledge-base/docs/search?keyword=ops&limit=101")
        conversation_response = self.client.get("/api/conversations?pageSize=101")

        self.assertEqual(chunk_response.status_code, 422)
        self.assertEqual(search_response.status_code, 422)
        self.assertEqual(conversation_response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
