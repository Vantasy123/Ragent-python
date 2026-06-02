from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers.users import router as users_router
from app.core.database import Base, get_db
from app.domain.models import User, UserAuditLog
from app.services.dependencies import require_admin
from app.services.schema_migrations import run_compatible_migrations


class UsersRouterSafetyTest(unittest.TestCase):
    """验证后台用户管理的管理员账号安全边界。"""

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
        app.include_router(users_router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[require_admin] = lambda: self.admin
        self.client = TestClient(app)

    def tearDown(self) -> None:
        """关闭测试数据库连接。"""

        self.db.close()

    def test_create_user_requires_explicit_password(self) -> None:
        """创建用户不能再隐式使用弱默认密码。"""

        response = self.client.post(
            "/users",
            json={"username": "operator", "nickname": "运维", "role": "user", "is_active": True},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("初始密码", response.json()["detail"])
        self.assertEqual(self.db.query(User).filter(User.username == "operator").count(), 0)

    def test_create_user_rejects_unknown_role(self) -> None:
        """未知角色不能写入用户表，避免权限判断出现灰区。"""

        response = self.client.post(
            "/users",
            json={"username": "operator", "nickname": "运维", "password": "StrongPassword2026!", "role": "owner", "is_active": True},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("角色", response.json()["detail"])

    def test_delete_last_active_admin_is_rejected(self) -> None:
        """不能删除系统最后一个活跃管理员。"""

        response = self.client.delete("/users/admin-1")

        self.assertEqual(response.status_code, 400)
        self.assertIn("最后一个活跃管理员", response.json()["detail"])
        self.assertEqual(self.db.query(User).filter(User.id == "admin-1").count(), 1)

    def test_disable_or_downgrade_last_active_admin_is_rejected(self) -> None:
        """最后一个活跃管理员不能被禁用或降级。"""

        disable_response = self.client.put(
            "/users/admin-1",
            json={"username": "admin", "nickname": "管理员", "role": "admin", "is_active": False},
        )
        downgrade_response = self.client.put(
            "/users/admin-1",
            json={"username": "admin", "nickname": "管理员", "role": "user", "is_active": True},
        )

        self.assertEqual(disable_response.status_code, 400)
        self.assertEqual(downgrade_response.status_code, 400)
        self.db.refresh(self.admin)
        self.assertEqual(self.admin.role, "admin")
        self.assertTrue(self.admin.is_active)

    def test_delete_admin_is_allowed_when_another_active_admin_exists(self) -> None:
        """存在第二个活跃管理员时，删除其中一个管理员应保持可用。"""

        second_admin = User(id="admin-2", username="admin2", nickname="管理员2", password_hash="hash", role="admin", is_active=True)
        self.db.add(second_admin)
        self.db.commit()

        response = self.client.delete("/users/admin-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.query(User).filter(User.id == "admin-1").count(), 0)
        self.assertEqual(self.db.query(User).filter(User.role == "admin", User.is_active.is_(True)).count(), 1)

    def test_create_user_writes_audit_log_without_password(self) -> None:
        """创建用户应写入审计日志，但不能记录密码明文或哈希。"""

        response = self.client.post(
            "/users",
            json={"username": "operator", "nickname": "运维", "password": "StrongPassword2026!", "role": "user", "is_active": True},
        )

        self.assertEqual(response.status_code, 200)
        logs = self.db.query(UserAuditLog).filter(UserAuditLog.action == "create").all()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].target_username, "operator")
        self.assertTrue(logs[0].new_value["passwordChanged"])
        self.assertNotIn("StrongPassword2026!", str(logs[0].new_value))
        self.assertNotIn("password_hash", str(logs[0].new_value))

    def test_update_user_writes_audit_log_with_safe_snapshot(self) -> None:
        """修改用户资料和密码时，审计日志只记录非敏感快照。"""

        user = User(id="user-1", username="operator", nickname="运维", password_hash="old-hash", role="user", is_active=True)
        self.db.add(user)
        self.db.commit()

        response = self.client.put(
            "/users/user-1",
            json={"username": "operator", "nickname": "运维负责人", "password": "NewStrongPassword2026!", "role": "admin", "is_active": True},
        )

        self.assertEqual(response.status_code, 200)
        log = self.db.query(UserAuditLog).filter(UserAuditLog.action == "update").one()
        self.assertEqual(log.old_value["role"], "user")
        self.assertEqual(log.new_value["role"], "admin")
        self.assertEqual(log.new_value["nickname"], "运维负责人")
        self.assertTrue(log.new_value["passwordChanged"])
        self.assertNotIn("NewStrongPassword2026!", str(log.new_value))
        self.assertNotIn("old-hash", str(log.old_value))

    def test_delete_user_writes_audit_log_and_audit_endpoint_filters(self) -> None:
        """删除用户应可通过审计接口按用户和动作追溯。"""

        user = User(id="user-1", username="operator", nickname="运维", password_hash="hash", role="user", is_active=True)
        self.db.add(user)
        self.db.commit()

        delete_response = self.client.delete("/users/user-1")
        audit_response = self.client.get("/users/audit", params={"targetUserId": "user-1", "action": "delete"})

        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(audit_response.status_code, 200)
        body = audit_response.json()["data"]
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["items"][0]["action"], "delete")
        self.assertEqual(body["items"][0]["targetUsername"], "operator")
        self.assertEqual(body["items"][0]["oldValue"]["role"], "user")
        self.assertEqual(body["items"][0]["newValue"], {})

    def test_compatible_migration_creates_user_audit_log_table(self) -> None:
        """兼容迁移应能为已有部署补建用户审计表。"""

        engine = create_engine("sqlite:///:memory:")

        run_compatible_migrations(engine)

        self.assertIn("user_audit_log", inspect(engine).get_table_names())


if __name__ == "__main__":
    unittest.main()
