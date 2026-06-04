from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.project_config_service import ProjectConfigService


class ProjectConfigServiceTest(unittest.TestCase):
    """验证开源部署配置文件读写能力。"""

    def test_status_reports_missing_config_steps(self) -> None:
        """配置文件不存在时应返回明确的下一步提示。"""

        with TemporaryDirectory() as temp_dir:
            service = ProjectConfigService(
                str(Path(temp_dir) / "servers.yml"),
                str(Path(temp_dir) / "monitoring.yml"),
            )

            status = service.status()

            self.assertFalse(status["ready"])
            self.assertFalse(status["serversConfigExists"])
            self.assertTrue(any("servers.example.yml" in item for item in status["nextSteps"]))

    def test_save_and_read_servers(self) -> None:
        """保存后的业务服务器配置应可再次读取，并保留禁用项。"""

        with TemporaryDirectory() as temp_dir:
            service = ProjectConfigService(
                str(Path(temp_dir) / "servers.yml"),
                str(Path(temp_dir) / "monitoring.yml"),
            )
            service.save_servers(
                [
                    {
                        "id": "order",
                        "name": "订单服务",
                        "enabled": True,
                        "health_url": "http://order:8080/health",
                    },
                    {
                        "id": "user",
                        "name": "用户服务",
                        "enabled": False,
                        "health_url": "http://user:8080/health",
                    },
                ]
            )

            self.assertEqual(len(service.all_servers()), 2)
            self.assertEqual(len(service.servers()), 1)
            self.assertEqual(service.servers()[0]["name"], "订单服务")

    def test_save_monitoring_config(self) -> None:
        """监控配置保存后应可供 MonitoringService 读取。"""

        with TemporaryDirectory() as temp_dir:
            service = ProjectConfigService(
                str(Path(temp_dir) / "servers.yml"),
                str(Path(temp_dir) / "monitoring.yml"),
            )
            service.save_monitoring(
                {
                    "enabled": True,
                    "prometheus_url": "http://prometheus:9090",
                    "alertmanager_url": "http://alertmanager:9093",
                    "timeout_seconds": 3,
                },
                [{"id": "gateway", "name": "网关", "url": "http://gateway/health"}],
            )

            monitoring = service.monitoring()

            self.assertTrue(monitoring["enabled"])
            self.assertEqual(monitoring["prometheus_url"], "http://prometheus:9090")
            self.assertEqual(monitoring["probes"][0]["name"], "网关")

    def test_rejects_non_http_monitoring_url(self) -> None:
        """监控地址只允许 HTTP/HTTPS，避免保存 file 等危险协议。"""

        with TemporaryDirectory() as temp_dir:
            service = ProjectConfigService(
                str(Path(temp_dir) / "servers.yml"),
                str(Path(temp_dir) / "monitoring.yml"),
            )

            with self.assertRaisesRegex(ValueError, "http 或 https"):
                service.save_monitoring({"enabled": True, "prometheus_url": "file:///etc/passwd"}, [])

    def test_enabled_probe_requires_url(self) -> None:
        """启用的探测目标必须有 URL，否则监控面板会出现不可解释的失败项。"""

        with TemporaryDirectory() as temp_dir:
            service = ProjectConfigService(
                str(Path(temp_dir) / "servers.yml"),
                str(Path(temp_dir) / "monitoring.yml"),
            )

            with self.assertRaisesRegex(ValueError, "不能为空"):
                service.save_monitoring({"enabled": True}, [{"id": "gateway", "name": "网关", "enabled": True, "url": ""}])

    def test_rejects_out_of_range_monitoring_timeout(self) -> None:
        """监控超时时间必须限制在合理范围内。"""

        with TemporaryDirectory() as temp_dir:
            service = ProjectConfigService(
                str(Path(temp_dir) / "servers.yml"),
                str(Path(temp_dir) / "monitoring.yml"),
            )

            with self.assertRaisesRegex(ValueError, "0 到 60 秒"):
                service.save_monitoring({"enabled": True, "timeout_seconds": 120}, [])


if __name__ == "__main__":
    unittest.main()
