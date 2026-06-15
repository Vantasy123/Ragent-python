from __future__ import annotations

import shutil
import unittest
import uuid
from pathlib import Path

from app.agents.tool_registry import UnifiedToolRegistry
from app.services.aiops_readiness_service import AIOpsReadinessService
from app.services.project_config_service import ProjectConfigService


class AIOpsReadinessServiceTest(unittest.TestCase):
    """验证 AIOps 运行前生产就绪校验。"""

    def setUp(self) -> None:
        self.created_dirs: list[Path] = []

    def tearDown(self) -> None:
        for directory in self.created_dirs:
            shutil.rmtree(directory, ignore_errors=True)

    def _make_directory(self) -> Path:
        """创建项目内测试目录，避免依赖系统临时目录权限。"""

        root = Path("scratch") / "test-aiops-readiness-service"
        root.mkdir(parents=True, exist_ok=True)
        directory = root / uuid.uuid4().hex
        directory.mkdir(parents=True, exist_ok=False)
        self.created_dirs.append(directory)
        return directory

    def test_ready_when_core_configs_and_tools_are_available(self) -> None:
        """配置和工具完整时应返回生产就绪状态。"""

        temp_dir = self._make_directory()
        servers_path = temp_dir / "servers.yml"
        monitoring_path = temp_dir / "monitoring.yml"
        servers_path.write_text(
            """
servers:
  - id: order-api
    name: 订单服务
    enabled: true
    health_url: http://order-api:8080/health
    owner: 交易团队
    dependencies:
      - payment-api
""",
            encoding="utf-8",
        )
        monitoring_path.write_text(
            """
monitoring:
  enabled: true
  prometheus_url: http://prometheus:9090
  alertmanager_url: http://alertmanager:9093
  timeout_seconds: 5
cloud_resources:
  - id: ecs-order-01
    provider: aliyun
    region: cn-hangzhou
    resource_type: ecs
    service: order-api
""",
            encoding="utf-8",
        )
        service = AIOpsReadinessService(ProjectConfigService(str(servers_path), str(monitoring_path)))

        payload = service.build()
        checks = {item["code"]: item for item in payload["checks"]}

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(checks["metrics_alerts"]["status"], "passed")
        self.assertEqual(checks["approval_gates"]["status"], "passed")
        self.assertEqual(checks["command_governance"]["status"], "passed")
        self.assertEqual(checks["audit_redaction"]["status"], "passed")
        self.assertTrue(payload["dataSources"]["metrics"])
        self.assertTrue(payload["dataSources"]["cloud"])
        self.assertTrue(payload["safetyControls"]["approvalGates"])
        self.assertTrue(payload["safetyControls"]["commandWhitelist"])
        self.assertTrue(payload["safetyControls"]["highRiskInterception"])
        self.assertTrue(payload["safetyControls"]["secretIsolation"])
        self.assertTrue(payload["safetyControls"]["auditRedaction"])
        self.assertEqual(payload["nextSteps"], [])

    def test_blocks_when_monitoring_is_enabled_without_endpoints(self) -> None:
        """监控启用但没有 Prometheus/Alertmanager 时不应进入生产自动化。"""

        temp_dir = self._make_directory()
        servers_path = temp_dir / "servers.yml"
        monitoring_path = temp_dir / "monitoring.yml"
        servers_path.write_text(
            """
servers:
  - id: order-api
    name: 订单服务
    enabled: true
    health_url: http://order-api:8080/health
""",
            encoding="utf-8",
        )
        monitoring_path.write_text(
            """
monitoring:
  enabled: true
  prometheus_url: ""
  alertmanager_url: ""
""",
            encoding="utf-8",
        )
        service = AIOpsReadinessService(ProjectConfigService(str(servers_path), str(monitoring_path)))

        payload = service.build()
        checks = {item["code"]: item for item in payload["checks"]}

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(checks["metrics_alerts"]["status"], "failed")
        self.assertFalse(payload["dataSources"]["metrics"])
        self.assertTrue(any("prometheus_url" in item for item in payload["nextSteps"]))

    def test_blocks_when_safe_command_governance_is_missing(self) -> None:
        """缺少命令模板白名单时，应阻断生产自动化 readiness。"""

        temp_dir = self._make_directory()
        servers_path = temp_dir / "servers.yml"
        monitoring_path = temp_dir / "monitoring.yml"
        servers_path.write_text(
            """
servers:
  - id: order-api
    name: 订单服务
    enabled: true
    health_url: http://order-api:8080/health
""",
            encoding="utf-8",
        )
        monitoring_path.write_text(
            """
monitoring:
  enabled: true
  prometheus_url: http://prometheus:9090
  alertmanager_url: http://alertmanager:9093
cloud_resources:
  - id: ecs-order-01
    provider: aliyun
    region: cn-hangzhou
    resource_type: ecs
    service: order-api
""",
            encoding="utf-8",
        )
        registry = UnifiedToolRegistry(include_ops=True)
        registry.tools.pop("safe_command")
        service = AIOpsReadinessService(ProjectConfigService(str(servers_path), str(monitoring_path)), registry=registry)

        payload = service.build()
        checks = {item["code"]: item for item in payload["checks"]}

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(checks["command_governance"]["status"], "failed")
        self.assertFalse(payload["safetyControls"]["commandWhitelist"])
        self.assertFalse(payload["safetyControls"]["highRiskInterception"])
        self.assertFalse(payload["safetyControls"]["secretIsolation"])
        self.assertTrue(any("safe_command" in item for item in payload["nextSteps"]))


if __name__ == "__main__":
    unittest.main()
