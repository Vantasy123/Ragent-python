from __future__ import annotations

import unittest
from pathlib import Path
import shutil
import uuid

from app.core.config import settings
from app.services.monitoring_service import MonitoringService
from app.services.project_config_service import ProjectConfigService


class MonitoringServiceTest(unittest.IsolatedAsyncioTestCase):
    """验证监控服务的解析、降级和 PromQL 白名单逻辑。"""

    def setUp(self) -> None:
        """保存全局配置，避免测试之间互相污染。"""

        self.old_enabled = settings.MONITORING_ENABLED
        self.old_prometheus = settings.PROMETHEUS_URL
        self.old_alertmanager = settings.ALERTMANAGER_URL
        self.old_servers_config = settings.SERVERS_CONFIG_PATH
        self.old_monitoring_config = settings.MONITORING_CONFIG_PATH
        self.created_dirs: list[Path] = []
        settings.MONITORING_ENABLED = True
        settings.PROMETHEUS_URL = "http://prometheus:9090"
        settings.ALERTMANAGER_URL = "http://alertmanager:9093"

    def tearDown(self) -> None:
        """恢复全局配置。"""

        settings.MONITORING_ENABLED = self.old_enabled
        settings.PROMETHEUS_URL = self.old_prometheus
        settings.ALERTMANAGER_URL = self.old_alertmanager
        settings.SERVERS_CONFIG_PATH = self.old_servers_config
        settings.MONITORING_CONFIG_PATH = self.old_monitoring_config
        for directory in self.created_dirs:
            shutil.rmtree(directory, ignore_errors=True)

    def _make_directory(self) -> Path:
        """创建本测试专用配置目录，避免 Windows 沙箱下 tempfile 目录权限异常。"""

        root = Path("scratch") / "test-monitoring-service"
        root.mkdir(parents=True, exist_ok=True)
        directory = root / uuid.uuid4().hex
        directory.mkdir(parents=True, exist_ok=False)
        self.created_dirs.append(directory)
        return directory

    async def test_targets_parse_prometheus_active_targets(self) -> None:
        """Prometheus targets 响应应转换为前端可直接展示的中文状态。"""

        service = MonitoringService()

        async def fake_get_json(_url, _params=None):
            return {
                "status": "success",
                "data": {
                    "activeTargets": [
                        {"labels": {"job": "redis", "instance": "redis-exporter:9121"}, "health": "up", "lastScrape": "2026-05-30T00:00:00Z"},
                        {"labels": {"job": "mysql", "instance": "mysqld-exporter:9104"}, "health": "down", "lastError": "connection refused"},
                    ]
                },
            }

        service._get_json = fake_get_json  # type: ignore[method-assign]

        result = await service.targets()

        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["data"]["items"][0]["statusLabel"], "正常")
        self.assertEqual(result["data"]["items"][1]["statusLabel"], "异常")

    async def test_alerts_parse_alertmanager_payload(self) -> None:
        """Alertmanager 告警应保留等级、摘要和开始时间。"""

        service = MonitoringService()

        async def fake_get_json(_url, _params=None):
            return {
                "status": "success",
                "data": [
                    {
                        "status": {"state": "active"},
                        "labels": {"alertname": "RagentTargetDown", "severity": "critical"},
                        "annotations": {"summary": "采集目标不可用"},
                        "startsAt": "2026-05-30T00:00:00Z",
                    }
                ],
            }

        service._get_json = fake_get_json  # type: ignore[method-assign]

        result = await service.alerts()

        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["data"]["items"][0]["severityLabel"], "严重")
        self.assertEqual(result["data"]["items"][0]["summary"], "采集目标不可用")

    async def test_alert_correlations_group_duplicate_alerts_and_emit_rca_hints(self) -> None:
        """告警关联分析应聚合同一影响面的重复告警，并输出 RCA 初筛线索。"""

        service = MonitoringService()

        async def fake_alerts():
            return {
                "status": "critical",
                "data": {
                    "items": [
                        {
                            "name": "TargetDown",
                            "severity": "critical",
                            "summary": "订单服务探活失败",
                            "startsAt": "2026-06-11T10:00:00Z",
                            "labels": {"service": "order-api", "instance": "10.0.0.1:8080", "severity": "critical"},
                        },
                        {
                            "name": "HighCPU",
                            "severity": "critical",
                            "summary": "订单服务 CPU 使用率过高",
                            "startsAt": "2026-06-11T10:01:00Z",
                            "labels": {"service": "order-api", "instance": "10.0.0.1:8080", "severity": "critical"},
                        },
                        {
                            "name": "RedisDown",
                            "severity": "warning",
                            "summary": "Redis 连接失败",
                            "startsAt": "2026-06-11T10:02:00Z",
                            "labels": {"job": "redis", "instance": "redis:6379", "severity": "warning"},
                        },
                    ]
                },
            }

        service.alerts = fake_alerts  # type: ignore[method-assign]

        result = await service.alert_correlations()

        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["data"]["alertCount"], 3)
        self.assertEqual(result["data"]["groupCount"], 2)
        self.assertEqual(result["data"]["noiseReduction"], 1)
        self.assertIn("order-api", result["data"]["affectedServices"])
        first_group = result["data"]["groups"][0]
        self.assertEqual(first_group["affectedServices"], ["order-api"])
        self.assertEqual(first_group["alertCount"], 2)
        self.assertTrue(any("探活失败" in hint or "资源饱和" in hint for hint in first_group["rootCauseHints"]))

    async def test_missing_monitoring_config_returns_degraded(self) -> None:
        """未启用监控时接口应降级，而不是抛出异常。"""

        settings.MONITORING_ENABLED = False
        service = MonitoringService()

        result = await service.prometheus_instant_query("up")

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["error"], "monitoring_degraded")

    async def test_unsafe_promql_is_rejected(self) -> None:
        """开放查询接口应拒绝包含明显危险片段的 PromQL。"""

        service = MonitoringService()

        result = await service.prometheus_instant_query("up; delete from users")

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["error"], "unsafe_promql")

    async def test_metric_series_flattens_range_points(self) -> None:
        """Prometheus range 响应应压平成图表点位。"""

        service = MonitoringService()

        async def fake_range_query(_query, _start, _end, _step, enforce_safe=True):
            return {
                "status": "healthy",
                "data": {
                    "result": [
                        {"values": [[1000, "1.5"], [1015, "2.5"]]},
                    ]
                },
            }

        service.prometheus_range_query = fake_range_query  # type: ignore[method-assign]

        result = await service.metric_series("cpu_percent", 1)

        self.assertEqual(result["status"], "healthy")
        self.assertEqual(len(result["data"]["points"]), 2)
        self.assertEqual(result["data"]["avg"], 2.0)

    async def test_probe_targets_include_user_configured_servers(self) -> None:
        """业务服务器配置应自动进入服务探测列表。"""

        temp_dir = self._make_directory()
        servers_path = temp_dir / "servers.yml"
        monitoring_path = temp_dir / "monitoring.yml"
        servers_path.write_text(
            """
servers:
  - id: order-service
    name: 订单服务
    enabled: true
    base_url: http://order-service:8080
    health_url: http://order-service:8080/health
    metrics_url: http://order-service:8080/metrics
    owner: 交易团队
    tags:
      - order
""",
            encoding="utf-8",
        )
        monitoring_path.write_text(
            """
monitoring:
  enabled: true
  prometheus_url: http://custom-prometheus:9090
  alertmanager_url: http://custom-alertmanager:9093
probes:
  - id: gateway
    name: 网关服务
    enabled: true
    url: http://gateway:8080/health
""",
            encoding="utf-8",
        )
        settings.PROMETHEUS_URL = ""
        settings.ALERTMANAGER_URL = ""
        service = MonitoringService(config_service=ProjectConfigService(str(servers_path), str(monitoring_path)))

        targets = service.probe_targets()

        self.assertEqual(service.prometheus_url, "http://custom-prometheus:9090")
        self.assertTrue(any(item["name"] == "订单服务" and item["source"] == "server" for item in targets))
        self.assertTrue(any(item["name"] == "网关服务" and item["source"] == "probe" for item in targets))


if __name__ == "__main__":
    unittest.main()
