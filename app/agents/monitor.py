"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

from app.agents.base import AgentRole, AgentStep, BaseAgent, ToolSpec
from app.agents.tools import OpsToolkit


class MonitorAgent(BaseAgent):
    """监控 Agent，负责性能、资源和告警类检查。"""

    role = AgentRole.MONITOR
    name = "monitor"
    description = "采集运行指标、容器资源、响应时间和告警状态。"

    def __init__(self, toolkit: OpsToolkit | None = None) -> None:
        self.toolkit = toolkit or OpsToolkit()
        super().__init__(self.toolkit.tools)

    def tool_specs(self) -> list[ToolSpec]:
        """监控 Agent 使用指标类只读工具。"""

        names = {"system_metrics", "container_stats", "response_time_probe", "alert_status", "metric_trend"}
        return [spec for spec in self.toolkit.specs() if spec.name in names]

    def _deterministic_plan(self, task: str, context: dict | None = None) -> list[AgentStep]:
        """根据性能相关关键词决定是否追加资源和响应时间检查。"""

        text = task.lower()
        steps = [
            AgentStep("采集系统指标", "system_metrics", assigned_agent=self.name),
            AgentStep("查询告警状态", "alert_status", assigned_agent=self.name),
        ]
        if any(key in text for key in ["慢", "耗时", "性能", "latency", "timeout", "超时"]):
            # 使用空 url 让工具层自动选择容器内可达的默认健康检查地址。
            steps.append(AgentStep("探测后端响应时间", "response_time_probe", {"url": "", "count": 5}, self.name))
        if any(key in text for key in ["cpu", "内存", "资源", "容器"]):
            steps.append(AgentStep("检查后端容器资源", "container_stats", {"service": "ragent-api"}, self.name))
            steps.append(AgentStep("查询 CPU 趋势", "metric_trend", {"metric": "cpu_percent", "minutes": 30}, self.name))
        return steps
