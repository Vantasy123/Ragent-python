"""求职 Agent 意图到工具的契约测试。"""

from __future__ import annotations

import asyncio

from app.agents.job_intent_router import route_job_intent
from app.agents.react_agent import ConversationReactAgent
from app.agents.tool_registry import UnifiedToolRegistry


def test_job_intent_routes_local_live_and_sync_searches():
    assert route_job_intent("帮我找北京 Java 后端岗位").tool == "job_search_postings"
    assert route_job_intent("查一下最新的北京 Java 岗位").tool == "job_live_search_postings"
    assert route_job_intent("从 BOSS 直聘同步北京 Java 岗位").tool == "job_sync_platforms"
    assert route_job_intent("搜索本地岗位库，不要访问外部平台").tool == "job_search_postings"


def test_job_intent_routes_resume_and_interview_tasks():
    assert route_job_intent("解析我的简历").tool == "job_parse_resume"
    assert route_job_intent("针对这个岗位生成面试题").tool == "job_generate_interview_questions"
    assert route_job_intent("帮我写一段给 HR 的打招呼话术").tool == "job_generate_greeting"
    assert route_job_intent("分析这份简历和这个 JD 是否匹配").tool == "job_match_analysis"


def test_react_agent_emits_deterministic_job_route_without_llm(monkeypatch):
    calls = []

    async def fake_call(self, request, *, skip_approval=False, actor_role="admin"):
        calls.append(request.name)
        class Result:
            success = True
            def to_dict(self):
                return {"success": True, "summary": "fixture", "data": {"jobs": []}}
        return Result()

    monkeypatch.setattr(UnifiedToolRegistry, "call", fake_call)
    agent = ConversationReactAgent(registry=UnifiedToolRegistry(), max_steps=1)
    events = asyncio.run(_collect(agent.run("查一下最新的北京 Java 岗位")))

    assert calls == ["job_live_search_postings"]
    tool_events = [event for event in events if event["type"] == "tool_call"]
    assert tool_events[0]["tool"] == "job_live_search_postings"
    assert tool_events[0]["intent"] == "live_job_search"
    assert tool_events[0]["routing_confidence"] >= 0.9


async def _collect(iterator):
    return [event async for event in iterator]
