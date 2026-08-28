"""求职 Agent 的确定性意图路由规则。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class JobRouteDecision:
    """岗位意图路由结果，供 Agent 和契约测试共同使用。"""

    intent: str
    tool: str | None
    args: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    reason: str = ""
    requires_clarification: bool = False


def _extract_search_args(text: str) -> dict[str, Any]:
    """从确定性路由文本中提取通用搜索参数，未识别字段保留默认值。"""
    args: dict[str, Any] = {}
    cities = ("北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "西安")
    city = next((item for item in cities if item in text), None)
    if city:
        args["city"] = city
    platform_aliases = {
        "boss直聘": "boss", "boss": "boss", "猎聘": "liepin",
        "前程无忧": "51job", "51job": "51job", "牛客": "nowcoder",
    }
    platform = next((value for marker, value in platform_aliases.items() if marker in text), None)
    if platform:
        args["platform"] = platform
    return args


def route_job_intent(question: str) -> JobRouteDecision | None:
    """将明确的求职意图路由到唯一工具；无法确定时返回 None。"""
    text = str(question or "").strip()
    if not text:
        return None

    sync_markers = ("同步", "采集并保存", "抓取入库", "入库", "采集岗位")
    live_markers = ("最新", "实时", "平台", "boss直聘", "boss", "猎聘", "前程无忧", "51job", "牛客")
    local_only_markers = ("不要访问外部", "不访问外部", "只要本地", "仅本地")
    local_markers = ("岗位库", "本地", "已同步", "缓存")

    if any(marker in text for marker in ("并同步", "并入库", "同步到库", "采集并保存")):
        return JobRouteDecision(
            intent="job_sync",
            tool="job_sync_platforms",
            args=_extract_search_args(text),
            confidence=0.99,
            reason="用户明确要求采集并产生入库副作用",
        )
    if any(marker in text for marker in sync_markers):
        return JobRouteDecision(
            intent="job_sync",
            tool="job_sync_platforms",
            args=_extract_search_args(text),
            confidence=0.98,
            reason="用户明确要求同步或采集入库",
        )
    if any(marker in text for marker in ("匹配", "适合度", "对比") ) and any(marker in text for marker in ("简历", "JD", "岗位")):
        return JobRouteDecision(
            intent="job_match",
            tool="job_match_analysis",
            confidence=0.97,
            reason="用户要求比较简历与岗位要求",
        )
    if any(marker in text for marker in ("解析简历", "简历解析", "提取简历", "读取简历", "解析我的简历")):
        return JobRouteDecision(
            intent="resume_parse",
            tool="job_parse_resume",
            confidence=0.99,
            reason="用户要求提取简历结构化信息",
        )
    if any(marker in text for marker in ("面试题", "模拟面试", "面试问题")):
        return JobRouteDecision(
            intent="interview_questions",
            tool="job_generate_interview_questions",
            confidence=0.98,
            reason="用户要求生成岗位面试问题",
        )
    if any(marker in text for marker in ("打招呼", "求职信", "联系 HR", "联系hr", "给hr")):
        return JobRouteDecision(
            intent="greeting",
            tool="job_generate_greeting",
            confidence=0.98,
            reason="用户要求生成 HR 沟通文案",
        )
    if any(marker in text for marker in local_only_markers) or (any(marker in text for marker in local_markers) and not any(marker in text for marker in live_markers)):
        return JobRouteDecision(
            intent="local_job_search",
            tool="job_search_postings",
            args=_extract_search_args(text),
            confidence=0.97,
            reason="用户限定搜索本地或已同步岗位库",
        )
    if any(marker in text for marker in live_markers):
        return JobRouteDecision(
            intent="live_job_search",
            tool="job_live_search_postings",
            args=_extract_search_args(text),
            confidence=0.96,
            reason="用户要求最新或招聘平台实时岗位",
        )
    if any(marker in text for marker in ("找工作", "找岗位", "职位", "岗位", "招聘")):
        return JobRouteDecision(
            intent="local_job_search",
            tool="job_search_postings",
            args=_extract_search_args(text),
            confidence=0.75,
            reason="一般岗位搜索默认查询本地岗位库，避免未经要求访问外部平台",
        )
    return None
