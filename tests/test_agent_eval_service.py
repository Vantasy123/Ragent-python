from __future__ import annotations

import unittest

from app.services.agent_eval_service import compare_experiments, evaluate_ops_trajectory, summarize_experiment


class AgentEvaluationServiceTest(unittest.TestCase):
    """验证实验对比和运维轨迹指标可作为稳定回归门禁。"""

    def test_experiment_comparison_flags_quality_regression(self) -> None:
        baseline = summarize_experiment(
            [
                {"metrics": {"answer_correctness": {"status": "completed", "score": 0.9}}},
                {"metrics": {"answer_correctness": {"status": "completed", "score": 0.8}}},
            ]
        )
        candidate = summarize_experiment(
            [
                {"metrics": {"answer_correctness": {"status": "completed", "score": 0.7}}},
                {"metrics": {"answer_correctness": {"status": "completed", "score": 0.6}}},
            ]
        )

        result = compare_experiments(
            baseline,
            candidate,
            higher_is_better={"answer_correctness"},
        )

        self.assertEqual(result["regressionGate"], "failed")
        self.assertEqual(result["comparisons"]["answer_correctness"]["status"], "regressed")
        self.assertEqual(baseline["metrics"]["answer_correctness"]["p50"], 0.85)

    def test_ops_trajectory_reports_safety_and_execution_signals(self) -> None:
        events = [
            {"type": "tool_call", "tool": "api_health_check"},
            {"type": "observation", "durationMs": 120, "result": {"success": True, "data": {"sources": ["probe"]}}},
            {"type": "tool_call", "tool": "compose_restart_service", "riskLevel": "write"},
            {"type": "approval_required", "tool": "compose_restart_service"},
            {"type": "replan_decision", "action": "blocked"},
            {"type": "done", "status": "completed"},
        ]

        metrics = evaluate_ops_trajectory(events)

        self.assertEqual(metrics["toolCallCount"], 2)
        self.assertEqual(metrics["approvalCoverage"], 1.0)
        self.assertEqual(metrics["toolFailureRate"], 0.0)
        self.assertEqual(metrics["replanCount"], 1)
        self.assertTrue(metrics["completed"])


if __name__ == "__main__":
    unittest.main()
