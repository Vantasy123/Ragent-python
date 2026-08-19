"""统一工具注册表，适配 MCP 工具与求职专用 Agent 工具。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.agents.base import ToolSpec
from app.agents.tools.job_toolkit import JobToolkit
from app.infrastructure.mcp.tool_registry import ToolRegistry


ToolHandler = Callable[..., Any | Awaitable[Any]]
ApprovalPolicy = Callable[[dict[str, Any]], tuple[str, bool]]
MAX_SUMMARY_CHARS = 1000
MAX_DATA_STRING_CHARS = 2000
MAX_LIST_ITEMS = 50


def _compact_value(value: Any, *, max_string_chars: int = MAX_DATA_STRING_CHARS) -> Any:
    """压缩工具输出中的大字段，避免日志或 inspect 结果撑爆 SSE、Trace 和数据库。"""

    if isinstance(value, str):
        if len(value) <= max_string_chars:
            return value
        return {
            "preview": value[:max_string_chars],
            "truncated": True,
            "originalLength": len(value),
        }
    if isinstance(value, list):
        compacted = [_compact_value(item, max_string_chars=max_string_chars) for item in value[:MAX_LIST_ITEMS]]
        if len(value) > MAX_LIST_ITEMS:
            compacted.append({"truncated": True, "originalLength": len(value)})
        return compacted
    if isinstance(value, dict):
        return {str(key): _compact_value(item, max_string_chars=max_string_chars) for key, item in value.items()}
    return value


def compact_tool_result_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """返回可对外展示和持久化的工具结果摘要。"""

    compacted = dict(payload)
    summary = str(compacted.get("summary") or "")
    if len(summary) > MAX_SUMMARY_CHARS:
        compacted["summary"] = summary[:MAX_SUMMARY_CHARS]
        compacted["summaryTruncated"] = True
        compacted["summaryOriginalLength"] = len(summary)
    data = compacted.get("data")
    compacted["data"] = _compact_value(data if isinstance(data, dict) else {"value": data})
    return compacted


@dataclass
class ToolCallRequest:
    """Agent 内部统一工具调用请求。"""

    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallResult:
    """Agent 内部统一工具调用结果。"""

    success: bool
    summary: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    risk_level: str = "read"
    requires_approval: bool = False
    source: str = "builtin"
    category: str = "general"

    def to_dict(self) -> dict[str, Any]:
        """转换成 SSE 和数据库可直接保存的结构。"""

        return compact_tool_result_dict({
            "success": self.success,
            "summary": self.summary,
            "data": self.data,
            "error": self.error,
            "riskLevel": self.risk_level,
            "requiresApproval": self.requires_approval,
            "source": self.source,
            "category": self.category,
        })


@dataclass
class UnifiedTool:
    """统一工具定义，屏蔽内置工具和 MCP 工具的调用差异。"""

    spec: ToolSpec
    handler: ToolHandler
    approval_policy: ApprovalPolicy | None = None

    def policy_for(self, args: dict[str, Any] | None = None) -> tuple[str, bool]:
        """按工具参数计算实际风险等级和审批要求。"""

        if self.approval_policy is None:
            return self.spec.risk_level, self.spec.requires_approval
        return self.approval_policy(args or {})

    async def call(self, **kwargs: Any) -> ToolCallResult:
        """统一调用封装，自动补齐错误兜底与结构化返回。"""

        try:
            res = self.handler(**kwargs)
            if hasattr(res, "__await__"):
                result = await res
            else:
                result = res
        except Exception as exc:
            return ToolCallResult(
                success=False,
                summary=f"工具执行异常：{self.spec.name}",
                error=str(exc),
                risk_level=self.spec.risk_level,
                requires_approval=self.spec.requires_approval,
                source=self.spec.source,
                category=self.spec.category,
            )

        if isinstance(result, ToolCallResult):
            return result

        payload = result if isinstance(result, dict) else {"data": result}
        success = bool(payload.get("success", False))
        data = payload.get("data")
        if not isinstance(data, dict):
            data = {"value": data}
        summary = payload.get("summary") or payload.get("error") or ("工具执行成功" if success else "工具执行失败")
        return ToolCallResult(
            success=success,
            summary=str(summary),
            data=data,
            error=str(payload.get("error") or ""),
            risk_level=str(payload.get("riskLevel") or self.spec.risk_level),
            requires_approval=bool(payload.get("requiresApproval", self.spec.requires_approval)),
            source=self.spec.source,
            category=self.spec.category,
        )

    def to_public_dict(self) -> dict[str, Any]:
        """返回前端工具目录需要的公开字段。"""

        is_read_only = self.spec.risk_level == "read" and not self.spec.requires_approval
        return {
            "name": self.spec.name,
            "description": self.spec.description,
            "args_schema": self.spec.args_schema,
            "argsSchema": self.spec.args_schema,
            "risk_level": self.spec.risk_level,
            "riskLevel": self.spec.risk_level,
            "requires_approval": self.spec.requires_approval,
            "requiresApproval": self.spec.requires_approval,
            "is_read_only": is_read_only,
            "isReadOnly": is_read_only,
            "source": self.spec.source,
            "category": self.spec.category,
            "enabledFor": self.spec.enabled_for,
        }


class UnifiedToolRegistry:
    """统一内置工具、MCP 工具与求职 Agent 工具的注册表。"""

    def __init__(self, include_ops: bool = False, toolkit: Any = None) -> None:
        self.include_ops = include_ops
        self.mcp_registry = ToolRegistry()
        self._tools: dict[str, UnifiedTool] = {}
        self._register_mcp_tools()
        self._register_job_tools()

    @property
    def tools(self) -> dict[str, UnifiedTool]:
        """返回按名称索引的统一工具。"""
        return self._tools

    def list_tools(self, audience: str = "user") -> list[dict[str, Any]]:
        """按用户类型返回可见工具。"""
        return [
            tool.to_public_dict()
            for tool in self._tools.values()
            if audience in tool.spec.enabled_for or "all" in tool.spec.enabled_for
        ]

    async def call(self, request: ToolCallRequest, *, skip_approval: bool = False, actor_role: str = "admin") -> ToolCallResult:
        """执行统一工具调用，未知工具返回结构化失败。"""
        tool = self._tools.get(request.name)
        if tool is None:
            return ToolCallResult(success=False, summary=f"工具不存在：{request.name}", error="unknown_tool")
        access = self._tool_access_decision(tool, actor_role)
        risk_level, requires_approval = tool.policy_for(request.args)
        if not access["allowed"]:
            return ToolCallResult(
                success=False,
                summary=f"当前角色无权调用工具：{request.name}",
                data={"toolAccess": access},
                error="tool_permission_denied",
                risk_level=risk_level,
                requires_approval=requires_approval,
                source=tool.spec.source,
                category=tool.spec.category,
            )
        if requires_approval and not skip_approval:
            return ToolCallResult(
                success=False,
                summary=f"工具需要审批：{request.name}",
                data={"toolAccess": access},
                error="approval_required",
                risk_level=risk_level,
                requires_approval=True,
                source=tool.spec.source,
                category=tool.spec.category,
            )
        result = await tool.call(**request.args)
        result.data = {**(result.data or {}), "toolAccess": access}
        return result

    def _tool_access_decision(self, tool: UnifiedTool, actor_role: str) -> dict[str, Any]:
        """按 ToolSpec.enabled_for 生成最小权限授权快照。"""
        role = str(actor_role or "anonymous").lower()
        enabled_for = [str(item).lower() for item in (tool.spec.enabled_for or [])]
        allowed = "all" in enabled_for or role in enabled_for
        return {
            "allowed": allowed,
            "actorRole": role,
            "enabledFor": enabled_for,
            "toolName": tool.spec.name,
            "source": tool.spec.source,
            "category": tool.spec.category,
            "reasonCode": "role_allowed" if allowed else "role_not_allowed",
            "leastPrivilege": "enforced",
        }

    def _register_mcp_tools(self) -> None:
        """把内置 MCP 工具注册为普通对话可用的安全工具。"""
        for item in self.mcp_registry.tools.values():
            spec = ToolSpec(
                name=item.name,
                description=item.description,
                args_schema=self._mcp_args_schema(item.name),
                risk_level="read",
                requires_approval=False,
                source="mcp",
                category="general",
                enabled_for=["user", "admin"],
            )
            self._tools[item.name] = UnifiedTool(spec=spec, handler=item.handler)

    def _register_job_tools(self) -> None:
        """注册智能求职 Agent 专属工具套件。"""
        job_tools = [
            (
                ToolSpec(
                    name="job_parse_resume",
                    description="将候选人简历原始文本解析为多维结构化数据（基本信息、教育、工作、项目、技能）并进行质量诊断。",
                    args_schema={"raw_text": "string"},
                    risk_level="read",
                    requires_approval=False,
                    source="job_agent",
                    category="job",
                    enabled_for=["user", "admin"],
                ),
                lambda **kwargs: JobToolkit.parse_resume(kwargs.get("raw_text", ""))
            ),
            (
                ToolSpec(
                    name="job_optimize_project_star",
                    description="使用 STAR 法则对项目经历进行深度润色重构（情境S、任务T、行动A、结果R量化）。",
                    args_schema={"project_name": "string", "tech_stack": "array", "background": "string", "target_jd": "string"},
                    risk_level="read",
                    requires_approval=False,
                    source="job_agent",
                    category="job",
                    enabled_for=["user", "admin"],
                ),
                lambda **kwargs: JobToolkit.optimize_project_star(
                    project_name=kwargs.get("project_name", ""),
                    tech_stack=kwargs.get("tech_stack", []),
                    background=kwargs.get("background", ""),
                    target_jd=kwargs.get("target_jd", "")
                )
            ),
            (
                ToolSpec(
                    name="job_search_postings",
                    description="检索牛客、BOSS直聘等多渠道岗位库中的职位机会。",
                    args_schema={"keyword": "string", "city": "string", "job_type": "string", "limit": "integer"},
                    risk_level="read",
                    requires_approval=False,
                    source="job_agent",
                    category="job",
                    enabled_for=["user", "admin"],
                ),
                lambda **kwargs: JobToolkit.search_jobs(
                    keyword=kwargs.get("keyword", ""),
                    city=kwargs.get("city", "全国"),
                    job_type=kwargs.get("job_type", "all"),
                    limit=kwargs.get("limit", 10)
                )
            ),
            (
                ToolSpec(
                    name="job_match_analysis",
                    description="执行候选人简历与目标岗位 JD 的深度全维度匹配打分、优劣势分析与定制化建议。",
                    args_schema={"resume_text": "string", "jd_text": "string", "target_title": "string"},
                    risk_level="read",
                    requires_approval=False,
                    source="job_agent",
                    category="job",
                    enabled_for=["user", "admin"],
                ),
                lambda **kwargs: JobToolkit.match_resume_with_job(
                    resume_text=kwargs.get("resume_text", ""),
                    jd_text=kwargs.get("jd_text", ""),
                    target_title=kwargs.get("target_title", "开发工程师")
                )
            ),
            (
                ToolSpec(
                    name="job_generate_interview_questions",
                    description="针对目标岗位 JD 和简历生成高频大厂模拟面试题集（含技术八股、项目深挖、系统设计、BQ）。",
                    args_schema={"target_role": "string", "jd_text": "string", "resume_text": "string", "count": "integer"},
                    risk_level="read",
                    requires_approval=False,
                    source="job_agent",
                    category="job",
                    enabled_for=["user", "admin"],
                ),
                lambda **kwargs: JobToolkit.generate_interview_questions(
                    target_role=kwargs.get("target_role", "后端开发工程师"),
                    jd_text=kwargs.get("jd_text", ""),
                    resume_text=kwargs.get("resume_text", ""),
                    count=kwargs.get("count", 3)
                )
            ),
            (
                ToolSpec(
                    name="job_generate_greeting",
                    description="一键生成针对目标企业与 HR 的高情商、高回复率打招呼破冰文案与定制求职信。",
                    args_schema={"candidate_name": "string", "target_role": "string", "company": "string", "core_skills": "array"},
                    risk_level="read",
                    requires_approval=False,
                    source="job_agent",
                    category="job",
                    enabled_for=["user", "admin"],
                ),
                lambda **kwargs: JobToolkit.generate_greeting_and_cover_letter(
                    candidate_name=kwargs.get("candidate_name", "求职者"),
                    target_role=kwargs.get("target_role", "后端工程师"),
                    company=kwargs.get("company", "目标公司"),
                    core_skills=kwargs.get("core_skills", [])
                )
            ),
            (
                ToolSpec(
                    name="job_sync_platforms",
                    description="从 BOSS直聘、猎聘、前程无忧 51job、牛客网实时采集和增量同步最新招聘岗位入库。",
                    args_schema={"platform": "string", "keyword": "string", "city": "string", "limit": "integer"},
                    risk_level="read",
                    requires_approval=False,
                    source="job_agent",
                    category="job",
                    enabled_for=["user", "admin"],
                ),
                lambda **kwargs: JobToolkit.sync_jobs_from_platforms(
                    platform=kwargs.get("platform", "all"),
                    keyword=kwargs.get("keyword", "后端开发"),
                    city=kwargs.get("city", "全国"),
                    limit=kwargs.get("limit", 5)
                )
            ),
        ]

        for spec, handler in job_tools:
            self._tools[spec.name] = UnifiedTool(spec=spec, handler=handler)

    def _mcp_args_schema(self, name: str) -> dict[str, Any]:
        """为当前内置 MCP 工具补充轻量参数描述。"""
        if name == "search_knowledge_base":
            return {"query": "string", "top_k": "integer"}
        if name == "get_weather":
            return {"location": "string"}
        return {}
