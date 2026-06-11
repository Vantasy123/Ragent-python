"""运维监控服务，统一封装 Prometheus、Alertmanager 和 HTTP 探测能力。"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.services.project_config_service import ProjectConfigService


class MonitoringService:
    """集中处理监控查询，避免 API 路由和 Ops Agent 各自维护一套口径。"""

    METRIC_ALIASES: dict[str, str] = {
        "cpu": '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))',
        "cpu_percent": '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))',
        "memory": "100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))",
        "memory_percent": "100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))",
        "container_cpu": 'sum(rate(container_cpu_usage_seconds_total{name!=""}[5m])) by (name)',
        "container_memory": 'container_memory_usage_bytes{name!=""}',
        "redis_up": 'up{job="redis"}',
        "mysql_up": 'up{job="mysql"}',
        "target_up": "up",
        "probe_success": "probe_success",
    }
    ALLOWED_PROMQL_RE = re.compile(r'^[a-zA-Z0-9_:\{\}\[\]\(\)\.,="\s\+\-\*/%!~|<>]+$')
    BLOCKED_PROMQL_RE = re.compile(r"(?i)([;\r\n]|drop|delete|insert|update|create|alter|shutdown|admin)")

    def __init__(
        self,
        prometheus_url: str | None = None,
        alertmanager_url: str | None = None,
        config_service: ProjectConfigService | None = None,
    ) -> None:
        """允许测试注入监控地址，生产环境默认读取配置。"""

        self.config_service = config_service or ProjectConfigService()
        self.monitoring_config = self.config_service.monitoring()
        # 环境变量优先，未设置时读取 config/monitoring.yml，便于开源用户按文件配置。
        configured_prometheus = self.monitoring_config.get("prometheus_url", "")
        configured_alertmanager = self.monitoring_config.get("alertmanager_url", "")
        self.prometheus_url = (prometheus_url if prometheus_url is not None else settings.PROMETHEUS_URL or configured_prometheus).rstrip("/")
        self.alertmanager_url = (alertmanager_url if alertmanager_url is not None else settings.ALERTMANAGER_URL or configured_alertmanager).rstrip("/")
        self.timeout = float(self.monitoring_config.get("timeout_seconds") or settings.MONITORING_TIMEOUT_SECONDS)

    def monitoring_enabled(self) -> bool:
        """判断监控查询是否已启用。"""

        return bool(getattr(settings, "MONITORING_ENABLED", False) or self.monitoring_config.get("enabled", False))

    async def overview(self) -> dict[str, Any]:
        """聚合后台看板首页需要的健康状态、核心指标和告警摘要。"""

        issues: list[dict[str, Any]] = []
        probes = await self.probes()
        targets = await self.targets()
        alerts = await self.alerts()
        cpu = await self.metric_value("cpu_percent")
        memory = await self.metric_value("memory_percent")

        for item in (targets, alerts, cpu, memory):
            if item.get("status") == "degraded":
                issues.append({"来源": item.get("displayName", "监控源"), "原因": item.get("message", item.get("summary", ""))})

        active_alerts = alerts.get("data", {}).get("items", [])
        failed_probes = [item for item in probes.get("data", {}).get("items", []) if item.get("status") != "healthy"]
        target_items = targets.get("data", {}).get("items", [])
        down_targets = [item for item in target_items if item.get("status") != "healthy"]

        status = "healthy"
        summary = "系统监控状态正常"
        if active_alerts or failed_probes or down_targets:
            status = "critical" if active_alerts or failed_probes else "degraded"
            summary = "存在需要关注的监控异常"
        elif issues:
            status = "degraded"
            summary = "部分监控源不可用，已返回降级数据"

        cards = [
            self._card("serviceHealth", "服务健康", len(failed_probes), "个异常", "healthy" if not failed_probes else "critical"),
            self._card("activeAlerts", "活跃告警", len(active_alerts), "条", "healthy" if not active_alerts else "critical"),
            self._card("cpuPercent", "CPU 使用率", cpu.get("data", {}).get("value"), "%", cpu.get("status", "degraded")),
            self._card("memoryPercent", "内存使用率", memory.get("data", {}).get("value"), "%", memory.get("status", "degraded")),
        ]
        return {
            "status": status,
            "displayName": "运维监控总览",
            "summary": summary,
            "updatedAt": self._now(),
            "cards": cards,
            "services": probes.get("data", {}).get("items", []),
            "metrics": {
                "cpuPercent": cpu,
                "memoryPercent": memory,
            },
            "targets": target_items,
            "alerts": {
                "count": len(active_alerts),
                "items": active_alerts,
            },
            "issues": issues,
        }

    async def probes(self) -> dict[str, Any]:
        """执行后台、前端代理和测试服务的轻量 HTTP 探活。"""

        checks = self.probe_targets()
        items = [await self.http_probe(item["key"], item["name"], item["url"], item) for item in checks]
        failed = [item for item in items if item["status"] != "healthy"]
        return {
            "status": "healthy" if not failed else "critical",
            "displayName": "服务探测",
            "summary": "所有服务探测正常" if not failed else f"发现 {len(failed)} 个服务探测异常",
            "updatedAt": self._now(),
            "data": {"items": items},
        }

    def probe_targets(self) -> list[dict[str, Any]]:
        """合并内置探测、业务服务器和用户自定义探测目标。"""

        checks = [
            {
                "key": "api",
                "name": "后端 API",
                "url": "http://127.0.0.1:8000/api/health",
                "source": "builtin",
                "tags": ["ragent", "api"],
            },
            {
                "key": "frontend",
                "name": "前端入口",
                "url": "http://frontend",
                "source": "builtin",
                "tags": ["ragent", "frontend"],
            },
            {
                "key": "nginxProxy",
                "name": "Nginx 代理",
                "url": "http://frontend/api/health",
                "source": "builtin",
                "tags": ["ragent", "nginx"],
            },
            {
                "key": "opsTestService",
                "name": "运维测试服务",
                "url": "http://ops-test-service",
                "source": "builtin",
                "tags": ["ragent", "ops"],
            },
        ]
        for server in self.config_service.servers():
            if server.get("health_url"):
                checks.append(
                    {
                        "key": f"server:{server['id']}",
                        "name": server["name"],
                        "url": server["health_url"],
                        "source": "server",
                        "env": server.get("env", ""),
                        "owner": server.get("owner", ""),
                        "baseUrl": server.get("base_url", ""),
                        "metricsUrl": server.get("metrics_url", ""),
                        "tags": server.get("tags", []),
                    }
                )
        for probe in self.monitoring_config.get("probes", []):
            if probe.get("url"):
                checks.append(
                    {
                        "key": f"probe:{probe['id']}",
                        "name": probe["name"],
                        "url": probe["url"],
                        "source": "probe",
                        "tags": probe.get("tags", []),
                    }
                )
        return checks

    async def http_probe(self, key: str, name: str, url: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """对单个 HTTP 地址执行探活，并返回前端友好的中文字段。"""

        extra = extra or {}
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
            duration_ms = int((time.perf_counter() - started) * 1000)
            status = "healthy" if response.status_code < 500 else "critical"
            return {
                "key": key,
                "name": name,
                "displayName": name,
                "status": status,
                "statusLabel": "正常" if status == "healthy" else "异常",
                "url": url,
                "source": extra.get("source", ""),
                "env": extra.get("env", ""),
                "owner": extra.get("owner", ""),
                "baseUrl": extra.get("baseUrl", ""),
                "metricsUrl": extra.get("metricsUrl", ""),
                "tags": extra.get("tags", []),
                "statusCode": response.status_code,
                "durationMs": duration_ms,
                "message": f"HTTP {response.status_code}，耗时 {duration_ms} ms",
                "updatedAt": self._now(),
            }
        except Exception as exc:
            return {
                "key": key,
                "name": name,
                "displayName": name,
                "status": "critical",
                "statusLabel": "异常",
                "url": url,
                "source": extra.get("source", ""),
                "env": extra.get("env", ""),
                "owner": extra.get("owner", ""),
                "baseUrl": extra.get("baseUrl", ""),
                "metricsUrl": extra.get("metricsUrl", ""),
                "tags": extra.get("tags", []),
                "statusCode": None,
                "durationMs": None,
                "message": f"探测失败：{exc}",
                "updatedAt": self._now(),
            }

    async def targets(self) -> dict[str, Any]:
        """读取 Prometheus targets 状态。"""

        if not self._prometheus_ready():
            return self._degraded("Prometheus Targets", "Prometheus 未配置或未启用，无法读取采集目标")
        payload = await self._get_json(self._join_url(self.prometheus_url, "/api/v1/targets"), {"state": "any"})
        if payload.get("status") != "success":
            return self._degraded("Prometheus Targets", payload.get("summary", "Prometheus targets 查询失败"))

        active_targets = payload.get("data", {}).get("activeTargets", [])
        items = []
        for target in active_targets if isinstance(active_targets, list) else []:
            labels = target.get("labels") if isinstance(target.get("labels"), dict) else {}
            health = target.get("health") or "unknown"
            items.append(
                {
                    "job": labels.get("job", "unknown"),
                    "instance": labels.get("instance", ""),
                    "scrapeUrl": target.get("scrapeUrl", ""),
                    "status": "healthy" if health == "up" else "critical",
                    "statusLabel": "正常" if health == "up" else "异常",
                    "lastScrape": target.get("lastScrape"),
                    "lastError": target.get("lastError", ""),
                    "labels": labels,
                }
            )
        failed = [item for item in items if item["status"] != "healthy"]
        return {
            "status": "healthy" if not failed else "critical",
            "displayName": "Prometheus 采集目标",
            "summary": f"共 {len(items)} 个采集目标，异常 {len(failed)} 个",
            "updatedAt": self._now(),
            "data": {"items": items},
        }

    async def alerts(self) -> dict[str, Any]:
        """读取 Alertmanager 当前活跃告警。"""

        if not self._alertmanager_ready():
            return self._degraded("Alertmanager 告警", "Alertmanager 未配置或未启用，无法读取当前告警", {"items": [], "count": 0})
        payload = await self._get_json(self._join_url(self.alertmanager_url, "/api/v2/alerts"))
        if payload.get("status") != "success":
            return self._degraded("Alertmanager 告警", payload.get("summary", "Alertmanager 查询失败"), {"items": [], "count": 0})

        raw_alerts = payload.get("data", [])
        items = []
        for alert in raw_alerts if isinstance(raw_alerts, list) else []:
            if not isinstance(alert, dict):
                continue
            status = alert.get("status") if isinstance(alert.get("status"), dict) else {}
            if status.get("state") not in {"active", "unprocessed", "suppressed"}:
                continue
            labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
            annotations = alert.get("annotations") if isinstance(alert.get("annotations"), dict) else {}
            severity = labels.get("severity", "unknown")
            items.append(
                {
                    "name": labels.get("alertname", "unknown"),
                    "displayName": labels.get("alertname", "unknown"),
                    "severity": severity,
                    "severityLabel": self._severity_label(severity),
                    "summary": annotations.get("summary") or annotations.get("description") or "",
                    "description": annotations.get("description", ""),
                    "startsAt": alert.get("startsAt"),
                    "labels": labels,
                    "annotations": annotations,
                }
            )
        return {
            "status": "healthy" if not items else "critical",
            "displayName": "活跃告警",
            "summary": "当前没有活跃告警" if not items else f"当前有 {len(items)} 条活跃告警",
            "updatedAt": self._now(),
            "data": {"items": items, "count": len(items)},
        }

    async def alert_correlations(self) -> dict[str, Any]:
        """对当前活跃告警做轻量降噪和影响面聚合，作为 AIOps RCA 的入口上下文。"""

        alerts = await self.alerts()
        if alerts.get("status") == "degraded":
            return self._degraded("告警关联分析", alerts.get("summary", "Alertmanager 不可用"), {"groups": [], "affectedServices": []})

        items = alerts.get("data", {}).get("items", [])
        groups = self._group_alerts(items if isinstance(items, list) else [])
        affected_services = sorted({service for group in groups for service in group["affectedServices"]})
        critical_groups = [group for group in groups if group["severity"] == "critical"]
        noise_reduction = max(0, len(items) - len(groups))
        return {
            "status": "healthy" if not critical_groups else "critical",
            "displayName": "告警关联分析",
            "summary": (
                "当前没有需要关联分析的活跃告警"
                if not groups
                else f"聚合 {len(items)} 条活跃告警为 {len(groups)} 个告警组，涉及 {len(affected_services)} 个服务"
            ),
            "updatedAt": self._now(),
            "data": {
                "alertCount": len(items),
                "groupCount": len(groups),
                "noiseReduction": noise_reduction,
                "affectedServices": affected_services,
                "groups": groups,
            },
        }

    async def change_correlations(self) -> dict[str, Any]:
        """关联活跃告警中的发布、提交和版本线索，为 RCA 提供变更证据。"""

        alerts = await self.alerts()
        if alerts.get("status") == "degraded":
            return self._degraded(
                "变更关联分析",
                alerts.get("summary", "Alertmanager 不可用，无法关联变更"),
                {"affectedServices": [], "correlatedChanges": [], "dataGaps": ["缺少活跃告警数据，无法提取变更线索"]},
            )

        items = alerts.get("data", {}).get("items", [])
        alert_items = items if isinstance(items, list) else []
        inventory = self._service_inventory()
        affected_services = sorted({self._alert_service((item.get("labels") or {}) if isinstance(item, dict) else {}) for item in alert_items})
        candidates = self._change_candidates_from_alerts(alert_items, inventory)
        data_gaps = self._change_data_gaps(alert_items, candidates)
        high_risk = [item for item in candidates if item.get("riskLevel") == "high"]
        return {
            "status": "critical" if high_risk else "healthy",
            "displayName": "变更关联分析",
            "summary": (
                "未发现活跃告警中的变更线索"
                if not candidates
                else f"从 {len(alert_items)} 条活跃告警中识别 {len(candidates)} 个疑似相关变更，涉及 {len(affected_services)} 个服务"
            ),
            "updatedAt": self._now(),
            "data": {
                "alertCount": len(alert_items),
                "changeCount": len(candidates),
                "affectedServices": affected_services,
                "correlatedChanges": candidates,
                "dataGaps": data_gaps,
                "recommendedNextSteps": self._change_recommended_steps(candidates, data_gaps),
            },
        }

    def _group_alerts(self, alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """按服务、实例和严重等级聚合告警，降低重复告警对诊断 Agent 的干扰。"""

        buckets: dict[str, dict[str, Any]] = {}
        for alert in alerts:
            labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
            service = self._alert_service(labels)
            instance = str(labels.get("instance") or labels.get("pod") or labels.get("node") or "unknown")
            severity = str(alert.get("severity") or labels.get("severity") or "unknown")
            alert_name = str(alert.get("name") or labels.get("alertname") or "unknown")
            group_key = f"{service}|{instance}|{severity}"
            bucket = buckets.setdefault(
                group_key,
                {
                    "groupKey": group_key,
                    "severity": severity,
                    "severityLabel": self._severity_label(severity),
                    "affectedServices": set(),
                    "instances": set(),
                    "alertNames": set(),
                    "alerts": [],
                    "rootCauseHints": set(),
                    "recommendedNextSteps": set(),
                    "firstSeenAt": alert.get("startsAt"),
                },
            )
            bucket["affectedServices"].add(service)
            bucket["instances"].add(instance)
            bucket["alertNames"].add(alert_name)
            bucket["alerts"].append(alert)
            for hint in self._root_cause_hints(alert_name, labels, alert.get("summary", "")):
                bucket["rootCauseHints"].add(hint)
            for step in self._recommended_steps(alert_name, labels):
                bucket["recommendedNextSteps"].add(step)
            if alert.get("startsAt") and (not bucket["firstSeenAt"] or str(alert.get("startsAt")) < str(bucket["firstSeenAt"])):
                bucket["firstSeenAt"] = alert.get("startsAt")

        results = []
        for bucket in buckets.values():
            alerts_in_group = bucket["alerts"]
            results.append(
                {
                    "groupKey": bucket["groupKey"],
                    "severity": bucket["severity"],
                    "severityLabel": bucket["severityLabel"],
                    "affectedServices": sorted(bucket["affectedServices"]),
                    "instances": sorted(bucket["instances"]),
                    "alertNames": sorted(bucket["alertNames"]),
                    "alertCount": len(alerts_in_group),
                    "firstSeenAt": bucket["firstSeenAt"],
                    "summary": self._alert_group_summary(bucket),
                    "rootCauseHints": sorted(bucket["rootCauseHints"]),
                    "recommendedNextSteps": sorted(bucket["recommendedNextSteps"]),
                    "sampleAlerts": alerts_in_group[:3],
                }
            )
        return sorted(results, key=lambda item: (self._severity_rank(item["severity"]), -item["alertCount"], item["groupKey"]))

    def _alert_service(self, labels: dict[str, Any]) -> str:
        """从常见 Alertmanager 标签中提取服务名，缺失时回退到 job。"""

        for key in ("service", "app", "application", "component", "job", "namespace"):
            value = str(labels.get(key) or "").strip()
            if value:
                return value
        return "unknown"

    def _root_cause_hints(self, alert_name: str, labels: dict[str, Any], summary: str) -> list[str]:
        """根据告警名称和标签给出 RCA 初筛线索。"""

        text = f"{alert_name} {summary} {' '.join(str(value) for value in labels.values())}".lower()
        hints: list[str] = []
        if any(token in text for token in ("targetdown", "up == 0", "probe", "unreachable", "connection refused")):
            hints.append("采集目标或服务探活失败，优先检查实例存活、网络连通性和服务端口")
        if any(token in text for token in ("cpu", "load", "throttle")):
            hints.append("资源饱和风险，优先检查 CPU 使用率、容器限额和最近流量变化")
        if any(token in text for token in ("memory", "oom", "outofmemory")):
            hints.append("内存压力风险，优先检查内存水位、OOM 记录和缓存增长")
        if any(token in text for token in ("latency", "duration", "timeout", "slow")):
            hints.append("请求延迟异常，优先关联 Trace 慢 span、下游依赖和数据库慢查询")
        if any(token in text for token in ("mysql", "redis", "database", "db")):
            hints.append("中间件或数据库异常，优先检查连接数、慢查询、主从状态和错误日志")
        if any(token in text for token in ("pod", "kube", "container", "deployment")):
            hints.append("Kubernetes 工作负载异常，优先检查 Pod 事件、重启次数和最近发布变更")
        return hints or ["需要结合 Metrics、Logs、Traces 和近期变更继续分析根因"]

    def _recommended_steps(self, alert_name: str, labels: dict[str, Any]) -> list[str]:
        """为告警组生成后续诊断动作建议，供计划 Agent 生成 Runbook 步骤。"""

        service = self._alert_service(labels)
        instance = str(labels.get("instance") or labels.get("pod") or labels.get("node") or "")
        steps = [
            f"查看 {service} 的最近指标趋势和同一时间窗口内的活跃告警",
            f"检索 {service} 的 Runbook、历史事故和最近变更记录",
        ]
        if instance:
            steps.append(f"检查实例 {instance} 的日志、重启记录和资源水位")
        if "down" in alert_name.lower() or "up" in alert_name.lower():
            steps.append("执行服务探活并确认是否存在网络、端口或依赖不可达")
        return steps

    def _alert_group_summary(self, bucket: dict[str, Any]) -> str:
        """生成告警组摘要，方便前端和诊断 Agent 快速理解影响面。"""

        service_text = "、".join(sorted(bucket["affectedServices"]))
        alert_text = "、".join(sorted(bucket["alertNames"]))
        instance_count = len(bucket["instances"])
        return f"{service_text} 出现 {len(bucket['alerts'])} 条 {bucket['severityLabel']}告警，涉及 {instance_count} 个实例，主要告警：{alert_text}"

    def _change_candidates_from_alerts(self, alerts: list[dict[str, Any]], inventory: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        """从告警标签和注解中抽取发布、提交、镜像等变更候选。"""

        buckets: dict[str, dict[str, Any]] = {}
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
            annotations = alert.get("annotations") if isinstance(alert.get("annotations"), dict) else {}
            merged = {**annotations, **labels}
            change = self._extract_change_metadata(merged)
            if not change:
                continue
            service = self._alert_service(labels)
            server = inventory.get(service, {})
            key_parts = [service, change.get("changeId") or change.get("gitSha") or change.get("version") or change.get("image") or "unknown"]
            key = "|".join(key_parts)
            bucket = buckets.setdefault(
                key,
                {
                    "changeKey": key,
                    "service": service,
                    "serviceName": server.get("name") or service,
                    "owner": server.get("owner", ""),
                    "env": server.get("env", ""),
                    "changeId": change.get("changeId", ""),
                    "version": change.get("version", ""),
                    "gitSha": change.get("gitSha", ""),
                    "image": change.get("image", ""),
                    "pipeline": change.get("pipeline", ""),
                    "changedAt": change.get("changedAt", ""),
                    "alertNames": set(),
                    "alertSeverities": set(),
                    "evidence": [],
                    "firstAlertAt": alert.get("startsAt"),
                },
            )
            alert_name = str(alert.get("name") or labels.get("alertname") or "unknown")
            severity = str(alert.get("severity") or labels.get("severity") or "unknown")
            bucket["alertNames"].add(alert_name)
            bucket["alertSeverities"].add(severity)
            bucket["evidence"].append(
                {
                    "alertName": alert_name,
                    "severity": severity,
                    "startsAt": alert.get("startsAt"),
                    "summary": alert.get("summary", ""),
                }
            )
            if alert.get("startsAt") and (not bucket["firstAlertAt"] or str(alert.get("startsAt")) < str(bucket["firstAlertAt"])):
                bucket["firstAlertAt"] = alert.get("startsAt")

        results: list[dict[str, Any]] = []
        for item in buckets.values():
            severities = sorted(item.pop("alertSeverities"), key=self._severity_rank)
            alert_names = sorted(item.pop("alertNames"))
            risk_level = "high" if "critical" in severities else "medium" if "warning" in severities else "low"
            confidence = self._change_confidence(item, alert_names)
            item["alertNames"] = alert_names
            item["riskLevel"] = risk_level
            item["confidence"] = confidence
            item["summary"] = self._change_summary(item)
            item["rollbackHint"] = self._rollback_hint(item)
            results.append(item)
        return sorted(results, key=lambda item: ({"high": 0, "medium": 1, "low": 2}.get(item["riskLevel"], 3), item["service"], item["changeKey"]))

    def _extract_change_metadata(self, payload: dict[str, Any]) -> dict[str, str]:
        """从常见发布系统、Git 和镜像标签字段中提取变更元数据。"""

        aliases = {
            "changeId": ["change_id", "change", "deployment", "deployment_id", "release", "release_id", "rollout", "revision"],
            "version": ["version", "app_version", "release_version", "image_tag", "tag"],
            "gitSha": ["git_sha", "commit", "commit_sha", "revision_sha", "vcs_ref"],
            "image": ["image", "container_image"],
            "pipeline": ["pipeline", "pipeline_id", "ci_pipeline", "build", "build_id", "job_url"],
            "changedAt": ["changed_at", "deployed_at", "deployment_time", "release_time"],
        }
        result: dict[str, str] = {}
        lowered = {str(key).lower(): str(value).strip() for key, value in payload.items() if value not in (None, "")}
        for target_key, keys in aliases.items():
            for key in keys:
                value = lowered.get(key.lower())
                if value:
                    result[target_key] = value
                    break
        return result

    def _service_inventory(self) -> dict[str, dict[str, Any]]:
        """把接入配置中的服务映射为 RCA 可用的 CMDB 轻量视图。"""

        inventory: dict[str, dict[str, Any]] = {}
        for server in self.config_service.servers():
            keys = [server.get("id"), server.get("name"), *(server.get("tags") or [])]
            for key in keys:
                text = str(key or "").strip()
                if text:
                    inventory[text] = server
        return inventory

    def _change_data_gaps(self, alerts: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[str]:
        """生成变更关联的数据缺口，帮助用户补齐 CI/CD、Git 或 CMDB 标签。"""

        gaps: list[str] = []
        if alerts and not candidates:
            gaps.append("活跃告警未携带 change_id、git_sha、version、image 或 pipeline 标签，无法直接关联发布变更")
        if candidates and any(not item.get("changedAt") for item in candidates):
            gaps.append("部分变更缺少 changed_at/deployed_at 时间，无法精确判断告警和发布的时间先后")
        if candidates and any(not item.get("owner") for item in candidates):
            gaps.append("部分服务未在接入配置中维护 owner，无法自动定位负责团队")
        if not alerts:
            gaps.append("当前没有活跃告警，变更关联仅能等待告警或外部变更源接入后分析")
        return gaps

    def _change_recommended_steps(self, candidates: list[dict[str, Any]], data_gaps: list[str]) -> list[str]:
        """根据变更候选生成后续排查、回滚和数据接入建议。"""

        steps: list[str] = []
        for item in candidates[:5]:
            service = item.get("serviceName") or item.get("service") or "相关服务"
            version = item.get("version") or item.get("gitSha") or item.get("changeId") or item.get("image") or "当前变更"
            steps.append(f"核对 {service} 的发布记录 {version}，确认告警是否在发布后出现")
            steps.append(f"检索 {service} 的回滚 Runbook，并评估回滚对依赖服务的影响")
        if data_gaps:
            steps.append("在告警规则或发布流水线中补充 change_id、git_sha、version、deployed_at 等标签")
        return self._deduplicate(steps)

    def _change_confidence(self, item: dict[str, Any], alert_names: list[str]) -> str:
        """按元数据完整度给变更候选打置信等级。"""

        score = 0
        if item.get("service"):
            score += 1
        if item.get("gitSha") or item.get("version") or item.get("changeId"):
            score += 1
        if item.get("changedAt"):
            score += 1
        if alert_names:
            score += 1
        if score >= 3:
            return "high"
        if score == 2:
            return "medium"
        return "low"

    def _change_summary(self, item: dict[str, Any]) -> str:
        """生成变更候选摘要，便于报告直接引用。"""

        marker = item.get("version") or item.get("gitSha") or item.get("changeId") or item.get("image") or "未知变更"
        service = item.get("serviceName") or item.get("service") or "未知服务"
        alerts = "、".join(item.get("alertNames") or [])
        suffix = f"，关联告警：{alerts}" if alerts else ""
        return f"{service} 存在疑似相关变更 {marker}{suffix}"

    def _rollback_hint(self, item: dict[str, Any]) -> str:
        """给出保守回滚提示，实际执行仍必须走审批。"""

        service = item.get("serviceName") or item.get("service") or "相关服务"
        return f"如确认变更导致故障，先查阅 {service} 回滚 Runbook，回滚或重启必须通过审批流程执行"

    def _deduplicate(self, lines: list[str]) -> list[str]:
        """按原顺序去重列表内容。"""

        seen: set[str] = set()
        results: list[str] = []
        for line in lines:
            text = str(line or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            results.append(text)
        return results

    def _severity_rank(self, severity: str) -> int:
        """严重等级排序，数值越小优先级越高。"""

        return {"critical": 0, "warning": 1, "info": 2}.get(severity, 3)

    async def metric_value(self, metric: str) -> dict[str, Any]:
        """查询单个指标的即时值。"""

        query = self.metric_query(metric)
        result = await self.prometheus_instant_query(query, enforce_safe=False)
        if result.get("status") != "healthy":
            return result
        value = self.first_value(result)
        return {
            "status": "healthy",
            "displayName": self.metric_label(metric),
            "summary": f"{self.metric_label(metric)} 当前值 {value:.2f}",
            "updatedAt": self._now(),
            "data": {"metric": metric, "query": query, "value": round(value, 4)},
        }

    async def metric_series(self, metric: str, minutes: int = 30) -> dict[str, Any]:
        """查询单个指标的最近趋势。"""

        safe_minutes = max(1, min(int(minutes or 30), 24 * 60))
        query = self.metric_query(metric)
        end = time.time()
        start = end - safe_minutes * 60
        step = max(15, int((safe_minutes * 60) / 60))
        result = await self.prometheus_range_query(query, start, end, step, enforce_safe=False)
        if result.get("status") != "healthy":
            return result
        points = self.points(result)
        values = [point["value"] for point in points]
        return {
            "status": "healthy",
            "displayName": self.metric_label(metric),
            "summary": f"{self.metric_label(metric)} 最近 {safe_minutes} 分钟返回 {len(points)} 个点",
            "updatedAt": self._now(),
            "data": {
                "metric": metric,
                "metricLabel": self.metric_label(metric),
                "query": query,
                "points": points,
                "min": min(values) if values else None,
                "max": max(values) if values else None,
                "avg": round(sum(values) / len(values), 4) if values else None,
            },
        }

    async def prometheus_instant_query(self, query: str, query_time: float | None = None, enforce_safe: bool = True) -> dict[str, Any]:
        """执行 Prometheus 即时查询。"""

        safe_query = self.metric_query(query)
        if not safe_query:
            return self._degraded("Prometheus 查询", "PromQL 不能为空", error="invalid_promql")
        if enforce_safe and not self.is_safe_promql(safe_query):
            return self._degraded("Prometheus 查询", "PromQL 不在允许范围内", error="unsafe_promql")
        if not self._prometheus_ready():
            return self._degraded("Prometheus 查询", "Prometheus 未配置或未启用，无法执行查询")

        params: dict[str, Any] = {"query": safe_query}
        if query_time is not None:
            params["time"] = query_time
        payload = await self._get_json(self._join_url(self.prometheus_url, "/api/v1/query"), params)
        if payload.get("status") != "success":
            return self._degraded("Prometheus 查询", payload.get("summary", "Prometheus 查询失败"))
        data = payload.get("data", {})
        result = data.get("result", [])
        return {
            "status": "healthy",
            "displayName": "Prometheus 查询",
            "summary": f"Prometheus 查询成功，返回 {len(result) if isinstance(result, list) else 0} 组结果",
            "updatedAt": self._now(),
            "data": {"query": safe_query, "result": result, "resultType": data.get("resultType")},
        }

    async def prometheus_range_query(
        self,
        query: str,
        start: float,
        end: float,
        step: int,
        enforce_safe: bool = True,
    ) -> dict[str, Any]:
        """执行 Prometheus 区间查询。"""

        safe_query = self.metric_query(query)
        if enforce_safe and not self.is_safe_promql(safe_query):
            return self._degraded("Prometheus 趋势查询", "PromQL 不在允许范围内", error="unsafe_promql")
        if not self._prometheus_ready():
            return self._degraded("Prometheus 趋势查询", "Prometheus 未配置或未启用，无法执行趋势查询")
        payload = await self._get_json(
            self._join_url(self.prometheus_url, "/api/v1/query_range"),
            {"query": safe_query, "start": start, "end": end, "step": step},
        )
        if payload.get("status") != "success":
            return self._degraded("Prometheus 趋势查询", payload.get("summary", "Prometheus 趋势查询失败"))
        data = payload.get("data", {})
        result = data.get("result", [])
        return {
            "status": "healthy",
            "displayName": "Prometheus 趋势查询",
            "summary": f"Prometheus 趋势查询成功，返回 {len(result) if isinstance(result, list) else 0} 组序列",
            "updatedAt": self._now(),
            "data": {"query": safe_query, "result": result, "resultType": data.get("resultType")},
        }

    def is_safe_promql(self, query: str) -> bool:
        """对开放给后台的 PromQL 做基础白名单校验。"""

        text = str(query or "").strip()
        if not text or len(text) > 300:
            return False
        if self.BLOCKED_PROMQL_RE.search(text):
            return False
        return bool(self.ALLOWED_PROMQL_RE.match(text))

    def metric_query(self, metric: str) -> str:
        """把前端常用指标别名转换为 PromQL。"""

        text = str(metric or "").strip()
        return self.METRIC_ALIASES.get(text, text)

    def metric_label(self, metric: str) -> str:
        """返回指标中文名称。"""

        labels = {
            "cpu": "CPU 使用率",
            "cpu_percent": "CPU 使用率",
            "memory": "内存使用率",
            "memory_percent": "内存使用率",
            "container_cpu": "容器 CPU",
            "container_memory": "容器内存",
            "redis_up": "Redis 状态",
            "mysql_up": "MySQL 状态",
            "target_up": "采集目标状态",
            "probe_success": "服务探测状态",
        }
        return labels.get(metric, metric)

    def first_value(self, result: dict[str, Any]) -> float:
        """从 Prometheus instant vector 中取第一个数值。"""

        rows = result.get("data", {}).get("result") or []
        if not rows:
            return 0.0
        value = rows[0].get("value") if isinstance(rows[0], dict) else None
        if not isinstance(value, list) or len(value) < 2:
            return 0.0
        try:
            return float(value[1])
        except (TypeError, ValueError):
            return 0.0

    def points(self, result: dict[str, Any]) -> list[dict[str, float]]:
        """把 Prometheus matrix 结果压平为前端图表点位。"""

        series = result.get("data", {}).get("result") or []
        points: list[dict[str, float]] = []
        for item in series[:5]:
            if not isinstance(item, dict):
                continue
            for raw_time, raw_value in item.get("values") or []:
                try:
                    points.append({"timestamp": float(raw_time), "value": float(raw_value)})
                except (TypeError, ValueError):
                    continue
        return points[-240:]

    async def tool_system_metrics(self) -> dict[str, Any]:
        """为 OpsToolkit 适配旧 system_metrics 返回结构。"""

        cpu = await self.metric_value("cpu_percent")
        memory = await self.metric_value("memory_percent")
        if cpu.get("status") != "healthy" and memory.get("status") != "healthy":
            return {
                "success": True,
                "summary": "监控源未配置或不可用，已返回基础占位指标",
                "data": {"cpuPercent": 0, "memoryPercent": 0, "source": "fallback"},
                "error": "monitoring_not_configured",
            }
        return {
            "success": True,
            "summary": f"CPU {cpu.get('data', {}).get('value', 0):.2f}%，内存 {memory.get('data', {}).get('value', 0):.2f}%",
            "data": {
                "cpuPercent": cpu.get("data", {}).get("value", 0),
                "memoryPercent": memory.get("data", {}).get("value", 0),
                "source": "prometheus",
                "raw": {"cpu": cpu, "memory": memory},
            },
            "error": "",
        }

    async def tool_alert_status(self) -> dict[str, Any]:
        """为 OpsToolkit 适配旧 alert_status 返回结构。"""

        result = await self.alerts()
        items = result.get("data", {}).get("items", [])
        return {
            "success": result.get("status") in {"healthy", "critical"},
            "summary": result.get("summary", ""),
            "data": {"alerts": items, "count": len(items)},
            "error": "" if result.get("status") in {"healthy", "critical"} else "monitoring_not_configured",
        }

    async def tool_alert_correlations(self) -> dict[str, Any]:
        """为 OpsToolkit 适配告警关联分析结果，供诊断 Agent 直接消费。"""

        result = await self.alert_correlations()
        data = result.get("data", {}) if isinstance(result.get("data"), dict) else {}
        return {
            "success": result.get("status") in {"healthy", "critical"},
            "summary": result.get("summary", ""),
            "data": data,
            "error": "" if result.get("status") in {"healthy", "critical"} else result.get("error", "monitoring_not_configured"),
        }

    async def tool_change_correlations(self) -> dict[str, Any]:
        """为 OpsToolkit 适配变更关联分析结果，供 RCA 和计划 Agent 消费。"""

        result = await self.change_correlations()
        data = result.get("data", {}) if isinstance(result.get("data"), dict) else {}
        return {
            "success": result.get("status") in {"healthy", "critical"},
            "summary": result.get("summary", ""),
            "data": data,
            "error": "" if result.get("status") in {"healthy", "critical"} else result.get("error", "monitoring_not_configured"),
        }

    async def tool_metric_trend(self, metric: str = "cpu_percent", minutes: int = 30) -> dict[str, Any]:
        """为 OpsToolkit 适配旧 metric_trend 返回结构。"""

        result = await self.metric_series(metric, minutes)
        return {
            "success": result.get("status") == "healthy",
            "summary": result.get("summary", ""),
            "data": result.get("data", {}),
            "error": "" if result.get("status") == "healthy" else "monitoring_query_failed",
        }

    async def tool_prometheus_query(self, query: str = "", time: float | None = None) -> dict[str, Any]:
        """为 OpsToolkit 适配旧 prometheus_query 返回结构。"""

        result = await self.prometheus_instant_query(query, query_time=time)
        return {
            "success": result.get("status") == "healthy",
            "summary": result.get("summary", ""),
            "data": result.get("data", {}),
            "error": "" if result.get("status") == "healthy" else result.get("error", "monitoring_query_failed"),
        }

    async def _get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """执行 GET 请求并把异常统一转换为降级结构。"""

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
            payload = response.json()
            # Prometheus 自带 status/data 结构，Alertmanager 直接返回数组；这里统一兼容两类响应。
            if isinstance(payload, dict) and "status" in payload:
                return payload
            return {"status": "success", "data": payload}
        except Exception as exc:
            return {"status": "failed", "summary": f"监控查询失败：{exc}", "data": {}}

    def _prometheus_ready(self) -> bool:
        """判断 Prometheus 是否具备查询条件。"""

        return self.monitoring_enabled() and bool(self.prometheus_url)

    def _alertmanager_ready(self) -> bool:
        """判断 Alertmanager 是否具备查询条件。"""

        return self.monitoring_enabled() and bool(self.alertmanager_url)

    def _degraded(self, display_name: str, message: str, data: dict[str, Any] | None = None, error: str = "monitoring_degraded") -> dict[str, Any]:
        """返回统一降级结构，前端可直接渲染错误态。"""

        return {
            "status": "degraded",
            "displayName": display_name,
            "summary": message,
            "message": message,
            "updatedAt": self._now(),
            "data": data or {},
            "error": error,
        }

    def _card(self, key: str, label: str, value: Any, unit: str, status: str) -> dict[str, Any]:
        """生成总览卡片数据。"""

        return {
            "key": key,
            "label": label,
            "displayName": label,
            "value": 0 if value is None else value,
            "unit": unit,
            "status": status,
            "statusLabel": self._status_label(status),
        }

    def _status_label(self, status: str) -> str:
        """把内部状态转换为中文标签。"""

        return {"healthy": "正常", "degraded": "降级", "critical": "异常"}.get(status, "未知")

    def _severity_label(self, severity: str) -> str:
        """把告警等级转换为中文标签。"""

        return {"critical": "严重", "warning": "警告", "info": "提示"}.get(severity, severity or "未知")

    def _join_url(self, base: str, path: str) -> str:
        """拼接监控服务地址。"""

        return f"{base.rstrip('/')}/{path.lstrip('/')}"

    def _now(self) -> str:
        """生成 UTC ISO 时间戳，方便前端统一展示。"""

        return datetime.now(timezone.utc).isoformat()
