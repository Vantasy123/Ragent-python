"""云平台资源证据服务，用于把云主机、负载均衡和托管资源纳入 RCA。"""

from __future__ import annotations

from typing import Any

from app.services.monitoring_service import MonitoringService
from app.services.project_config_service import ProjectConfigService


class CloudEvidenceService:
    """只读分析云资源清单和告警标签，不直接持有云厂商凭证。"""

    CLOUD_LABEL_ALIASES: dict[str, list[str]] = {
        "provider": ["cloud_provider", "provider", "cloud", "vendor"],
        "accountId": ["account_id", "cloud_account", "account", "tenant_id", "project_id"],
        "region": ["region", "cloud_region", "aliyun_region", "aws_region"],
        "zone": ["zone", "availability_zone", "az"],
        "resourceId": ["resource_id", "instance_id", "node", "host", "pod_node", "vm_id", "ecs_instance_id"],
        "resourceType": ["resource_type", "instance_type", "cloud_resource_type", "type"],
        "service": ["service", "app", "application", "job"],
    }
    HEALTHY_STATUS = {"", "ok", "healthy", "running", "available", "active", "normal", "up"}

    def __init__(
        self,
        config_service: ProjectConfigService | None = None,
        monitoring_service: MonitoringService | None = None,
    ) -> None:
        self.config_service = config_service or ProjectConfigService()
        self.monitoring_service = monitoring_service or MonitoringService(config_service=self.config_service)

    async def analyze(self) -> dict[str, Any]:
        """聚合云资源配置和告警标签，输出资源风险、RCA 线索和接入缺口。"""

        resources = self.config_service.cloud_resources()
        alerts_result = await self.monitoring_service.alerts()
        alert_items = alerts_result.get("data", {}).get("items", []) if alerts_result.get("status") != "degraded" else []
        alerts = alert_items if isinstance(alert_items, list) else []
        cloud_alerts = self._cloud_alerts(alerts)
        matched = self._matched_resources(resources, cloud_alerts)
        risk_signals = self._risk_signals(resources, cloud_alerts, matched)
        data_gaps = self._data_gaps(resources, alerts, cloud_alerts)
        rca_hints = self._root_cause_hints(resources, cloud_alerts, risk_signals)
        recommended = self._recommended_steps(resources, cloud_alerts, data_gaps, alerts_result)
        status = self._status_from_risks(risk_signals, data_gaps)

        return {
            "status": status,
            "displayName": "云平台资源证据",
            "summary": f"识别 {len(resources)} 个云资源配置、{len(cloud_alerts)} 条云资源告警、{len(risk_signals)} 条风险信号",
            "data": {
                "resources": resources,
                "cloudAlerts": cloud_alerts,
                "matchedResources": matched,
                "riskSignals": risk_signals,
                "rootCauseHints": rca_hints,
                "recommendedNextSteps": recommended,
                "dataGaps": data_gaps,
            },
        }

    def _cloud_alerts(self, alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """从 Alertmanager 标签和注解中抽取云资源线索。"""

        results: list[dict[str, Any]] = []
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
            annotations = alert.get("annotations") if isinstance(alert.get("annotations"), dict) else {}
            merged = {**annotations, **labels}
            evidence = self._extract_cloud_metadata(merged)
            cloud_fields = set(evidence) - {"service"}
            if not cloud_fields and not self._looks_like_cloud_alert(alert):
                continue
            severity = str(alert.get("severity") or labels.get("severity") or "warning")
            evidence.update(
                {
                    "alertName": alert.get("name") or labels.get("alertname") or "CloudAlert",
                    "severity": severity,
                    "summary": alert.get("summary") or annotations.get("summary") or annotations.get("description") or "",
                    "startsAt": alert.get("startsAt") or "",
                    "labels": labels,
                }
            )
            evidence["fingerprint"] = self._cloud_alert_key(evidence)
            results.append(evidence)
        return results

    def _extract_cloud_metadata(self, values: dict[str, Any]) -> dict[str, str]:
        """按别名抽取 provider、region、resourceId 等云资源字段。"""

        metadata: dict[str, str] = {}
        lowered = {str(key).lower(): value for key, value in values.items()}
        for field, aliases in self.CLOUD_LABEL_ALIASES.items():
            for alias in aliases:
                value = lowered.get(alias.lower())
                if value is not None and str(value).strip():
                    metadata[field] = str(value).strip()
                    break
        return metadata

    def _looks_like_cloud_alert(self, alert: dict[str, Any]) -> bool:
        """识别没有标准云标签但明显来自云资源的告警。"""

        labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
        values = [alert.get("name"), alert.get("summary"), *labels.values()]
        text = " ".join(str(value) for value in values).lower()
        return any(keyword in text for keyword in ["ecs", "rds", "slb", "elb", "clb", "vm", "node", "cloud", "云", "主机", "负载均衡"])

    def _matched_resources(self, resources: list[dict[str, Any]], cloud_alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """把云告警映射到配置中的资源清单，形成影响面证据。"""

        matched: list[dict[str, Any]] = []
        for resource in resources:
            aliases = self._resource_aliases(resource)
            related_alerts = []
            for alert in cloud_alerts:
                alert_values = self._alert_aliases(alert)
                if aliases & alert_values:
                    related_alerts.append(alert)
            if related_alerts:
                matched.append(
                    {
                        "resourceId": resource.get("resourceId"),
                        "name": resource.get("name"),
                        "provider": resource.get("provider"),
                        "region": resource.get("region"),
                        "resourceType": resource.get("resourceType"),
                        "service": resource.get("service"),
                        "owner": resource.get("owner"),
                        "alertCount": len(related_alerts),
                        "alerts": [item.get("alertName") for item in related_alerts],
                    }
                )
        return matched

    def _risk_signals(
        self,
        resources: list[dict[str, Any]],
        cloud_alerts: list[dict[str, Any]],
        matched: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """把资源状态和云告警转成统一风险信号。"""

        signals: list[dict[str, str]] = []
        for resource in resources:
            status = str(resource.get("status") or "").strip().lower()
            if status and status not in self.HEALTHY_STATUS:
                signals.append(
                    {
                        "severity": "high" if status in {"down", "failed", "unavailable", "stopped"} else "medium",
                        "type": "cloud_resource_status",
                        "message": f"云资源 {resource.get('name') or resource.get('resourceId')} 状态为 {resource.get('status')}",
                    }
                )
        for alert in cloud_alerts:
            severity = str(alert.get("severity") or "warning").lower()
            signals.append(
                {
                    "severity": "high" if severity == "critical" else "medium",
                    "type": "cloud_alert",
                    "message": f"云资源告警 {alert.get('alertName')}：{alert.get('summary') or alert.get('resourceId') or alert.get('service')}",
                }
            )
        if cloud_alerts and not matched and resources:
            signals.append({"severity": "medium", "type": "unmatched_cloud_alert", "message": "云资源告警未命中配置清单，可能存在 CMDB 漏配或标签不一致"})
        return self._deduplicate_dicts(signals, "message")

    def _data_gaps(self, resources: list[dict[str, Any]], alerts: list[dict[str, Any]], cloud_alerts: list[dict[str, Any]]) -> list[str]:
        """生成云平台证据的数据缺口。"""

        gaps: list[str] = []
        if not resources:
            gaps.append("未在 monitoring.yml 中配置 cloud_resources，无法基于 CMDB 清单判断云资源影响面")
        if alerts and not cloud_alerts:
            gaps.append("当前告警未携带 cloud_provider、region、instance_id、resource_id 等云资源标签")
        if resources and any(not item.get("region") for item in resources):
            gaps.append("部分云资源缺少 region，跨地域故障时无法准确圈定影响范围")
        if resources and any(not item.get("owner") for item in resources):
            gaps.append("部分云资源缺少 owner，无法自动定位负责团队")
        return gaps

    def _root_cause_hints(
        self,
        resources: list[dict[str, Any]],
        cloud_alerts: list[dict[str, Any]],
        risk_signals: list[dict[str, str]],
    ) -> list[str]:
        """生成云平台 RCA 初筛线索。"""

        hints: list[str] = []
        for signal in risk_signals:
            if signal.get("severity") in {"high", "medium"}:
                hints.append(str(signal.get("message") or ""))
        for alert in cloud_alerts[:5]:
            resource = alert.get("resourceId") or alert.get("service") or "云资源"
            region = f" {alert.get('region')}" if alert.get("region") else ""
            hints.append(f"优先核对{region} {resource} 的云监控、实例事件、网络 ACL/安全组和资源配额")
        if resources:
            providers = sorted({str(item.get("provider")) for item in resources if item.get("provider")})
            if providers:
                hints.append(f"已配置云厂商资源：{', '.join(providers)}，可继续接入对应云 API 拉取实例事件和资源配额")
        return self._deduplicate(hints)

    def _recommended_steps(
        self,
        resources: list[dict[str, Any]],
        cloud_alerts: list[dict[str, Any]],
        data_gaps: list[str],
        alerts_result: dict[str, Any],
    ) -> list[str]:
        """给出云平台侧排查和接入建议。"""

        steps: list[str] = []
        for alert in cloud_alerts[:5]:
            target = alert.get("resourceId") or alert.get("service") or alert.get("alertName")
            steps.append(f"在云控制台核对 {target} 的实例事件、资源利用率、网络安全组和最近变更")
        if resources:
            steps.append("把云资源清单与服务拓扑、Kubernetes 节点和告警标签做一致性校验")
        if alerts_result.get("status") == "degraded":
            steps.append("补齐 Alertmanager 接入后重新运行云资源证据分析，获取告警侧云标签")
        if data_gaps:
            steps.append("在告警规则中补充 cloud_provider、account_id、region、resource_id、resource_type、service 标签")
        return self._deduplicate(steps)

    def _status_from_risks(self, risk_signals: list[dict[str, str]], data_gaps: list[str]) -> str:
        """按最高风险映射前端状态。"""

        if any(signal.get("severity") == "high" for signal in risk_signals):
            return "critical"
        if risk_signals or data_gaps:
            return "degraded"
        return "healthy"

    def _resource_aliases(self, resource: dict[str, Any]) -> set[str]:
        """生成资源匹配告警时使用的别名集合。"""

        values = {
            resource.get("resourceId"),
            resource.get("id"),
            resource.get("name"),
            resource.get("service"),
            *[str(item) for item in resource.get("tags") or []],
        }
        return {str(value).strip().lower() for value in values if str(value).strip()}

    def _alert_aliases(self, alert: dict[str, Any]) -> set[str]:
        """生成云告警匹配资源清单时使用的别名集合。"""

        values = {alert.get("resourceId"), alert.get("service"), alert.get("alertName")}
        labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
        values.update(str(value) for value in labels.values())
        return {str(value).strip().lower() for value in values if str(value).strip()}

    def _cloud_alert_key(self, alert: dict[str, Any]) -> str:
        """生成告警指纹，便于后续前端去重。"""

        return "|".join(str(alert.get(key) or "") for key in ["provider", "accountId", "region", "resourceId", "alertName"])

    def _deduplicate(self, items: list[str]) -> list[str]:
        """按原顺序去重文本列表。"""

        seen: set[str] = set()
        results: list[str] = []
        for item in items:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            results.append(text)
        return results

    def _deduplicate_dicts(self, items: list[dict[str, str]], key: str) -> list[dict[str, str]]:
        """按指定字段去重字典列表。"""

        seen: set[str] = set()
        results: list[dict[str, str]] = []
        for item in items:
            marker = str(item.get(key) or "").strip()
            if not marker or marker in seen:
                continue
            seen.add(marker)
            results.append(item)
        return results
