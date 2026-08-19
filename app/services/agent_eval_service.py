"""面向 Agent 实验的聚合、对比和运维轨迹评估工具。"""

from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any, Iterable


DEFAULT_THRESHOLD = 0.7


def _completed_metrics(results: Iterable[dict[str, Any]]) -> dict[str, list[float]]:
    """按指标名收集已完成分数，忽略 skipped 和非法值。"""

    buckets: dict[str, list[float]] = defaultdict(list)
    for result in results:
        metrics = result.get("metrics") if isinstance(result, dict) else None
        if not isinstance(metrics, dict):
            continue
        for key, metric in metrics.items():
            if not isinstance(metric, dict) or metric.get("status") not in {None, "completed"}:
                continue
            try:
                score = float(metric.get("score"))
            except (TypeError, ValueError):
                continue
            buckets[str(key)].append(max(0.0, min(1.0, score)))
    return buckets


def summarize_experiment(
    results: Iterable[dict[str, Any]],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """生成实验摘要，支持均值、P50、通过率和样本数。"""

    result_list = [result for result in results if isinstance(result, dict)]
    buckets = _completed_metrics(result_list)
    metrics: dict[str, dict[str, Any]] = {}
    for key, values in sorted(buckets.items()):
        ordered = sorted(values)
        metrics[key] = {
            "count": len(values),
            "mean": round(sum(values) / len(values), 4),
            "p50": round(float(median(ordered)), 4),
            "passRate": round(sum(value >= threshold for value in values) / len(values), 4),
            "threshold": threshold,
        }

    means = [item["mean"] for item in metrics.values()]
    return {
        "sampleCount": len(result_list),
        "scoredObservationCount": sum(item["count"] for item in metrics.values()),
        "metricCount": len(metrics),
        "overallMean": round(sum(means) / len(means), 4) if means else 0.0,
        "metrics": metrics,
    }


def compare_experiments(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    higher_is_better: set[str] | None = None,
    min_delta: float = 0.02,
) -> dict[str, Any]:
    """比较两个实验摘要，并以回归门禁形式返回结论。"""

    higher_is_better = higher_is_better or set()
    baseline_metrics = baseline.get("metrics") if isinstance(baseline.get("metrics"), dict) else {}
    candidate_metrics = candidate.get("metrics") if isinstance(candidate.get("metrics"), dict) else {}
    keys = sorted(set(baseline_metrics) | set(candidate_metrics))
    comparisons: dict[str, dict[str, Any]] = {}
    improved: list[str] = []
    regressed: list[str] = []

    for key in keys:
        before = baseline_metrics.get(key, {}).get("mean")
        after = candidate_metrics.get(key, {}).get("mean")
        if before is None or after is None:
            comparisons[key] = {"status": "missing", "baseline": before, "candidate": after}
            continue
        delta = round(float(after) - float(before), 4)
        effective_delta = delta if key in higher_is_better else -delta
        if effective_delta >= min_delta:
            status = "improved"
            improved.append(key)
        elif effective_delta <= -min_delta:
            status = "regressed"
            regressed.append(key)
        else:
            status = "unchanged"
        comparisons[key] = {
            "status": status,
            "baseline": round(float(before), 4),
            "candidate": round(float(after), 4),
            "delta": delta,
        }

    baseline_overall = float(baseline.get("overallMean") or 0.0)
    candidate_overall = float(candidate.get("overallMean") or 0.0)
    return {
        "baselineOverallMean": round(baseline_overall, 4),
        "candidateOverallMean": round(candidate_overall, 4),
        "overallDelta": round(candidate_overall - baseline_overall, 4),
        "improved": improved,
        "regressed": regressed,
        "regressionGate": "failed" if regressed else "passed",
        "comparisons": comparisons,
    }


def evaluate_ops_trajectory(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """从 Ops Agent 事件流计算可解释的效率、可靠性和安全指标。"""

    event_list = [event for event in events if isinstance(event, dict)]
    tool_calls = [event for event in event_list if event.get("type") == "tool_call"]
    observations = [event for event in event_list if event.get("type") == "observation"]
    approvals = [event for event in event_list if event.get("type") == "approval_required"]
    replans = [event for event in event_list if event.get("type") == "replan_decision"]
    failures = [
        event
        for event in observations
        if event.get("result", {}).get("success") is False
        or event.get("status") in {"failed", "error"}
    ]
    write_calls = [
        event
        for event in tool_calls
        if str(event.get("riskLevel") or event.get("risk_level") or "").lower() in {"write", "high", "critical"}
    ]
    approved_write_events = [
        event
        for event in event_list
        if event.get("type") in {"approval_required", "approval_granted", "approval_denied"}
    ]
    durations = [int(event["durationMs"]) for event in observations if str(event.get("durationMs", "")).isdigit()]
    evidence_count = sum(
        len((event.get("result") or {}).get("data", {}).get("sources", []))
        for event in observations
        if isinstance(event.get("result"), dict)
        and isinstance((event.get("result") or {}).get("data"), dict)
    )
    final = next((event for event in reversed(event_list) if event.get("type") in {"done", "final_answer"}), None)

    return {
        "toolCallCount": len(tool_calls),
        "observationCount": len(observations),
        "replanCount": len(replans),
        "approvalRequiredCount": len(approvals),
        "writeCallCount": len(write_calls),
        "approvalCoverage": round(len(approved_write_events) / len(write_calls), 4) if write_calls else 1.0,
        "toolFailureRate": round(len(failures) / len(observations), 4) if observations else 0.0,
        "meanToolLatencyMs": round(sum(durations) / len(durations), 2) if durations else 0.0,
        "p50ToolLatencyMs": int(median(durations)) if durations else 0,
        "evidenceCount": evidence_count,
        "completed": bool(final and final.get("type") == "done"),
        "eventCount": len(event_list),
    }
