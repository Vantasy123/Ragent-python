"""岗位实时搜索与搜索质量评测测试。"""

from __future__ import annotations

from pathlib import Path

from app.services.job_search_eval_service import (
    compare_catalog_variants,
    compare_search_runs,
    evaluate_search_case,
    load_job_search_catalog,
)


CATALOG_PATH = Path(__file__).parent / "fixtures" / "job_search_catalog.json"


def _job(job_id: str, platform: str = "boss") -> dict:
    return {"id": job_id, "source_platform": platform}


def test_evaluate_search_case_perfect_ranking():
    result = evaluate_search_case(
        [_job("a"), _job("b"), _job("c")],
        {"a": 3, "b": 2, "c": 1},
        k=3,
        required_platform="boss",
    )
    assert result["precisionAtK"] == 1.0
    assert result["recallAtK"] == 1.0
    assert result["mrr"] == 1.0
    assert result["ndcgAtK"] == 1.0
    assert result["hardFilterViolationRate"] == 0.0


def test_evaluate_search_case_duplicate_and_filter_violation():
    result = evaluate_search_case(
        [_job("a"), _job("a"), _job("excluded", "liepin")],
        {"a": 3, "b": 2},
        k=3,
        excluded_ids={"excluded"},
        required_platform="boss",
    )
    assert result["duplicateRate"] > 0
    assert result["hardFilterViolationRate"] == 0.3333
    assert result["platformCoverage"] == 0.6667


def test_catalog_loader_validates_fixed_cases():
    catalog = load_job_search_catalog(CATALOG_PATH)
    assert catalog["version"] == 2
    assert [case["id"] for case in catalog["cases"]] == [
        "java-beijing-boss",
        "python-shanghai-all",
    ]
    assert all(case["retrieved_jobs"] for case in catalog["cases"])


def test_fixed_catalog_candidate_beats_baseline_from_retrieved_jobs():
    """从固定岗位序列实际执行两种策略，禁止直接手工构造 metrics。"""
    catalog = load_job_search_catalog(CATALOG_PATH)

    def baseline_search(search_input: dict) -> list[dict]:
        # 代表旧策略：沿用平台原始顺序，不过滤、不去重、不重排。
        return list(search_input["retrieved_jobs"])

    def candidate_search(search_input: dict) -> list[dict]:
        # 候选策略只能看到查询、硬过滤和离线回放候选，不能读取 gold 标签。
        assert "gold_jobs" not in search_input
        assert "gold_ranking" not in search_input
        assert "excluded_ids" not in search_input
        hard_filters = search_input["hard_filters"]

        def matches(job: dict) -> bool:
            if str(job.get("city")) != str(hard_filters["city"]):
                return False
            if str(job.get("job_type")) != str(hard_filters["job_type"]):
                return False
            platform = hard_filters.get("platform")
            return platform is None or str(job.get("source_platform")) == str(platform)

        filtered = [job for job in search_input["retrieved_jobs"] if matches(job)]
        return sorted(
            filtered,
            key=lambda job: (
                -len(job.get("search_terms", [])),
                {"boss": 0, "liepin": 1, "51job": 2, "nowcoder": 3}.get(
                    str(job.get("source_platform", "")), 99
                ),
                str(job.get("id", "")),
            ),
        )

    result = compare_catalog_variants(
        catalog,
        baseline_search,
        candidate_search,
        k=3,
        minimums={"ndcgAtK": 0.9, "recallAtK": 1.0, "hardFilterViolationRate": 0.0},
        allowed_regression={"ndcgAtK": 0.0, "recallAtK": 0.0, "hardFilterViolationRate": 0.0},
        experiment_id="offline-catalog-candidate-v1",
    )

    assert result["experimentId"] == "offline-catalog-candidate-v1"
    assert result["catalogVersion"] == 2
    assert result["gate"] == "passed"
    assert result["baseline"]["caseCount"] == 2
    assert result["candidate"]["caseCount"] == 2
    assert result["comparisons"]["ndcgAtK"]["delta"] > 0
    assert result["comparisons"]["recallAtK"]["delta"] > 0
    assert result["candidate"]["metrics"]["hardFilterViolationRate"] == 0.0
    assert result["candidate"]["cases"][0]["retrievedIds"] == [
        "boss-java-001",
        "boss-java-002",
        "boss-java-003",
    ]


def test_compare_search_runs_passes_improved_candidate():
    baseline = {"metrics": {"ndcgAtK": 0.6, "recallAtK": 0.5}}
    candidate = {"metrics": {"ndcgAtK": 0.8, "recallAtK": 0.7}}
    result = compare_search_runs(
        baseline,
        candidate,
        minimums={"ndcgAtK": 0.7, "recallAtK": 0.6},
        allowed_regression={"ndcgAtK": 0.0, "recallAtK": 0.0},
    )
    assert result["gate"] == "passed"


def test_compare_search_runs_fails_regression():
    result = compare_search_runs(
        {"metrics": {"ndcgAtK": 0.8}},
        {"metrics": {"ndcgAtK": 0.6}},
        minimums={"ndcgAtK": 0.7},
        allowed_regression={"ndcgAtK": 0.05},
    )
    assert result["gate"] == "failed"
    assert result["failures"]
