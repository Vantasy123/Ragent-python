"""岗位搜索质量评测与 baseline/candidate 回归门禁。"""

from __future__ import annotations

import json
from math import log2
from pathlib import Path
from typing import Any, Callable, Iterable


SearchFn = Callable[[dict[str, Any]], list[dict[str, Any]]]


def _job_id(job: dict[str, Any]) -> str:
    return str(job.get("id") or job.get("external_job_id") or job.get("source_url") or "")


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return round(sum(values) / len(values), 4) if values else 0.0


def load_job_search_catalog(path: str | Path) -> dict[str, Any]:
    """加载并校验固定岗位搜索 catalog，避免评测悄悄使用空或重复 case。"""
    catalog_path = Path(path)
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("岗位搜索 catalog 必须包含 cases 数组")
    case_ids: set[str] = set()
    for case in payload["cases"]:
        if not isinstance(case, dict):
            raise ValueError("岗位搜索 catalog case 必须是对象")
        case_id = str(case.get("id") or "")
        if not case_id or case_id in case_ids:
            raise ValueError(f"岗位搜索 catalog case id 无效或重复：{case_id}")
        case_ids.add(case_id)
        for field in ("keyword", "city", "platform", "job_type", "gold_jobs"):
            if field not in case:
                raise ValueError(f"岗位搜索 catalog case 缺少字段：{case_id}.{field}")
        if not isinstance(case["gold_jobs"], dict):
            raise ValueError(f"gold_jobs 必须是对象：{case_id}")
    return payload


def _matches_hard_filters(job: dict[str, Any], hard_filters: dict[str, Any]) -> bool:
    """按 catalog 声明的字段检查岗位是否满足硬过滤条件。"""
    aliases = {
        "platform": ("source_platform", "sourcePlatform"),
        "city": ("city",),
        "job_type": ("job_type", "jobType"),
    }
    for field, expected in hard_filters.items():
        if field not in aliases:
            continue
        actual = next((job.get(key) for key in aliases[field] if job.get(key) is not None), None)
        if str(expected) != str(actual):
            return False
    return True


