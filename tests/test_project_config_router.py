from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers.project_config import router as project_config_router
from app.core.config import settings
from app.core.database import Base, get_db
from app.domain.models import SecurityAuditLog, User
from app.services.dependencies import require_admin


class ProjectConfigRouterTest(unittest.TestCase):
    """验证接入配置路由的写入审计能力。"""

    def setUp(self) -> None:
        """创建隔离数据库、临时配置路径和测试客户端。"""

        self.temp_dir = TemporaryDirectory()
        self.old_servers_config_path = settings.SERVERS_CONFIG_PATH
        self.old_monitoring_config_path = settings.MONITORING_CONFIG_PATH
        settings.SERVERS_CONFIG_PATH = str(Path(self.temp_dir.name) / "servers.yml")
        settings.MONITORING_CONFIG_PATH = str(Path(self.temp_dir.name) / "monitoring.yml")

        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(bind=engine)
        self.db = self.Session()
        self.admin = User(id="admin-1", username="admin", nickname="管理员", password_hash="hash", role="admin", is_active=True)
        self.db.add(self.admin)
        self.db.commit()

        app = FastAPI()
        app.include_router(project_config_router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[require_admin] = lambda: self.admin
        self.client = TestClient(app)

    def tearDown(self) -> None:
        """还原全局配置并关闭测试资源。"""

        self.db.close()
        settings.SERVERS_CONFIG_PATH = self.old_servers_config_path
        settings.MONITORING_CONFIG_PATH = self.old_monitoring_config_path
        self.temp_dir.cleanup()

    def test_save_servers_records_config_audit_summary(self) -> None:
        """保存业务服务器配置后应写入安全审计摘要。"""

        response = self.client.put(
            "/admin/project-config/servers",
            json={
                "servers": [
                    {
                        "id": "gateway",
                        "name": "网关服务",
                        "env": "prod",
                        "enabled": True,
                        "base_url": "https://gateway.example.com",
                        "health_url": "https://gateway.example.com/health",
                        "metrics_url": "https://gateway.example.com/metrics",
                        "owner": "ops",
                        "tags": ["核心"],
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        row = self.db.query(SecurityAuditLog).one()
        self.assertEqual(row.category, "config")
        self.assertEqual(row.action, "update_servers_config")
        self.assertEqual(row.target_type, "project_config")
        self.assertEqual(row.target_id, "servers")
        self.assertEqual(row.operator_id, self.admin.id)
        self.assertEqual(row.detail["total"], 1)
        self.assertEqual(row.detail["enabled"], 1)
        self.assertEqual(row.detail["serverIds"], ["gateway"])

    def test_invalid_servers_config_does_not_record_audit(self) -> None:
        """非法配置保存失败时不能写入成功审计。"""

        response = self.client.put(
            "/admin/project-config/servers",
            json={
                "servers": [
                    {
                        "id": "gateway",
                        "name": "网关服务",
                        "enabled": True,
                        "health_url": "file:///etc/passwd",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.db.query(SecurityAuditLog).count(), 0)

    def test_save_monitoring_records_config_audit_summary(self) -> None:
        """保存监控配置后应记录启用状态和探测目标数量。"""

        response = self.client.put(
            "/admin/project-config/monitoring",
            json={
                "monitoring": {
                    "enabled": True,
                    "prometheus_url": "http://prometheus:9090",
                    "alertmanager_url": "http://alertmanager:9093",
                    "timeout_seconds": 5,
                },
                "probes": [
                    {"id": "gateway", "name": "网关", "enabled": True, "url": "https://gateway.example.com/health"},
                    {"id": "admin", "name": "后台", "enabled": False, "url": ""},
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        row = self.db.query(SecurityAuditLog).one()
        self.assertEqual(row.action, "update_monitoring_config")
        self.assertEqual(row.target_id, "monitoring")
        self.assertTrue(row.detail["enabled"])
        self.assertTrue(row.detail["prometheusConfigured"])
        self.assertTrue(row.detail["alertmanagerConfigured"])
        self.assertEqual(row.detail["probeCount"], 2)
        self.assertEqual(row.detail["enabledProbeCount"], 1)

    def test_probe_test_records_sanitized_url(self) -> None:
        """手动探测审计应移除 URL 中的账号、查询参数和片段。"""

        async def fake_http_probe(_service, _target_id, _name, _url, _meta):
            """替代真实 HTTP 请求，专注验证路由审计行为。"""

            return {"status": "up", "statusCode": 200, "durationMs": 12}

        with patch("app.api.routers.project_config.MonitoringService.http_probe", fake_http_probe):
            response = self.client.post(
                "/admin/project-config/probe-test",
                json={"name": "网关", "url": "https://user:pass@gateway.example.com:8443/health?token=secret#frag"},
            )

        self.assertEqual(response.status_code, 200)
        row = self.db.query(SecurityAuditLog).one()
        self.assertEqual(row.action, "probe_test")
        self.assertEqual(row.detail["url"], "https://gateway.example.com:8443/health")
        self.assertNotIn("token=secret", str(row.detail))
        self.assertNotIn("user:pass", str(row.detail))


if __name__ == "__main__":
    unittest.main()
