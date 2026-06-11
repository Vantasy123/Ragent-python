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

    async def test_tool_alert_correlations_adapts_result_for_ops_toolkit(self) -> None:
        """OpsToolkit 使用的告警关联工具应返回标准工具结果结构。"""

        service = MonitoringService()

        async def fake_alert_correlations():
            return {
                "status": "critical",
                "summary": "聚合 2 条活跃告警为 1 个告警组，涉及 1 个服务",
                "data": {"alertCount": 2, "groupCount": 1, "groups": [{"affectedServices": ["api"]}]},
            }

        service.alert_correlations = fake_alert_correlations  # type: ignore[method-assign]

        result = await service.tool_alert_correlations()

        self.assertTrue(result["success"])
        self.assertEqual(result["error"], "")
        self.assertEqual(result["data"]["groupCount"], 1)

    async def test_kubernetes_events_extracts_crashloop_and_oom_hints(self) -> None:
        """Kubernetes 事件分析应从告警标签中识别 Pod 重启和 OOM 线索。"""

        service = MonitoringService()

        async def fake_alerts():
            return {
                "status": "critical",
                "data": {
                    "items": [
                        {
                            "name": "KubePodCrashLooping",
                            "severity": "critical",
                            "summary": "订单服务 Pod CrashLoopBackOff",
                            "startsAt": "2026-06-11T10:00:00Z",
                            "labels": {
                                "alertname": "KubePodCrashLooping",
                                "severity": "critical",
                                "namespace": "prod",
                                "deployment": "order-api",
                                "pod": "order-api-7f9c",
                                "container": "api",
                                "reason": "CrashLoopBackOff",
                                "restarts": "12",
                            },
                            "annotations": {"summary": "order-api 反复重启"},
                        },
                        {
                            "name": "KubeContainerOOMKilled",
                            "severity": "warning",
                            "summary": "支付服务容器 OOMKilled",
                            "startsAt": "2026-06-11T10:03:00Z",
                            "labels": {
                                "alertname": "KubeContainerOOMKilled",
                                "severity": "warning",
                                "namespace": "prod",
                                "workload": "payment-api",
                                "pod": "payment-api-55d",
                                "container": "api",
                            },
                            "annotations": {"description": "last terminated reason OOMKilled"},
                        },
                    ]
                },
            }

        service.alerts = fake_alerts  # type: ignore[method-assign]

        result = await service.kubernetes_events()

        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["data"]["eventCount"], 2)
        self.assertIn("prod", result["data"]["affectedNamespaces"])
        self.assertIn("order-api", result["data"]["affectedWorkloads"])
        reasons = {item["reason"] for item in result["data"]["events"]}
        self.assertIn("CrashLoopBackOff", reasons)
        self.assertIn("OOMKilled", reasons)
        self.assertTrue(any("previous logs" in item for item in result["data"]["rootCauseHints"]))
        self.assertTrue(any("内存限额" in item for item in result["data"]["rootCauseHints"]))

    async def test_tool_kubernetes_events_adapts_result_for_ops_toolkit(self) -> None:
        """OpsToolkit 使用的 Kubernetes 事件工具应返回标准工具结果结构。"""

        service = MonitoringService()

        async def fake_kubernetes_events():
            return {
                "status": "critical",
                "summary": "识别 1 个 Kubernetes 事件线索",
                "data": {"eventCount": 1, "events": [{"reason": "CrashLoopBackOff"}]},
            }

        service.kubernetes_events = fake_kubernetes_events  # type: ignore[method-assign]

        result = await service.tool_kubernetes_events()

        self.assertTrue(result["success"])
        self.assertEqual(result["error"], "")
        self.assertEqual(result["data"]["eventCount"], 1)

    async def test_database_middleware_health_combines_metrics_and_alerts(self) -> None:
        """数据库与中间件健康分析应结合 up 指标和告警信号输出 RCA 线索。"""

        service = MonitoringService()

        async def fake_metric_value(metric: str):
            values = {"redis_up": 1.0, "mysql_up": 0.0, "postgres_up": 1.0}
            return {
                "status": "healthy",
                "summary": f"{metric} 当前值 {values[metric]}",
                "data": {"metric": metric, "value": values[metric]},
            }

        async def fake_alerts():
            return {
                "status": "critical",
                "data": {
                    "items": [
                        {
                            "name": "RedisConnectionPoolHigh",
                            "severity": "warning",
                            "summary": "Redis connection pool nearly exhausted",
                            "startsAt": "2026-06-11T10:00:00Z",
                            "labels": {"alertname": "RedisConnectionPoolHigh", "job": "redis", "severity": "warning"},
                            "annotations": {"summary": "Redis 连接池接近耗尽"},
                        },
                        {
                            "name": "MysqlSlowQueryHigh",
                            "severity": "critical",
                            "summary": "MySQL slow query latency high",
                            "startsAt": "2026-06-11T10:03:00Z",
                            "labels": {"alertname": "MysqlSlowQueryHigh", "job": "mysql", "severity": "critical"},
                            "annotations": {"description": "慢查询延迟升高"},
                        },
                    ]
                },
            }

        service.metric_value = fake_metric_value  # type: ignore[method-assign]
        service.alerts = fake_alerts  # type: ignore[method-assign]

        result = await service.database_middleware_health()

        self.assertEqual(result["status"], "critical")
        components = {item["key"]: item for item in result["data"]["components"]}
        self.assertEqual(components["redis"]["status"], "healthy")
        self.assertEqual(components["mysql"]["status"], "critical")
        self.assertEqual(result["data"]["alertSignals"][0]["component"], "redis")
        self.assertTrue(any("慢查询" in item or "连接池" in item for item in result["data"]["rootCauseHints"]))
        self.assertTrue(any("Trace 慢 span" in item for item in result["data"]["recommendedNextSteps"]))

    async def test_tool_database_middleware_health_adapts_result_for_ops_toolkit(self) -> None:
        """OpsToolkit 使用的数据库与中间件健康工具应返回标准工具结果结构。"""

        service = MonitoringService()

        async def fake_database_middleware_health():
            return {
                "status": "critical",
                "summary": "发现 1 个异常组件",
                "data": {"components": [{"key": "mysql", "status": "critical"}]},
            }

        service.database_middleware_health = fake_database_middleware_health  # type: ignore[method-assign]

        result = await service.tool_database_middleware_health()

        self.assertTrue(result["success"])
        self.assertEqual(result["error"], "")
        self.assertEqual(result["data"]["components"][0]["key"], "mysql")

    async def test_change_correlations_extract_release_metadata_from_alerts(self) -> None:
        """变更关联分析应从告警标签中提取发布、提交和流水线线索。"""

        temp_dir = self._make_directory()
        servers_path = temp_dir / "servers.yml"
        monitoring_path = temp_dir / "monitoring.yml"
        servers_path.write_text(
            """
servers:
  - id: order-service
    name: 订单服务
    enabled: true
    env: prod
    health_url: http://order-service:8080/health
    owner: 交易团队
    tags:
      - order-service
""",
            encoding="utf-8",
        )
        monitoring_path.write_text("monitoring:\n  enabled: true\n", encoding="utf-8")
        service = MonitoringService(config_service=ProjectConfigService(str(servers_path), str(monitoring_path)))

        async def fake_alerts():
            return {
                "status": "critical",
                "data": {
                    "items": [
                        {
                            "name": "HighErrorRate",
                            "severity": "critical",
                            "summary": "订单服务错误率升高",
                            "startsAt": "2026-06-11T10:10:00Z",
                            "labels": {
                                "service": "order-service",
                                "severity": "critical",
                                "version": "2026.06.11.1",
                                "git_sha": "abc1234",
                                "pipeline_id": "pipe-42",
                                "deployed_at": "2026-06-11T10:00:00Z",
                            },
                        }
                    ]
                },
            }

        service.alerts = fake_alerts  # type: ignore[method-assign]

        result = await service.change_correlations()

        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["data"]["changeCount"], 1)
        item = result["data"]["correlatedChanges"][0]
        self.assertEqual(item["serviceName"], "订单服务")
        self.assertEqual(item["owner"], "交易团队")
        self.assertEqual(item["version"], "2026.06.11.1")
        self.assertEqual(item["gitSha"], "abc1234")
        self.assertEqual(item["riskLevel"], "high")
        self.assertEqual(item["confidence"], "high")
        self.assertIn("回滚 Runbook", item["rollbackHint"])

    async def test_service_topology_marks_direct_and_propagated_impacts(self) -> None:
        """服务拓扑应根据 dependencies 计算直接异常节点和上游受波及节点。"""

        temp_dir = self._make_directory()
        servers_path = temp_dir / "servers.yml"
        monitoring_path = temp_dir / "monitoring.yml"
        servers_path.write_text(
            """
servers:
  - id: order-service
    name: 订单服务
    enabled: true
    health_url: http://order-service:8080/health
    owner: 交易团队
    dependencies:
      - payment-service
    tags:
      - order
  - id: payment-service
    name: 支付服务
    enabled: true
    health_url: http://payment-service:8080/health
    owner: 支付团队
    tags:
      - payment
""",
            encoding="utf-8",
        )
        monitoring_path.write_text("monitoring:\n  enabled: true\n", encoding="utf-8")
        service = MonitoringService(config_service=ProjectConfigService(str(servers_path), str(monitoring_path)))

        async def fake_alerts():
            return {
                "status": "critical",
                "data": {
                    "items": [
                        {
                            "name": "PaymentDown",
                            "severity": "critical",
                            "summary": "支付服务不可用",
                            "startsAt": "2026-06-11T10:10:00Z",
                            "labels": {"service": "payment-service", "severity": "critical"},
                        }
                    ]
                },
            }

        service.alerts = fake_alerts  # type: ignore[method-assign]

        result = await service.service_topology()

        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["data"]["affectedNodeIds"], ["payment-service"])
        self.assertIn("order-service", result["data"]["impactedNodeIds"])
        node_status = {item["id"]: item["impactStatus"] for item in result["data"]["nodes"]}
        self.assertEqual(node_status["payment-service"], "affected")
        self.assertEqual(node_status["order-service"], "impacted")
        self.assertEqual(result["data"]["edges"][0]["source"], "order-service")
        self.assertEqual(result["data"]["edges"][0]["target"], "payment-service")
        self.assertIn("支付服务 -> 订单服务", result["data"]["impactPaths"][0]["summary"])

    async def test_tool_change_correlations_adapts_result_for_ops_toolkit(self) -> None:
        """OpsToolkit 使用的变更关联工具应返回标准工具结果结构。"""

        service = MonitoringService()

        async def fake_change_correlations():
            return {
                "status": "critical",
                "summary": "识别 1 个疑似相关变更",
                "data": {"changeCount": 1, "correlatedChanges": [{"service": "api"}]},
            }

        service.change_correlations = fake_change_correlations  # type: ignore[method-assign]

        result = await service.tool_change_correlations()

        self.assertTrue(result["success"])
        self.assertEqual(result["error"], "")
        self.assertEqual(result["data"]["changeCount"], 1)

    async def test_tool_service_topology_adapts_result_for_ops_toolkit(self) -> None:
        """OpsToolkit 使用的服务拓扑工具应返回标准工具结果结构。"""

        service = MonitoringService()

        async def fake_service_topology():
            return {
                "status": "critical",
                "summary": "识别 1 个直接异常节点",
                "data": {"affectedNodeIds": ["api"], "nodes": [{"id": "api"}], "edges": []},
            }

        service.service_topology = fake_service_topology  # type: ignore[method-assign]

        result = await service.tool_service_topology()

        self.assertTrue(result["success"])
        self.assertEqual(result["error"], "")
        self.assertEqual(result["data"]["affectedNodeIds"], ["api"])

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

    async def test_metric_anomalies_detects_high_watermark_and_spike(self) -> None:
        """指标异常检测应输出高水位、突增和可解释证据。"""

        service = MonitoringService()

        async def fake_range_query(_query, _start, _end, _step, enforce_safe=True):
            return {
                "status": "healthy",
                "data": {
                    "result": [
                        {"values": [[1000, "20"], [1015, "22"], [1030, "21"], [1045, "92"], [1060, "95"]]},
                    ]
                },
            }

        service.prometheus_range_query = fake_range_query  # type: ignore[method-assign]

        result = await service.metric_anomalies("cpu_percent", 5)

        self.assertEqual(result["status"], "critical")
        anomaly_types = {item["type"] for item in result["data"]["anomalies"]}
        self.assertIn("high_watermark", anomaly_types)
        self.assertIn("spike", anomaly_types)
        self.assertEqual(result["data"]["max"], 95.0)
        self.assertTrue(any("时间线对齐" in item for item in result["data"]["recommendedNextSteps"]))

    async def test_tool_metric_anomalies_adapts_result_for_ops_toolkit(self) -> None:
        """OpsToolkit 使用的指标异常工具应返回标准工具结果结构。"""

        service = MonitoringService()

        async def fake_metric_anomalies(_metric, _minutes):
            return {
                "status": "critical",
                "summary": "CPU 使用率 检测到 1 个异常信号",
                "data": {"anomalies": [{"type": "high_watermark"}]},
            }

        service.metric_anomalies = fake_metric_anomalies  # type: ignore[method-assign]

        result = await service.tool_metric_anomalies("cpu_percent", 30)

        self.assertTrue(result["success"])
        self.assertEqual(result["error"], "")
        self.assertEqual(result["data"]["anomalies"][0]["type"], "high_watermark")

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
