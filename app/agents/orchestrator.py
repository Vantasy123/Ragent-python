"""运维 Agent 编排器，实现 Plan-Execute-Replan 循环。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from langchain_core.messages import HumanMessage

from app.agents.base import AgentRole, AgentStep, BaseAgent, StepStatus, ToolSpec
from app.agents.memory import SharedMemory
from app.agents.tool_registry import ToolCallRequest, ToolCallResult, UnifiedToolRegistry
from app.agents.tools import OpsToolkit
from app.rag.workflow import build_primary_llm


OPS_SERVICE_ALIASES = {
    "api": "ragent-api",
    "backend": "ragent-api",
    "ragent-api": "ragent-api",
    "后端": "ragent-api",
    "服务端": "ragent-api",
    "frontend": "ragent-frontend",
    "ragent-frontend": "ragent-frontend",
    "front": "ragent-frontend",
    "nginx": "ragent-frontend",
    "前端": "ragent-frontend",
    "mysql": "mysql",
    "ragent-mysql": "ragent-mysql",
    "postgres": "postgres",
    "ragent-postgres": "ragent-postgres",
    "ops-test-service": "ops-test-service",
}

OPS_SERVICE_TOOLS = {
    "container_logs",
    "container_inspect",
    "container_stats",
    "log_analyzer",
    "compose_restart_service",
}

SIMPLE_OPS_KEYWORDS = {
    "日志",
    "log",
    "logs",
    "健康",
    "health",
    "状态",
    "status",
    "502",
    "端口",
    "port",
    "前端",
    "frontend",
    "后端",
    "backend",
    "api",
    "慢",
    "性能",
    "timeout",
    "超时",
    "cpu",
    "内存",
    "重启",
    "restart",
    "恢复",
}


AGENT_REGISTRY = {
    "planner": {"name": "计划 Agent", "description": "查询知识库并生成运维执行计划"},
    "executor": {"name": "执行 Agent", "description": "按计划单步调用白名单工具"},
    "replanner": {"name": "重规划 Agent", "description": "根据观察结果判断完成、继续或修订计划"},
    "diagnostics": {"name": "诊断 Agent", "description": "兼容旧前端展示的诊断能力"},
    "monitor": {"name": "监控 Agent", "description": "兼容旧前端展示的监控能力"},
    "knowledge": {"name": "知识 Agent", "description": "兼容旧前端展示的知识库能力"},
}


@dataclass
class PlanStep:
    """Plan-Execute-Replan 流程中的计划步骤。"""

    title: str
    tool_name: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    assigned_agent: str = "executor"

    def to_agent_step(self) -> AgentStep:
        """转换为现有 AgentStep，复用持久化和审批结构。"""

        return AgentStep(
            title=self.title,
            tool_name=self.tool_name,
            args=self.args,
            assigned_agent=self.assigned_agent,
            reasoning=self.reasoning,
        )


@dataclass
class ReplanDecision:
    """Replanner 对当前计划状态的判断。"""

    action: str
    reason: str
    new_steps: list[PlanStep] = field(default_factory=list)
    final_report: str = ""


class PlannerAgent:
    """运维计划 Agent，优先结合知识库生成执行计划。"""

    name = "planner"

    def __init__(self, registry: UnifiedToolRegistry) -> None:
        self.registry = registry

    async def create_plan(self, task: str, knowledge: ToolCallResult | None = None) -> list[AgentStep]:
        """生成运维计划，模型失败时回退到确定性计划。"""

        if self._is_simple_ops_task(task):
            return [step.to_agent_step() for step in self._deterministic_plan(task)]

        try:
            llm_steps = await self._llm_plan(task, knowledge)
            if llm_steps:
                return [step.to_agent_step() for step in llm_steps]
        except Exception:
            pass
        return [step.to_agent_step() for step in self._deterministic_plan(task)]

    async def _llm_plan(self, task: str, knowledge: ToolCallResult | None) -> list[PlanStep]:
        """调用主模型生成 JSON 计划。"""

        tools = self._compact_tool_specs()
        knowledge_text = self._compact_knowledge(knowledge)
        prompt = (
            "你是 Ragent 运维 Planner，需要生成安全、可执行的排障计划。\n"
            "只能输出 JSON，不要输出 Markdown。格式：{\"steps\":[{\"title\":\"步骤标题\",\"tool\":\"工具名\",\"args\":{},\"reasoning\":\"原因\"}]}\n"
            "要求：优先使用只读工具；写操作可以出现在计划中，但必须由审批流程执行；最多 6 步。\n\n"
            f"可用工具：{json.dumps(tools, ensure_ascii=False)}\n"
            f"服务名白名单：{json.dumps(sorted(set(OPS_SERVICE_ALIASES.values())), ensure_ascii=False)}\n"
            "如果用户只说“后端/API/服务端”，service 必须使用 ragent-api；只说“前端/nginx”，service 必须使用 ragent-frontend。\n"
            f"知识库结果：{knowledge_text}\n"
            f"用户问题：{task}"
        )
        llm = build_primary_llm(streaming=False)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        data = self._parse_json(getattr(response, "content", ""))
        raw_steps = data.get("steps") if isinstance(data, dict) else None
        if not isinstance(raw_steps, list):
            return []

        allowed = set(self.registry.tools)
        steps: list[PlanStep] = []
        for item in raw_steps[:6]:
            if not isinstance(item, dict):
                continue
            tool_name = str(item.get("tool") or item.get("tool_name") or "")
            if tool_name and tool_name not in allowed:
                continue
            args = item.get("args") if isinstance(item.get("args"), dict) else {}
            args = self._normalize_tool_args(task, tool_name, args)
            steps.append(
                PlanStep(
                    title=str(item.get("title") or tool_name or "分析问题"),
                    tool_name=tool_name,
                    args=args,
                    reasoning=str(item.get("reasoning") or ""),
                )
            )
        return steps

    def _is_simple_ops_task(self, task: str) -> bool:
        """判断是否为可直接用规则计划处理的常见运维任务。"""

        text = task.lower()
        return any(keyword in text or keyword in task for keyword in SIMPLE_OPS_KEYWORDS)

    def _compact_tool_specs(self) -> list[dict[str, Any]]:
        """压缩传给 Planner 的工具描述，减少 LLM prompt 体积。"""

        allowed_categories = {"ops", "knowledge", "system"}
        compacted: list[dict[str, Any]] = []
        for item in self.registry.list_tools(audience="admin"):
            if item.get("category") not in allowed_categories:
                continue
            compacted.append(
                {
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "args": item.get("argsSchema") or item.get("args_schema") or {},
                    "risk": item.get("riskLevel") or item.get("risk_level"),
                    "requiresApproval": item.get("requiresApproval", False),
                }
            )
        return compacted

    def _compact_knowledge(self, knowledge: ToolCallResult | None) -> str:
        """只保留前两条知识库摘要，避免 Planner 输入过长。"""

        if not knowledge:
            return "{}"
        payload = knowledge.to_dict()
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        rows = data.get("value") or data.get("chunks") or []
        if not isinstance(rows, list):
            return json.dumps(payload, ensure_ascii=False)[:1200]

        compacted = []
        for row in rows[:2]:
            if not isinstance(row, dict):
                compacted.append({"content": str(row)[:400]})
                continue
            compacted.append(
                {
                    "content": str(row.get("content") or "")[:400],
                    "source": (row.get("metadata") or {}).get("source") if isinstance(row.get("metadata"), dict) else "",
                }
            )
        return json.dumps(compacted, ensure_ascii=False)

    def _normalize_tool_args(self, task: str, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """规范模型生成的工具参数，避免服务名越过运维白名单。"""

        normalized = dict(args)
        if tool_name not in OPS_SERVICE_TOOLS:
            return normalized

        raw_service = str(normalized.get("service") or "").strip()
        service_key = raw_service.lower()
        if raw_service in OPS_SERVICE_ALIASES:
            normalized["service"] = OPS_SERVICE_ALIASES[raw_service]
            return normalized
        if service_key in OPS_SERVICE_ALIASES:
            normalized["service"] = OPS_SERVICE_ALIASES[service_key]
            return normalized

        text = task.lower()
        if "前端" in task or "frontend" in text or "nginx" in text:
            normalized["service"] = "ragent-frontend"
        else:
            # 未识别服务名时回退到本项目后端服务，避免模型幻觉出 order-core 等外部名称。
            normalized["service"] = "ragent-api"
        return normalized

    def _deterministic_plan(self, task: str) -> list[PlanStep]:
        """模型不可用时的稳定排障计划。"""

        text = task.lower()
        steps = [
            PlanStep("检查 Compose 服务状态", "compose_ps", reasoning="先确认核心服务是否存在异常状态"),
        ]

        if any(key in text or key in task for key in ["日志", "log", "logs", "报错", "error", "exception", "502"]):
            steps.append(PlanStep("读取后端最近日志", "container_logs", {"service": "ragent-api", "tail": 120}, "补充运行上下文"))
            steps.append(PlanStep("分析后端错误日志", "log_analyzer", {"service": "ragent-api", "tail": 200}, "定位异常堆栈或错误模式"))

        if any(key in text or key in task for key in ["健康", "health", "状态", "status", "502", "前端", "frontend", "后端", "backend", "api"]):
            steps.append(PlanStep("检查后端健康接口", "api_health_check", reasoning="确认 API 服务是否可达"))
            steps.append(PlanStep("检查前端代理到后端", "nginx_proxy_check", reasoning="排查常见代理链路问题"))

        if any(key in text or key in task for key in ["端口", "port", "connection refused", "连接拒绝"]):
            steps.append(PlanStep("检查后端端口连通性", "port_check", {"host": "localhost", "port": 8000}, "确认 TCP 端口是否可连接"))

        if any(key in text or key in task for key in ["慢", "性能", "timeout", "超时", "cpu", "内存"]):
            steps.append(PlanStep("探测后端响应时间", "response_time_probe", {"url": "", "count": 5}, "确认是否存在慢请求"))
            steps.append(PlanStep("采集基础系统指标", "system_metrics", reasoning="补充资源占用信息"))
            steps.append(PlanStep("检查后端容器资源", "container_stats", {"service": "ragent-api"}, "补充容器资源快照"))

        if len(steps) == 1:
            steps.append(PlanStep("检查后端健康接口", "api_health_check", reasoning="确认 API 服务是否可达"))

        if any(key in text or key in task for key in ["重启", "restart", "恢复", "修复"]):
            service = "ragent-frontend" if ("前端" in task or "frontend" in text or "nginx" in text) else "ragent-api"
            steps.append(PlanStep(f"申请重启服务 {service}", "compose_restart_service", {"service": service}, "重启是写操作，必须进入审批"))
        return steps

    def _parse_json(self, content: str) -> dict[str, Any]:
        """从模型输出中解析 JSON。"""

        text = (content or "").strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        return json.loads(text)


class StepExecutorAgent:
    """单步执行 Agent，只通过统一工具注册表调用白名单工具。"""

    name = "executor"

    def __init__(self, registry: UnifiedToolRegistry) -> None:
        self.registry = registry

    async def execute(self, step: AgentStep) -> ToolCallResult:
        """执行一个计划步骤。"""

        if not step.tool_name:
            return ToolCallResult(success=True, summary=step.title)
        return await self.registry.call(ToolCallRequest(name=step.tool_name, args=step.args))


class ReplannerAgent:
    """重规划 Agent，根据每步观察结果决定下一步。"""

    name = "replanner"

    async def decide(
        self,
        task: str,
        completed: list[AgentStep],
        remaining: list[AgentStep],
        last_result: ToolCallResult,
    ) -> ReplanDecision:
        """生成重规划决策，模型失败时使用确定性策略。"""

        try:
            decision = await self._llm_decide(task, completed, remaining, last_result)
            if decision:
                return decision
        except Exception:
            pass
        return self._deterministic_decide(completed, remaining, last_result)

    async def _llm_decide(
        self,
        task: str,
        completed: list[AgentStep],
        remaining: list[AgentStep],
        last_result: ToolCallResult,
    ) -> ReplanDecision | None:
        """调用主模型判断是否完成或重规划。"""

        prompt = (
            "你是 Ragent 运维 Replanner，需要根据执行结果判断下一步。\n"
            "只能输出 JSON，格式：{\"action\":\"complete|continue|blocked|revise\",\"reason\":\"原因\",\"final_report\":\"可选总结\"}\n"
            "如果还有必要执行的剩余只读步骤，选择 continue；如果写操作等待审批，选择 blocked；如果已经足够回答，选择 complete。\n\n"
            f"用户问题：{task}\n"
            f"已完成步骤：{json.dumps([step.__dict__ for step in completed], ensure_ascii=False, default=str)[:3000]}\n"
            f"剩余步骤：{json.dumps([step.__dict__ for step in remaining], ensure_ascii=False, default=str)[:2000]}\n"
            f"最新结果：{json.dumps(last_result.to_dict(), ensure_ascii=False)[:2000]}"
        )
        llm = build_primary_llm(streaming=False)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        data = self._parse_json(getattr(response, "content", ""))
        action = str(data.get("action") or "")
        if action not in {"complete", "continue", "blocked", "revise"}:
            return None
        return ReplanDecision(action=action, reason=str(data.get("reason") or ""), final_report=str(data.get("final_report") or ""))

    def _deterministic_decide(
        self,
        completed: list[AgentStep],
        remaining: list[AgentStep],
        last_result: ToolCallResult,
    ) -> ReplanDecision:
        """模型不可用时的稳定重规划策略。"""

        if last_result.requires_approval:
            return ReplanDecision("blocked", "当前步骤需要审批，暂停自动执行。")
        if last_result.error == "approval_required":
            return ReplanDecision("blocked", "当前步骤需要审批，暂停自动执行。")
        if remaining:
            return ReplanDecision("continue", "继续执行剩余计划。")
        failures = [step for step in completed if step.status == StepStatus.FAILED]
        if failures:
            return ReplanDecision("complete", f"计划已执行完毕，其中 {len(failures)} 个步骤失败，请查看工具结果。")
        return ReplanDecision("complete", "计划已执行完毕。")

    def _parse_json(self, content: str) -> dict[str, Any]:
        """从模型输出中解析 JSON。"""

        text = (content or "").strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        return json.loads(text)


class OrchestratorAgent(BaseAgent):
    """运维 Agent 编排器，执行 Plan-Execute-Replan 循环。"""

    role = AgentRole.ORCHESTRATOR
    name = "orchestrator"
    description = "按计划、执行、重规划模式处理运维问题。"

    def __init__(self, toolkit: OpsToolkit | None = None) -> None:
        self.toolkit = toolkit or OpsToolkit()
        self.registry = UnifiedToolRegistry(include_ops=True, toolkit=self.toolkit)
        self.memory = SharedMemory()
        self.planner = PlannerAgent(self.registry)
        self.executor = StepExecutorAgent(self.registry)
        self.replanner = ReplannerAgent()
        super().__init__(self.toolkit.tools)

    def tool_specs(self) -> list[ToolSpec]:
        """对外暴露统一后的工具元数据。"""

        return [tool.spec for tool in self.registry.tools.values()]

    async def run(self, task: str, context: dict[str, Any] | None = None) -> AsyncIterator[dict[str, Any]]:
        """通过 LangGraph 状态图执行完整 Plan-Execute-Replan 流程。"""

        from app.agents.ops_graph import OpsLangGraphRunner

        runner = OpsLangGraphRunner(
            registry=self.registry,
            planner=self.planner,
            executor=self.executor,
            replanner=self.replanner,
            orchestrator=self,
            memory=self.memory,
            max_steps=10,
        )
        async for event in runner.run(task, context):
            yield event

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        """把真实执行耗时转换为 Trace 可展示的毫秒数。"""

        return max(1, int((time.perf_counter() - started) * 1000))

    def _should_call_replanner(self, result: ToolCallResult, remaining: list[AgentStep]) -> bool:
        """按需触发 LLM Replanner，避免成功只读步骤后反复调用模型。"""

        if result.requires_approval or result.error == "approval_required":
            return True
        if not result.success:
            return True
        if not remaining:
            return True
        return False

    def _build_report(self, task: str, steps: list[AgentStep], decision: ReplanDecision) -> str:
        """生成面向用户的最终运维报告。"""

        lines = ["## 运维 Agent 诊断报告", f"问题：{task}", "", "### 执行结果"]
        for index, step in enumerate(steps, start=1):
            status = step.status.value if isinstance(step.status, StepStatus) else str(step.status)
            lines.append(f"- {index}. {step.title}：{status}。{step.observation}")
        lines.extend(["", "### 重规划结论", decision.final_report or decision.reason])
        return "\n".join(lines)