def evaluate_search_case(
    retrieved_jobs: list[dict[str, Any]],
    gold_jobs: dict[str, int],
    *,
    k: int = 10,
    excluded_ids: set[str] | None = None,
    required_platform: str | None = None,
    hard_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """评测一个固定 catalog 查询，gold_jobs 的值为 0-3 graded relevance。"""

    top_jobs = retrieved_jobs[: max(0, k)]
    ids = [_job_id(job) for job in top_jobs]
    relevant_ids = {job_id for job_id, grade in gold_jobs.items() if int(grade) > 0}
    excluded_ids = excluded_ids or set()

    duplicate_count = len(ids) - len(set(ids))
    relevant_hits = [job_id for job_id in ids if job_id in relevant_ids]
    first_relevant_rank = next((rank for rank, job_id in enumerate(ids, 1) if job_id in relevant_ids), None)
    dcg = sum(
        max(0, int(gold_jobs.get(job_id, 0))) / log2(rank + 1)
        for rank, job_id in enumerate(ids, 1)
    )
    ideal = sorted((max(0, int(value)) for value in gold_jobs.values()), reverse=True)[: len(ids)]
    idcg = sum(value / log2(rank + 1) for rank, value in enumerate(ideal, 1))
    violations = sum(
        job_id in excluded_ids or (hard_filters is not None and not _matches_hard_filters(job, hard_filters))
        for job_id, job in zip(ids, top_jobs)
    )
    platform_hits = sum(
        str(job.get("source_platform") or job.get("sourcePlatform") or "") == required_platform
        for job in top_jobs
    ) if required_platform else 0

    return {
        "retrievedCount": len(top_jobs),
        "relevantCount": len(relevant_ids),
        "precisionAtK": round(len(set(relevant_hits)) / len(ids), 4) if ids else 0.0,
        "recallAtK": round(len(set(relevant_hits)) / len(relevant_ids), 4) if relevant_ids else 0.0,
        "mrr": round(1 / first_relevant_rank, 4) if first_relevant_rank else 0.0,
        "ndcgAtK": round(dcg / idcg, 4) if idcg else 0.0,
        "hitAtK": 1.0 if relevant_hits else 0.0,
        "hardFilterViolationRate": round(violations / len(ids), 4) if ids else 0.0,
        "duplicateRate": round(duplicate_count / len(ids), 4) if ids else 0.0,
        "platformCoverage": round(platform_hits / len(ids), 4) if required_platform and ids else (1.0 if not required_platform and ids else 0.0),
        "duplicateCount": duplicate_count,
        "hardFilterViolationCount": violations,
    }


def summarize_search_cases(cases: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """聚合多个固定查询的搜索指标。"""
    case_list = [case for case in cases if isinstance(case, dict)]
    metric_names = (
        "precisionAtK", "recallAtK", "mrr", "ndcgAtK", "hitAtK",
        "hardFilterViolationRate", "duplicateRate", "platformCoverage",
    )
    metrics = {name: _mean(case.get(name, 0.0) for case in case_list) for name in metric_names}
    return {"caseCount": len(case_list), "metrics": metrics}


def _search_input(case: dict[str, Any]) -> dict[str, Any]:
    """只向搜索适配器暴露查询与候选岗位，隔离评测标签。"""
    return {
        "id": case["id"],
        "keyword": case.get("keyword", ""),
        "city": case.get("city", ""),
        "platform": case.get("platform", "all"),
        "job_type": case.get("job_type", "all"),
        "hard_filters": dict(case.get("hard_filters") or {}),
        "retrieved_jobs": [dict(job) for job in case.get("retrieved_jobs", [])],
    }
def evaluate_catalog_variant(
    catalog: dict[str, Any],
    variant: str,
    search_fn: SearchFn,
    *,
    k: int = 3,
) -> dict[str, Any]:
    """执行 catalog 查询，并仅在评测侧读取 gold 标签计算指标。"""
    case_results: list[dict[str, Any]] = []
    for case in catalog["cases"]:
        retrieved = search_fn(_search_input(case))
        if not isinstance(retrieved, list) or not all(isinstance(job, dict) for job in retrieved):
            raise TypeError(f"{variant} 返回值必须是岗位对象列表：{case['id']}")
        metrics = evaluate_search_case(
            retrieved,
            {str(job_id): int(grade) for job_id, grade in case["gold_jobs"].items()},
            k=k,
            excluded_ids={str(item) for item in case.get("excluded_ids", [])},
            required_platform=case.get("hard_filters", {}).get("platform"),
            hard_filters=case.get("hard_filters"),
        )
        case_results.append({
            "id": case["id"],
            "query": {key: case.get(key) for key in ("keyword", "city", "platform", "job_type")},
            "retrievedIds": [_job_id(job) for job in retrieved[:k]],
            "metrics": metrics,
        })
    summary = summarize_search_cases(item["metrics"] for item in case_results)
    return {
        "variant": variant,
        "catalogVersion": catalog.get("version"),
        "cases": case_results,
        "caseCount": summary["caseCount"],
        "metrics": summary["metrics"],
    }


def compare_catalog_variants(
    catalog: dict[str, Any],
    baseline_search: SearchFn,
    candidate_search: SearchFn,
    *,
    minimums: dict[str, float] | None = None,
    allowed_regression: dict[str, float] | None = None,
    k: int = 3,
    experiment_id: str = "job-search-catalog-v1",
) -> dict[str, Any]:
    """执行两套真实搜索适配器并对实际计算结果执行回归门禁。"""
    baseline = evaluate_catalog_variant(catalog, "baseline", baseline_search, k=k)
    candidate = evaluate_catalog_variant(catalog, "candidate", candidate_search, k=k)
    comparison = compare_search_runs(
        baseline,
        candidate,
        minimums=minimums,
        allowed_regression=allowed_regression,
    )
    return {"experimentId": experiment_id, "catalogVersion": catalog.get("version"), **comparison}


def compare_search_runs(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    minimums: dict[str, float] | None = None,
    allowed_regression: dict[str, float] | None = None,
) -> dict[str, Any]:
    """比较搜索实验并执行绝对门槛与允许回归幅度门禁。"""
    minimums = minimums or {}
    allowed_regression = allowed_regression or {}
    before = baseline.get("metrics") if isinstance(baseline.get("metrics"), dict) else {}
    after = candidate.get("metrics") if isinstance(candidate.get("metrics"), dict) else {}
    keys = sorted(set(before) | set(after) | set(minimums))
    higher_is_better = {"precisionAtK", "recallAtK", "mrr", "ndcgAtK", "hitAtK", "platformCoverage"}
    comparisons: dict[str, Any] = {}
    failures: list[str] = []
    for key in keys:
        base_value = float(before.get(key, 0.0))
        candidate_value = float(after.get(key, 0.0))
        delta = round(candidate_value - base_value, 4)
        minimum = minimums.get(key)
        limit = float(allowed_regression.get(key, 0.0))
        minimum_failed = minimum is not None and candidate_value < float(minimum)
        regression_failed = (base_value - candidate_value) > limit if key in higher_is_better else (candidate_value - base_value) > limit
        if minimum_failed:
            failures.append(f"{key} 低于最低门槛 {minimum}")
        if regression_failed:
            failures.append(f"{key} 相比 baseline 回归超过允许值 {limit}")
        comparisons[key] = {
            "baseline": round(base_value, 4),
            "candidate": round(candidate_value, 4),
            "delta": delta,
            "minimum": minimum,
            "allowedRegression": limit,
            "minimumPassed": not minimum_failed,
            "regressionPassed": not regression_failed,
        }
    return {
        "gate": "passed" if not failures else "failed",
        "failures": failures,
        "baseline": baseline,
        "candidate": candidate,
        "comparisons": comparisons,
    }
