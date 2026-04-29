"""对话 Agent，实现 ReAct 工具调用循环和最终回答生成。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from langchain_core.messages import HumanMessage

from app.agents.tool_registry import ToolCallRequest, UnifiedToolRegistry
from app.rag.workflow import build_primary_llm


@dataclass
class ReactState:
    """对话 ReAct 循环状态。"""

    question: str
    history: list[dict[str, str]] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    final_answer: str = ""


class ConversationReactAgent:
    """普通对话 Agent，按思考、工具、观察、回答的 ReAct 流程运行。"""

    def __init__(self, registry: UnifiedToolRegistry | None = None, max_steps: int = 5) -> None:
        self.registry = registry or UnifiedToolRegistry(include_ops=False)
        self.max_steps = max(1, max_steps)

    async def run(self, question: str, history: list[dict[str, str]] | None = None) -> AsyncIterator[dict[str, Any]]:
        """运行 ReAct 循环；模型失败或无法产出合法动作时由调用方执行 RAG 回退。"""

        state = ReactState(question=question, history=history or [])
        for step_index in range(self.max_steps):
            decision = await self._decide(state, step_index)
            if not decision:
                yield {
                    "type": "react_step",
                    "stepIndex": step_index,
                    "status": "fallback",
                    "reason": "模型未返回可解析动作，准备回退到 RAG 链路",
                }
                return

            thought = str(decision.get("thought") or "")
            action = str(decision.get("action") or "final_answer")
            yield {"type": "react_step", "stepIndex": step_index, "thought": thought, "action": action}

            if action == "final_answer":
                answer = str(decision.get("final_answer") or decision.get("answer") or "")
                if not answer:
                    return
                state.final_answer = answer
                yield {"type": "final_answer", "content": answer}
                return

            if action != "tool_call":
                yield {
                    "type": "react_step",
                    "stepIndex": step_index,
                    "status": "fallback",
                    "reason": f"未知动作：{action}",
                }
                return

            tool_name = str(decision.get("tool") or "")
            tool_args = decision.get("args") if isinstance(decision.get("args"), dict) else {}
            yield {"type": "tool_call", "agent": "conversation", "stepIndex": step_index, "tool": tool_name, "args": tool_args}
            result = await self.registry.call(ToolCallRequest(name=tool_name, args=tool_args))
            result_data = result.to_dict()
            state.observations.append({"tool": tool_name, "args": tool_args, "result": result_data})
            yield {
                "type": "observation",
                "agent": "conversation",
                "stepIndex": step_index,
                "tool": tool_name,
                "args": tool_args,
                "result": result_data,
            }

        yield {
            "type": "react_step",
            "stepIndex": self.max_steps,
            "status": "fallback",
            "reason": "达到最大 ReAct 轮数，准备回退到 RAG 链路",
        }

    async def _decide(self, state: ReactState, step_index: int) -> dict[str, Any] | None:
        """调用主模型生成下一步动作，失败时返回 None 触发回退。"""

        prompt = self._build_prompt(state, step_index)
        try:
            llm = build_primary_llm(streaming=False)
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            return self._parse_json(getattr(response, "content", ""))
        except Exception:
            return None

    def _build_prompt(self, state: ReactState, step_index: int) -> str:
        """构造只允许 JSON 输出的 ReAct 决策提示词。"""

        tools = self.registry.list_tools(audience="user")
        observations = json.dumps(state.observations, ensure_ascii=False)[:5000]
        history = json.dumps(state.history[-6:], ensure_ascii=False)[:3000]
        return (
            "你是 Ragent 的对话 Agent，需要按 ReAct 流程解决用户问题。\n"
            "只能输出 JSON，不要输出 Markdown。\n"
            "JSON 格式二选一：\n"
            "{\"thought\":\"思考\", \"action\":\"tool_call\", \"tool\":\"工具名\", \"args\":{}}\n"
            "{\"thought\":\"思考\", \"action\":\"final_answer\", \"final_answer\":\"最终回答\"}\n"
            "规则：如果需要知识库、时间或天气信息，优先调用工具；如果已有足够信息，直接 final_answer。\n\n"
            f"当前轮次：{step_index + 1}/{self.max_steps}\n"
            f"可用工具：{json.dumps(tools, ensure_ascii=False)}\n"
            f"历史消息：{history}\n"
            f"已有观察：{observations}\n"
            f"用户问题：{state.question}"
        )

    def _parse_json(self, content: str) -> dict[str, Any] | None:
        """从模型输出中提取 JSON 对象。"""

        text = (content or "").strip()
        if not text:
            return None
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None
