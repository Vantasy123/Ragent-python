"""OpenAI Evals 外部评估适配服务。"""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.models import EvaluationBatchRun, EvaluationCaseResult


class OpenAIEvalsService:
    """把本地评估批次同步到 OpenAI Evals，形成可追踪的外部评估报告。"""

    def __init__(self, db: Session):
        """保存数据库会话，后续用于读取批次和回写远程运行状态。"""

        self.db = db

    def preview_batch_payload(self, batch_id: str) -> dict[str, Any]:
        """生成 OpenAI Evals 请求预览，不触发外部网络调用。"""

        batch = self._batch(batch_id)
        return {
            "enabled": self._enabled(),
            "evalPayload": self._eval_payload(batch),
            "runPayload": self._run_payload(batch),
            "itemCount": len(self._completed_results(batch)),
            "remote": {
                "apiBase": settings.OPENAI_EVALS_API_BASE,
                "graderModel": settings.OPENAI_EVALS_GRADER_MODEL,
            },
            "openaiEval": self._batch_remote_state(batch),
        }

    def start_batch_eval(self, batch_id: str) -> dict[str, Any]:
        """创建 OpenAI Eval 和 Eval Run，并把远程标识写回本地批次。"""

        self._ensure_remote_enabled()
        batch = self._batch(batch_id)
        eval_payload = self._eval_payload(batch)
        run_payload = self._run_payload(batch)
        eval_response = self._request_json("POST", "/evals", eval_payload)
        eval_id = str(eval_response.get("id") or "")
        if not eval_id:
            raise ValueError("OpenAI Evals 未返回 eval id")
        run_response = self._request_json("POST", f"/evals/{eval_id}/runs", run_payload)
        run_id = str(run_response.get("id") or "")
        if not run_id:
            raise ValueError("OpenAI Evals 未返回 run id")

        batch.openai_eval_id = eval_id
        batch.openai_eval_run_id = run_id
        batch.openai_eval_status = str(run_response.get("status") or "queued")
        batch.openai_eval_report = self._remote_report(run_response)
        self.db.commit()
        self.db.refresh(batch)
        return self._batch_remote_state(batch)

    def sync_batch_eval(self, batch_id: str) -> dict[str, Any]:
        """拉取 OpenAI Eval Run 最新状态，并同步到本地批次。"""

        self._ensure_remote_enabled()
        batch = self._batch(batch_id)
        if not batch.openai_eval_id or not batch.openai_eval_run_id:
            raise ValueError("该批次尚未启动 OpenAI Evals")
        run_response = self._request_json("GET", f"/evals/{batch.openai_eval_id}/runs/{batch.openai_eval_run_id}")
        batch.openai_eval_status = str(run_response.get("status") or batch.openai_eval_status or "")
        batch.openai_eval_report = self._remote_report(run_response)
        self.db.commit()
        self.db.refresh(batch)
        return self._batch_remote_state(batch)

    def _eval_payload(self, batch: EvaluationBatchRun) -> dict[str, Any]:
        """构造 Eval 定义，grader 直接评估本项目已生成的答案。"""

        return {
            "name": f"Ragent 批次评估 - {self._dataset_name(batch)}",
            "data_source_config": {
                "type": "custom",
                "schema": {
                    "type": "object",
                    "properties": {
                        "item": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"},
                                "expectedAnswer": {"type": "string"},
                                "expectedKeywords": {"type": "string"},
                                "answer": {"type": "string"},
                                "traceId": {"type": "string"},
                            },
                            "required": ["question", "answer"],
                        }
                    },
                    "required": ["item"],
                },
            },
            "testing_criteria": [
                {
                    "type": "label_model",
                    "model": settings.OPENAI_EVALS_GRADER_MODEL,
                    "name": "Ragent 输出可用性裁判",
                    "input": [
                        {
                            "role": "developer",
                            "content": (
                                "你是企业级 RAG/Agent 输出评估员。请判断回答是否准确、相关、忠实于参考答案或关键词，"
                                "并且是否给出了可执行结论。只能输出 pass 或 fail。"
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                "问题：{{item.question}}\n"
                                "参考答案：{{item.expectedAnswer}}\n"
                                "期望关键词：{{item.expectedKeywords}}\n"
                                "模型回答：{{item.answer}}\n"
                                "如果回答能解决问题且没有明显幻觉，输出 pass；否则输出 fail。"
                            ),
                        },
                    ],
                    "passing_labels": ["pass"],
                    "labels": ["pass", "fail"],
                }
            ],
            "metadata": {
                "source": "ragent-python",
                "batchId": batch.id,
                "datasetId": batch.dataset_id,
            },
        }

    def _run_payload(self, batch: EvaluationBatchRun) -> dict[str, Any]:
        """构造 Eval Run 数据源，使用本地批次已经产出的答案。"""

        items = [
            {
                "item": {
                    "question": result.question,
                    "expectedAnswer": result.expected_answer or "",
                    "expectedKeywords": "、".join(str(item) for item in (result.case.expected_keywords or [])) if result.case else "",
                    "answer": result.answer or "",
                    "traceId": result.trace_id or "",
                }
            }
            for result in self._completed_results(batch)
        ]
        if not items:
            raise ValueError("批次没有已完成的本地评估结果，无法提交 OpenAI Evals")
        return {
            "name": f"Ragent 本地输出复评 - {self._dataset_name(batch)}",
            "data_source": {
                "type": "jsonl",
                "source": {
                    "type": "file_content",
                    "content": items,
                },
            },
            "metadata": {
                "source": "ragent-python",
                "batchId": batch.id,
            },
        }

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """执行 OpenAI Evals API 请求，测试中可覆盖该方法避免真实网络。"""

        base = settings.OPENAI_EVALS_API_BASE.rstrip("/")
        url = f"{base}{path}"
        headers = {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=settings.OPENAI_EVALS_TIMEOUT_SECONDS) as client:
            response = client.request(method, url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return data if isinstance(data, dict) else {}

    def _batch(self, batch_id: str) -> EvaluationBatchRun:
        """按 ID 读取批次，找不到时抛出业务错误。"""

        batch = self.db.query(EvaluationBatchRun).filter(EvaluationBatchRun.id == batch_id).first()
        if not batch:
            raise ValueError("评估批次不存在")
        return batch

    @staticmethod
    def _completed_results(batch: EvaluationBatchRun) -> list[EvaluationCaseResult]:
        """只提交已完成且有答案的结果，避免远程评估无效样本。"""

        return [result for result in batch.results if result.status == "completed" and (result.answer or "").strip()]

    @staticmethod
    def _dataset_name(batch: EvaluationBatchRun) -> str:
        """读取数据集名称，缺失时退回批次 ID。"""

        return batch.dataset.name if batch.dataset else batch.id

    @staticmethod
    def _remote_report(run_response: dict[str, Any]) -> dict[str, Any]:
        """从远程 run 返回值中提取前端关心的报告字段。"""

        return {
            "reportUrl": run_response.get("report_url") or "",
            "resultCounts": run_response.get("result_counts") or {},
            "perModelUsage": run_response.get("per_model_usage") or [],
            "criteriaResults": run_response.get("per_testing_criteria_results") or [],
            "error": run_response.get("error"),
        }

    @staticmethod
    def _batch_remote_state(batch: EvaluationBatchRun) -> dict[str, Any]:
        """把本地保存的 OpenAI Evals 状态整理为接口响应。"""

        return {
            "evalId": batch.openai_eval_id or "",
            "runId": batch.openai_eval_run_id or "",
            "status": batch.openai_eval_status or "",
            "report": batch.openai_eval_report or {},
        }

    @staticmethod
    def _api_key() -> str:
        """优先使用专用 Evals key，缺省时复用 OpenAI 平台 key。"""

        return settings.OPENAI_EVALS_API_KEY or settings.OPENAI_API_KEY

    def _enabled(self) -> bool:
        """判断远程 OpenAI Evals 是否具备调用条件。"""

        return bool(settings.OPENAI_EVALS_ENABLED and self._api_key())

    def _ensure_remote_enabled(self) -> None:
        """远程调用前检查开关和凭证，避免未配置环境误触发外网请求。"""

        if not settings.OPENAI_EVALS_ENABLED:
            raise ValueError("OpenAI Evals 未启用，请配置 OPENAI_EVALS_ENABLED=true")
        if not self._api_key():
            raise ValueError("OpenAI Evals 缺少 API Key，请配置 OPENAI_EVALS_API_KEY")
