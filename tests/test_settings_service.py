from __future__ import annotations

import unittest

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers.settings import router as settings_router
from app.core.config import settings
from app.core.database import Base
from app.domain.models import SystemSetting, SystemSettingAuditLog, User
from app.services.settings_service import _build_setting_audit_log, build_settings_payload, list_setting_audit_logs, update_settings


class SettingsServiceSecurityTest(unittest.TestCase):
    """验证系统设置接口不会回显敏感连接信息。"""

    def setUp(self) -> None:
        """创建独立内存库并保存全局配置。"""

        self.original_database_url = settings.DATABASE_URL
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.admin = User(id="admin-user", username="admin", password_hash="hash", role="admin", is_active=True)
        self.db.add(self.admin)
        self.db.commit()

    def tearDown(self) -> None:
        """恢复全局配置和数据库连接。"""

        settings.DATABASE_URL = self.original_database_url
        self.db.close()

    def test_readonly_security_redacts_database_credentials(self) -> None:
        """只读安全配置应脱敏数据库用户名、密码和查询参数。"""

        settings.DATABASE_URL = "mysql+pymysql://root:secret-pass@mysql:3306/ragent?charset=utf8mb4"

        payload = build_settings_payload(self.db)
        security = payload["values"]["readonly"]["security"]

        self.assertTrue(security["databaseConfigured"])
        self.assertEqual(security["databaseScheme"], "mysql+pymysql")
        self.assertEqual(security["databaseHost"], "mysql")
        self.assertEqual(security["databaseUrl"], "mysql+pymysql://***:***@mysql:3306/ragent")
        self.assertNotIn("secret-pass", str(security))
        self.assertNotIn("charset", str(security))

    def test_readonly_security_masks_sqlite_local_path(self) -> None:
        """SQLite 本地文件路径不应暴露到后台设置接口。"""

        settings.DATABASE_URL = "sqlite:///E:/private/path/ragent.db"

        payload = build_settings_payload(self.db)
        security = payload["values"]["readonly"]["security"]

        self.assertEqual(security["databaseScheme"], "sqlite")
        self.assertEqual(security["databaseHost"], "local-file")
        self.assertEqual(security["databaseUrl"], "sqlite:///<local-file>")
        self.assertNotIn("private", str(security))

    def test_settings_meta_includes_numeric_bounds(self) -> None:
        """设置元数据应返回数值边界，便于前端同步展示和校验。"""

        payload = build_settings_payload(self.db)
        meta = payload["meta"]

        self.assertEqual(meta["rag"]["topK"]["min"], 1)
        self.assertEqual(meta["rag"]["topK"]["max"], 50)
        self.assertEqual(meta["rag"]["temperature"]["min"], 0.0)
        self.assertEqual(meta["rag"]["temperature"]["max"], 2.0)
        self.assertEqual(meta["upload"]["maxFileSize"]["min"], 1024)

    def test_update_settings_rejects_out_of_range_values(self) -> None:
        """后端应拒绝越界运行参数，不能只依赖前端输入框限制。"""

        with self.assertRaises(HTTPException) as context:
            update_settings(self.db, self.admin, {"rag": {"topK": 0}})

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("Top K", context.exception.detail)
        self.assertEqual(self.db.query(SystemSetting).count(), 0)

    def test_existing_out_of_range_override_is_not_loaded_silently(self) -> None:
        """历史异常配置也不能被静默加载进运行时 payload。"""

        self.db.add(SystemSetting(key="rag.temperature", value="9.9", value_type="float", updated_by=self.admin.id))
        self.db.commit()

        with self.assertRaises(HTTPException) as context:
            build_settings_payload(self.db)

        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("Temperature", context.exception.detail)

    def test_update_settings_writes_audit_log_for_new_value(self) -> None:
        """新增配置覆盖值时应写入审计日志。"""

        payload = update_settings(self.db, self.admin, {"rag": {"topK": 8}})

        logs = self.db.query(SystemSettingAuditLog).all()
        self.assertEqual(payload["changedKeys"], ["rag.topK"])
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].key, "rag.topK")
        self.assertEqual(logs[0].old_value, "")
        self.assertEqual(logs[0].new_value, "8")
        self.assertEqual(logs[0].changed_by, self.admin.id)

    def test_update_settings_skips_audit_log_when_value_unchanged(self) -> None:
        """重复提交相同配置不应产生审计噪音。"""

        update_settings(self.db, self.admin, {"rag": {"topK": 8}})
        update_settings(self.db, self.admin, {"rag": {"topK": 8}})

        logs = self.db.query(SystemSettingAuditLog).all()
        self.assertEqual(len(logs), 1)

    def test_update_settings_audit_log_records_old_and_new_values(self) -> None:
        """修改已有配置时应记录旧值和新值。"""

        update_settings(self.db, self.admin, {"rag": {"temperature": 0.3}})
        update_settings(self.db, self.admin, {"rag": {"temperature": 0.8}})

        logs = self.db.query(SystemSettingAuditLog).filter(SystemSettingAuditLog.key == "rag.temperature").order_by(SystemSettingAuditLog.created_at.asc()).all()
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[1].old_value, "0.3")
        self.assertEqual(logs[1].new_value, "0.8")

    def test_list_setting_audit_logs_supports_pagination_and_key_filter(self) -> None:
        """设置审计查询应支持分页和按配置键过滤。"""

        update_settings(self.db, self.admin, {"rag": {"topK": 8}})
        update_settings(self.db, self.admin, {"rag": {"temperature": 0.3}})
        update_settings(self.db, self.admin, {"rag": {"temperature": 0.8}})

        payload = list_setting_audit_logs(self.db, page_no=1, page_size=1, key="rag.temperature")

        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["pageNo"], 1)
        self.assertEqual(payload["pageSize"], 1)
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["key"], "rag.temperature")
        self.assertIn("createdAt", payload["items"][0])

    def test_sensitive_setting_audit_log_is_redacted_before_persisting(self) -> None:
        """敏感配置审计写库前就应脱敏，避免数据库保留明文密钥。"""

        log = _build_setting_audit_log("security.jwtSecret", "old-secret", "new-secret", "str", self.admin)
        self.db.add(log)
        self.db.commit()

        stored_log = self.db.query(SystemSettingAuditLog).filter(SystemSettingAuditLog.key == "security.jwtSecret").one()
        self.assertEqual(stored_log.old_value, "<redacted>")
        self.assertEqual(stored_log.new_value, "<redacted>")
        self.assertNotIn("old-secret", str(stored_log.__dict__))
        self.assertNotIn("new-secret", str(stored_log.__dict__))

    def test_legacy_sensitive_setting_audit_log_is_redacted_when_listed(self) -> None:
        """历史审计里若已有明文敏感值，查询返回时也不能再次暴露。"""

        self.db.add(
            SystemSettingAuditLog(
                key="provider.apiKey",
                old_value="sk-old-secret",
                new_value="sk-new-secret",
                value_type="str",
                changed_by=self.admin.id,
            )
        )
        self.db.commit()

        payload = list_setting_audit_logs(self.db, page_no=1, page_size=10)
        item = payload["items"][0]

        self.assertEqual(item["oldValue"], "<redacted>")
        self.assertEqual(item["newValue"], "<redacted>")
        self.assertNotIn("sk-old-secret", str(item))
        self.assertNotIn("sk-new-secret", str(item))

    def test_settings_router_exposes_audit_logs(self) -> None:
        """设置路由应提供管理员只读审计查询接口。"""

        from fastapi import FastAPI
        from app.core.database import get_db
        from app.services.dependencies import require_admin

        update_settings(self.db, self.admin, {"rag": {"topK": 8}})
        app = FastAPI()
        app.include_router(settings_router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[require_admin] = lambda: self.admin

        response = TestClient(app).get("/rag/settings/audit", params={"pageNo": 1, "pageSize": 10})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["code"], 200)
        self.assertEqual(body["data"]["total"], 1)
        self.assertEqual(body["data"]["items"][0]["key"], "rag.topK")


if __name__ == "__main__":
    unittest.main()
