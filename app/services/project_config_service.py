"""项目配置文件读取服务，用于开源部署时按用户环境接入业务系统。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from app.core.config import settings


class ProjectConfigService:
    """读取 config/*.yml，缺失时返回空配置，保证项目开箱仍可启动。"""

    def __init__(self, servers_path: str | None = None, monitoring_path: str | None = None) -> None:
        """允许测试或部署显式传入配置路径。"""

        self.servers_path = Path(servers_path or settings.SERVERS_CONFIG_PATH)
        self.monitoring_path = Path(monitoring_path or settings.MONITORING_CONFIG_PATH)

    def servers(self) -> list[dict[str, Any]]:
        """读取已启用的业务服务器配置。"""

        return [item for item in self.all_servers() if item.get("enabled", True) is not False]

    def all_servers(self) -> list[dict[str, Any]]:
        """读取全部业务服务器配置，包含已禁用项，供后台配置页编辑。"""

        payload = self._read_yaml(self.servers_path)
        raw_servers = payload.get("servers", [])
        if not isinstance(raw_servers, list):
            return []
        return [self._normalize_server(item) for item in raw_servers if isinstance(item, dict)]

    def monitoring(self) -> dict[str, Any]:
        """读取监控配置，包括 Prometheus、Alertmanager 和额外探测目标。"""

        payload = self._read_yaml(self.monitoring_path)
        monitoring = payload.get("monitoring", {})
        probes = payload.get("probes", [])
        if not isinstance(monitoring, dict):
            monitoring = {}
        if not isinstance(probes, list):
            probes = []
        return {
            "enabled": bool(monitoring.get("enabled", False)),
            "prometheus_url": str(monitoring.get("prometheus_url") or "").strip(),
            "alertmanager_url": str(monitoring.get("alertmanager_url") or "").strip(),
            "timeout_seconds": monitoring.get("timeout_seconds"),
            "probes": [self._normalize_probe(item) for item in probes if self._enabled(item)],
        }

    def cloud_resources(self) -> list[dict[str, Any]]:
        """读取云平台资源清单，作为 CMDB 的轻量补充。"""

        payload = self._read_yaml(self.monitoring_path)
        raw_resources = payload.get("cloud_resources") or payload.get("cloudResources") or []
        if not isinstance(raw_resources, list):
            return []
        return [self._normalize_cloud_resource(item) for item in raw_resources if self._enabled(item)]

    def save_servers(self, servers: list[dict[str, Any]]) -> dict[str, Any]:
        """保存业务服务器配置，供初始化向导或后台页面直接写入 YAML。"""

        normalized = [self._normalize_server(item, strict=True) for item in servers if isinstance(item, dict)]
        self._write_yaml(self.servers_path, {"servers": normalized})
        enabled_count = len([item for item in normalized if item.get("enabled", True) is not False])
        return {
            "path": str(self.servers_path),
            "items": normalized,
            "total": len(normalized),
            "enabled": enabled_count,
        }

    def save_monitoring(self, monitoring: dict[str, Any], probes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """保存监控配置和额外探测目标。"""

        normalized_monitoring = {
            "enabled": bool(monitoring.get("enabled", False)),
            "prometheus_url": self._normalize_http_url(monitoring.get("prometheus_url"), "Prometheus 地址"),
            "alertmanager_url": self._normalize_http_url(monitoring.get("alertmanager_url"), "Alertmanager 地址"),
            "timeout_seconds": self._normalize_timeout(monitoring.get("timeout_seconds") or 5),
        }
        normalized_probes = [self._normalize_probe(item, strict=True) for item in probes or [] if isinstance(item, dict)]
        self._write_yaml(self.monitoring_path, {"monitoring": normalized_monitoring, "probes": normalized_probes})
        return {
            "path": str(self.monitoring_path),
            "monitoring": normalized_monitoring,
            "probes": normalized_probes,
        }

    def status(self) -> dict[str, Any]:
        """返回开源部署初始化状态，前端可据此展示下一步提示。"""

        servers = self.all_servers()
        enabled_servers = [item for item in servers if item.get("enabled", True) is not False]
        monitoring = self.monitoring()
        next_steps: list[str] = []
        if not self.servers_path.exists():
            next_steps.append("复制 config/servers.example.yml 为 config/servers.yml 并填写业务服务器")
        if not self.monitoring_path.exists():
            next_steps.append("复制 config/monitoring.example.yml 为 config/monitoring.yml 并填写监控地址")
        if not enabled_servers:
            next_steps.append("至少添加一个启用的业务服务器健康检查地址")
        if not monitoring.get("prometheus_url"):
            next_steps.append("配置 Prometheus 地址以展示真实指标")
        if not monitoring.get("alertmanager_url"):
            next_steps.append("配置 Alertmanager 地址以展示告警")
        return {
            "serversConfigPath": str(self.servers_path),
            "monitoringConfigPath": str(self.monitoring_path),
            "serversConfigExists": self.servers_path.exists(),
            "monitoringConfigExists": self.monitoring_path.exists(),
            "serverCount": len(servers),
            "enabledServerCount": len(enabled_servers),
            "monitoringEnabled": monitoring.get("enabled", False),
            "prometheusConfigured": bool(monitoring.get("prometheus_url")),
            "alertmanagerConfigured": bool(monitoring.get("alertmanager_url")),
            "nextSteps": next_steps,
            "ready": not next_steps,
        }

    def _read_yaml(self, path: Path) -> dict[str, Any]:
        """安全读取 YAML 文件，文件不存在或格式错误时返回空字典。"""

        if not path.exists():
            return {}
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _write_yaml(self, path: Path, payload: dict[str, Any]) -> None:
        """写入 YAML 配置文件，自动创建 config 目录。"""

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def _enabled(self, item: Any) -> bool:
        """统一判断配置项是否启用。"""

        return isinstance(item, dict) and item.get("enabled", True) is not False

    def validate_probe_url(self, url: str) -> str:
        """校验手动探测地址，避免后台误触发非 HTTP 协议或空地址。"""

        return self._normalize_http_url(url, "探测地址", required=True)

    def _normalize_server(self, item: dict[str, Any], strict: bool = False) -> dict[str, Any]:
        """把业务服务器配置标准化，便于监控服务直接消费。"""

        server_id = str(item.get("id") or item.get("name") or item.get("base_url") or "").strip()
        enabled = item.get("enabled", True) is not False
        base_url = self._normalize_http_url(item.get("base_url"), "业务服务器 base_url") if strict else str(item.get("base_url") or "").strip()
        health_url = (
            self._normalize_http_url(item.get("health_url"), "业务服务器 health_url", required=enabled)
            if strict
            else str(item.get("health_url") or "").strip()
        )
        metrics_url = self._normalize_http_url(item.get("metrics_url"), "业务服务器 metrics_url") if strict else str(item.get("metrics_url") or "").strip()
        return {
            "id": server_id,
            "name": str(item.get("name") or server_id or "未命名服务").strip(),
            "env": str(item.get("env") or "").strip(),
            "enabled": enabled,
            "base_url": base_url,
            "health_url": health_url,
            "metrics_url": metrics_url,
            "owner": str(item.get("owner") or "").strip(),
            "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
            "dependencies": [str(value).strip() for value in item.get("dependencies", []) if str(value).strip()]
            if isinstance(item.get("dependencies"), list)
            else [],
        }

    def _normalize_probe(self, item: dict[str, Any], strict: bool = False) -> dict[str, Any]:
        """把额外探测目标配置标准化。"""

        probe_id = str(item.get("id") or item.get("name") or item.get("url") or "").strip()
        enabled = item.get("enabled", True) is not False
        url = self._normalize_http_url(item.get("url"), "探测地址", required=enabled) if strict else str(item.get("url") or "").strip()
        return {
            "id": probe_id,
            "name": str(item.get("name") or probe_id or "未命名探测").strip(),
            "enabled": enabled,
            "url": url,
            "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
        }

    def _normalize_cloud_resource(self, item: dict[str, Any]) -> dict[str, Any]:
        """把云资源配置标准化，便于故障诊断和影响面分析复用。"""

        resource_id = str(item.get("resource_id") or item.get("resourceId") or item.get("id") or "").strip()
        resource_type = str(item.get("resource_type") or item.get("resourceType") or item.get("type") or "").strip()
        return {
            "id": resource_id,
            "resourceId": resource_id,
            "name": str(item.get("name") or resource_id or "未命名云资源").strip(),
            "provider": str(item.get("provider") or item.get("cloud") or "").strip(),
            "accountId": str(item.get("account_id") or item.get("accountId") or "").strip(),
            "region": str(item.get("region") or "").strip(),
            "zone": str(item.get("zone") or item.get("availabilityZone") or "").strip(),
            "resourceType": resource_type,
            "service": str(item.get("service") or item.get("service_id") or item.get("serviceId") or "").strip(),
            "env": str(item.get("env") or "").strip(),
            "owner": str(item.get("owner") or "").strip(),
            "status": str(item.get("status") or "").strip(),
            "enabled": item.get("enabled", True) is not False,
            "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
        }

    def _normalize_http_url(self, value: Any, label: str, required: bool = False) -> str:
        """校验 HTTP/HTTPS URL，保留内网域名但拒绝空值和危险协议。"""

        text = str(value or "").strip()
        if not text:
            if required:
                raise ValueError(f"{label}不能为空")
            return ""
        parsed = urlparse(text)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"{label}必须是 http 或 https URL")
        return text

    def _normalize_timeout(self, value: Any) -> float:
        """把监控超时限制在生产可控范围内，避免配置错误拖垮后台请求。"""

        try:
            timeout = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("监控超时时间必须是数字") from exc
        if timeout <= 0 or timeout > 60:
            raise ValueError("监控超时时间必须在 0 到 60 秒之间")
        return timeout
