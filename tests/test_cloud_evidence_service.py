from __future__ import annotations

from pathlib import Path
import shutil
import unittest
import uuid

from app.services.cloud_evidence_service import CloudEvidenceService
from app.services.monitoring_service import MonitoringService
from app.services.project_config_service import ProjectConfigService


class CloudEvidenceServiceTest(unittest.IsolatedAsyncioTestCase):
    """验证云平台资源证据的配置读取、告警匹配和风险输出。"""

    def setUp(self) -> None:
        self.created_dirs: list[Path] = []

    def tearDown(self) -> None:
        for directory in self.created_dirs:
            shutil.rmtree(directory, ignore_errors=True)

    def _make_directory(self) -> Path:
        """创建项目内测试目录，避免依赖系统临时目录权限。"""

        root = Path("scratch") / "test-cloud-evidence-service"
        root.mkdir(parents=True, exist_ok=True)
        directory = root / uuid.uuid4().hex
        directory.mkdir(parents=True, exist_ok=False)
        self.created_dirs.append(directory)
        return directory

    async def test_analyze_matches_cloud_alerts_to_configured_resources(self) -> None:
        """云资源告警应命中配置清单并输出高风险 RCA 线索。"""

        temp_dir = self._make_directory()
        monitoring_path = temp_dir / "monitoring.yml"
        monitoring_path.write_text(
            """
monitoring:
  enabled: true
cloud_resources:
  - id: ecs-order-01
    name: 订单服务云主机
    provider: aliyun
    account_id: "123"
    region: cn-hangzhou
    resource_type: ecs
    service: order-service
    owner: 交易团队
    status: running
    tags:
      - order
""",
            encoding="utf-8",
        )
        config_service = ProjectConfigService(str(temp_dir / "servers.yml"), str(monitoring_path))
        monitoring_service = MonitoringService(config_service=config_service)

        async def fake_alerts() -> dict:
            return {
                "status": "critical",
                "data": {
                    "items": [
                        {
                            "name": "CloudInstanceDown",
                            "severity": "critical",
                            "summary": "订单服务云主机不可用",
                            "startsAt": "2026-06-11T10:00:00Z",
                            "labels": {
                                "cloud_provider": "aliyun",
                                "account_id": "123",
                                "region": "cn-hangzhou",
                                "instance_id": "ecs-order-01",
                                "resource_type": "ecs",
                                "service": "order-service",
                            },
                        }
                    ]
                },
            }

        monitoring_service.alerts = fake_alerts  # type: ignore[method-assign]
        service = CloudEvidenceService(config_service=config_service, monitoring_service=monitoring_service)

        result = await service.analyze()
        data = result["data"]

        assert result["status"] == "critical"
        assert data["resources"][0]["resourceId"] == "ecs-order-01"
        assert data["matchedResources"][0]["alertCount"] == 1
        assert data["cloudAlerts"][0]["resourceId"] == "ecs-order-01"
        assert any(signal["type"] == "cloud_alert" and signal["severity"] == "high" for signal in data["riskSignals"])
        assert any("云监控" in hint for hint in data["rootCauseHints"])

    async def test_analyze_reports_data_gaps_without_cloud_metadata(self) -> None:
        """缺少云资源清单和告警云标签时，应输出明确接入缺口。"""

        temp_dir = self._make_directory()
        config_service = ProjectConfigService(str(temp_dir / "servers.yml"), str(temp_dir / "monitoring.yml"))
        monitoring_service = MonitoringService(config_service=config_service)

        async def fake_alerts() -> dict:
            return {
                "status": "critical",
                "data": {"items": [{"name": "HighCPU", "severity": "warning", "summary": "CPU 高", "labels": {"service": "order-service"}}]},
            }

        monitoring_service.alerts = fake_alerts  # type: ignore[method-assign]
        service = CloudEvidenceService(config_service=config_service, monitoring_service=monitoring_service)

        result = await service.analyze()
        gaps = result["data"]["dataGaps"]

        assert result["status"] == "degraded"
        assert any("cloud_resources" in item for item in gaps)
        assert any("cloud_provider" in item for item in gaps)
