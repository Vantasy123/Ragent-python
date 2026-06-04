from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers.security_audit import router as security_audit_router
from app.core.database import Base, get_db
from app.domain.models import SecurityAuditLog, User
from app.services.dependencies import require_admin
from app.services.schema_migrations import run_compatible_migrations


class SecurityAuditRouterTest(unittest.TestCase):
    """验证安全审计中心的通用事件记录能力。"""

    def setUp(self) -> None:
        """创建独立内存库和测试客户端。"""

        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.admin = User(id="admin-1", username="admin", nickname="管理员", password_hash="hash", role="admin", is_active=True)
        self.db.add(self.admin)
        self.db.commit()

        app = FastAPI()
        app.include_router(security_audit_router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[require_admin] = lambda: self.admin
        self.client = TestClient(app)

    def tearDown(self) -> None:
        """关闭测试数据库连接。"""

        self.db.close()

    def test_record_export_event_and_list_by_filters(self) -> None:
        """导出审计数据应写入安全审计事件，并可按类型、动作和对象查询。"""

        response = self.client.post(
            "/admin/security-audit/events",
            json={
                "category": "export",
                "action": "export_audit_csv",
                "targetType": "audit",
                "targetId": "users",
                "detail": {"scope": "filtered", "rows": 20},
            },
        )
        list_response = self.client.get(
            "/admin/security-audit/events",
            params={"category": "export", "action": "export_audit_csv", "targetType": "audit", "targetId": "users"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.query(SecurityAuditLog).count(), 1)
        body = list_response.json()["data"]
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["action"], "export_audit_csv")
        self.assertEqual(body["items"][0]["operatorId"], self.admin.id)
        self.assertEqual(body["items"][0]["detail"]["rows"], 20)

    def test_rejects_unknown_security_event(self) -> None:
        """客户端不能写入未定义的任意安全审计事件。"""

        response = self.client.post(
            "/admin/security-audit/events",
            json={
                "category": "debug",
                "action": "manual_insert",
                "targetType": "audit",
                "targetId": "users",
                "detail": {},
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.query(SecurityAuditLog).count(), 0)

    def test_security_audit_detail_redacts_sensitive_fields(self) -> None:
        """安全事件详情不能保存 Token 或密钥明文。"""

        response = self.client.post(
            "/admin/security-audit/events",
            json={
                "category": "export",
                "action": "export_audit_csv",
                "targetType": "audit",
                "targetId": "ops",
                "detail": {"token": "secret-token", "safeFilter": "ops"},
            },
        )

        self.assertEqual(response.status_code, 200)
        row = self.db.query(SecurityAuditLog).one()
        self.assertEqual(row.detail["token"], "<redacted>")
        self.assertEqual(row.detail["safeFilter"], "ops")
        self.assertNotIn("secret-token", str(row.detail))

    def test_compatible_migration_creates_security_audit_log_table(self) -> None:
        """兼容迁移应能为已有部署补建安全审计事件表。"""

        engine = create_engine("sqlite:///:memory:")

        run_compatible_migrations(engine)

        self.assertIn("security_audit_log", inspect(engine).get_table_names())


if __name__ == "__main__":
    unittest.main()
