"""Trace 服务，负责链路运行和节点 span 的持久化。"""

from __future__ import annotations

import re

import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.text_sanitizer import redact_sensitive_payload
from app.domain.models import TraceRun, TraceSpan


@dataclass
class TraceSpanHandle:
    """Trace span 的临时句柄，完成时再写入数据库。"""

    trace_id: str
    operation: str
    started_at: float = field(default_factory=time.time)
    input_data: dict[str, Any] = field(default_factory=dict)
    context_data: dict[str, Any] = field(default_factory=dict)


class CostEstimator:
    """估算大模型和 Embedding 的 Token 消费成本（人民币/元）。"""

    PRICES = {
        # 阿里云千问 / 通义系列 (元 / 1k tokens)
        "qwen-plus": {"input": 0.004 / 1000, "output": 0.012 / 1000},
        "qwen-turbo": {"input": 0.002 / 1000, "output": 0.006 / 1000},
        "qwen-max": {"input": 0.02 / 1000, "output": 0.06 / 1000},
        "qwen/qwen2.5-72b-instruct": {"input": 0.004 / 1000, "output": 0.012 / 1000},
        "qwen/qwen2.5-32b-instruct": {"input": 0.0025 / 1000, "output": 0.005 / 1000},
        "qwen/qwen2.5-14b-instruct": {"input": 0.002 / 1000, "output": 0.004 / 1000},
        "qwen/qwen2.5-7b-instruct": {"input": 0.001 / 1000, "output": 0.002 / 1000},
        "qwen/qwen3-32b": {"input": 0.003 / 1000, "output": 0.006 / 1000},
        "qwen/qwen3-8b": {"input": 0.0015 / 1000, "output": 0.003 / 1000},
        # DeepSeek 系列
        "deepseek-ai/deepseek-r1": {"input": 0.004 / 1000, "output": 0.016 / 1000},
        "deepseek-ai/deepseek-v3": {"input": 0.002 / 1000, "output": 0.008 / 1000},
        "deepseek-ai/deepseek-v3.2": {"input": 0.002 / 1000, "output": 0.008 / 1000},
        "deepseek-ai/deepseek-r1-0528-qwen3-8b": {"input": 0.002 / 1000, "output": 0.004 / 1000},
        # 智谱与 Kimi 系列
        "zai-org/glm-5.2": {"input": 0.003 / 1000, "output": 0.008 / 1000},
        "zai-org/glm-4.5-air": {"input": 0.001 / 1000, "output": 0.002 / 1000},
        "thudm/glm-4-32b-0414": {"input": 0.002 / 1000, "output": 0.005 / 1000},
        "moonshotai/kimi-k2.7-code": {"input": 0.003 / 1000, "output": 0.008 / 1000},
        "pro/moonshotai/kimi-k2.6": {"input": 0.003 / 1000, "output": 0.008 / 1000},
        # 向量嵌入与多模态
        "baai/bge-m3": {"input": 0.0005 / 1000, "output": 0.0},
        "text-embedding-v3": {"input": 0.0007 / 1000, "output": 0.0},
        # OpenAI 模型
        "gpt-4o": {"input": 0.035 / 1000, "output": 0.105 / 1000},
        "gpt-4o-mini": {"input": 0.001 / 1000, "output": 0.004 / 1000},
        "gpt-4": {"input": 0.21 / 1000, "output": 0.42 / 1000},
        "gpt-3.5-turbo": {"input": 0.0035 / 1000, "output": 0.0105 / 1000},
    }

    @classmethod
    def estimate_cost(cls, model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
        model_name = str(model_name or "").strip().lower()
        price = cls.PRICES.get(model_name)
        if not price:
            # 模糊匹配
            if "embedding" in model_name or "bge" in model_name:
                price = {"input": 0.0005 / 1000, "output": 0.0}
            elif "deepseek-r1" in model_name or "r1" in model_name:
                price = {"input": 0.004 / 1000, "output": 0.016 / 1000}
            elif "deepseek" in model_name or "v3" in model_name:
                price = {"input": 0.002 / 1000, "output": 0.008 / 1000}
            elif "72b" in model_name or "max" in model_name:
                price = {"input": 0.004 / 1000, "output": 0.012 / 1000}
            elif "32b" in model_name or "plus" in model_name:
                price = {"input": 0.0025 / 1000, "output": 0.005 / 1000}
            elif "14b" in model_name:
                price = {"input": 0.002 / 1000, "output": 0.004 / 1000}
            elif "7b" in model_name or "8b" in model_name or "turbo" in model_name:
                price = {"input": 0.001 / 1000, "output": 0.002 / 1000}
            elif "glm" in model_name or "kimi" in model_name:
                price = {"input": 0.003 / 1000, "output": 0.008 / 1000}
            else:
                # 默认降级为 14B / qwen-plus 定价
                price = {"input": 0.002 / 1000, "output": 0.004 / 1000}

        cost = (prompt_tokens * price["input"]) + (completion_tokens * price["output"])
        return round(cost, 6)


class TraceService:
    """数据库持久化 Trace 服务。"""

    def __init__(self, db: Session):
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
        self.db = db

    def start_run(self, session_id: str | None = None, user_id: str | None = None, task_id: str | None = None) -> TraceRun:
        """start_run 函数：启动一次运行流程，并创建后续追踪或状态更新需要的初始记录。"""
        run = TraceRun(session_id=session_id, user_id=user_id, task_id=task_id, status="running")
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def create_span(
        self,
        trace_id: str,
        operation: str,
        input_data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        **legacy_input: Any,
    ) -> TraceSpanHandle:
        """创建 span 句柄。

        - `input_data`：显式输入摘要
        - `metadata`：节点上下文，不参与输入输出混用
        - `legacy_input`：兼容旧调用，默认视为输入摘要
        """

        return TraceSpanHandle(
            trace_id=trace_id,
            operation=operation,
            input_data=input_data or legacy_input,
            context_data=metadata or {},
        )

    def _parse_tokens(self, handle: TraceSpanHandle, output_data: dict | None) -> tuple[int, int, str]:
        """尝试从 span 数据中提取模型名和 Token 用量信息。"""
        # 1. 提取模型名称
        model_name = ""
        for source in [handle.context_data, handle.input_data, output_data]:
            if not source:
                continue
            if "model" in source:
                model_name = source["model"]
                break
            if "model_name" in source:
                model_name = source["model_name"]
                break

        if not model_name:
            # 根据操作名称降级推测默认模型
            if handle.operation == "embedding":
                from app.core.config import settings
                model_name = getattr(settings, "EMBEDDING_MODEL", "text-embedding-v3")
            elif handle.operation in ("llm", "generation", "chat", "query_rewrite", "intent_analysis"):
                from app.core.config import settings
                model_name = getattr(settings, "CHAT_MODEL", "qwen-plus")

        # 2. 提取 Token 用量
        prompt_tokens = 0
        completion_tokens = 0

        # 从 usage 结构中解析
        for source in [output_data, handle.input_data, handle.context_data]:
            if not source:
                continue
            usage = source.get("usage") or source.get("usage_metadata") or source.get("token_usage")
            if isinstance(usage, dict):
                prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
                completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
                break

            # 直系字段提取
            p = source.get("prompt_tokens") or source.get("input_tokens")
            c = source.get("completion_tokens") or source.get("output_tokens")
            if p is not None or c is not None:
                prompt_tokens = p or 0
                completion_tokens = c or 0
                break

        # 如果没有获取到 usage，使用字符数降级估算，确保计费覆盖率。
        if prompt_tokens == 0 and completion_tokens == 0:
            input_text = ""
            if "query" in handle.input_data:
                input_text = str(handle.input_data["query"])
            elif "question" in handle.input_data:
                input_text = str(handle.input_data["question"])

            output_text = ""
            if output_data:
                if "answerPreview" in output_data:
                    output_text = str(output_data["answerPreview"])
                elif "content" in output_data:
                    output_text = str(output_data["content"])
                elif "text" in output_data:
                    output_text = str(output_data["text"])

            if input_text or output_text:
                def _estimate_chars(text: str) -> int:
                    if not text:
                        return 0
                    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
                    other_chars = len(text) - chinese_chars
                    # 简易中文 0.85/字符，英文 0.35/字符
                    return int(chinese_chars * 0.85 + other_chars * 0.35)

                prompt_tokens = _estimate_chars(input_text)
                completion_tokens = _estimate_chars(output_text)

        return int(prompt_tokens), int(completion_tokens), str(model_name)

    def complete_span(
        self,
        handle: TraceSpanHandle,
        status: str = "success",
        error_message: str = "",
        output_data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        **legacy_output: Any,
    ) -> None:
        """完成 span 并写入结构化输入输出。"""

        resolved_output = dict(output_data or {})
        if metadata:
            resolved_output.update(metadata)
        if legacy_output:
            resolved_output.update(legacy_output)

        span_metadata = {
            "input": redact_sensitive_payload(handle.input_data),
            "output": redact_sensitive_payload(resolved_output),
            "context": redact_sensitive_payload(handle.context_data),
        }

        resolved_duration_ms = duration_ms if duration_ms is not None else int((time.time() - handle.started_at) * 1000)
        resolved_duration_ms = max(1, int(resolved_duration_ms))

        # 动态解析 Token 用量与消费成本
        prompt_tokens, completion_tokens, model_name = self._parse_tokens(handle, resolved_output)
        total_tokens = prompt_tokens + completion_tokens
        cost = CostEstimator.estimate_cost(model_name, prompt_tokens, completion_tokens) if total_tokens > 0 else 0.0

        span = TraceSpan(
            trace_id=handle.trace_id,
            operation=handle.operation,
            status=status,
            duration_ms=resolved_duration_ms,
            metadata_json=span_metadata,
            error_message=error_message,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=cost,
        )
        self.db.add(span)
        self.db.commit()

    def complete_run(self, trace_id: str, status: str = "success") -> None:
        """complete_run 函数：完成一次运行流程，把最终状态、耗时和输出结果写回。"""
        run = self.db.query(TraceRun).filter(TraceRun.id == trace_id).first()
        if not run:
            return

        spans = self.db.query(TraceSpan).filter(TraceSpan.trace_id == trace_id).all()

        run.total_duration_ms = sum(span.duration_ms or 0 for span in spans)
        run.status = status

        # 聚合节点 tokens 和成本费用
        run.prompt_tokens = sum(span.prompt_tokens or 0 for span in spans)
        run.completion_tokens = sum(span.completion_tokens or 0 for span in spans)
        run.total_tokens = sum(span.total_tokens or 0 for span in spans)
        run.cost = sum(span.cost or 0.0 for span in spans)

        self.db.commit()
