from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

from app.services.release_evidence_service import ReleaseEvidenceService


def run_git(repo: Path, *args: str) -> str:
    """执行测试用 Git 命令，失败时让 pytest 直接暴露 stderr。"""

    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        shell=False,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout.strip()


def make_repo() -> Path:
    """创建一个隔离的临时 Git 仓库，避免污染真实项目。"""

    repo = Path("scratch") / "pytest-tmp" / f"release-evidence-{uuid.uuid4().hex}"
    repo.mkdir(parents=True, exist_ok=True)
    run_git(repo, "-c", "init.defaultBranch=main", "init")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")
    (repo / "service.txt").write_text("v1\n", encoding="utf-8")
    run_git(repo, "add", "service.txt")
    run_git(repo, "commit", "-m", "release: initial deploy")
    return repo


class TestReleaseEvidenceService:
    """验证发布证据服务的 Git 与 CI/CD 解析能力。"""

    def teardown_method(self) -> None:
        # 只清理本测试创建的仓库，不能删除 pytest 正在使用的临时目录。
        for repo in (Path("scratch") / "pytest-tmp").glob("release-evidence-*"):
            shutil.rmtree(repo, ignore_errors=True)

    def test_analyze_reports_branch_head_and_dirty_risk(self) -> None:
        """工作区存在未提交改动时，应输出 dirty 风险和 GitHub Actions 元数据。"""

        repo = make_repo()
        head_sha = run_git(repo, "rev-parse", "--short", "HEAD")
        (repo / "service.txt").write_text("v2\n", encoding="utf-8")
        service = ReleaseEvidenceService(
            repo_dir=repo,
            env={
                "GITHUB_RUN_ID": "99",
                "GITHUB_RUN_NUMBER": "7",
                "GITHUB_SHA": head_sha,
                "GITHUB_REF_NAME": "main",
                "GITHUB_WORKFLOW": "deploy",
                "GITHUB_REPOSITORY": "demo/ragent",
                "GITHUB_SERVER_URL": "https://github.com",
            },
        )

        result = service.analyze(limit=5)
        data = result["data"]

        assert result["status"] == "degraded"
        assert data["repo"]["branch"] == "main"
        assert data["repo"]["headSha"] == head_sha
        assert data["repo"]["dirty"] is True
        assert data["ci"]["provider"] == "github_actions"
        assert data["ci"]["url"] == "https://github.com/demo/ragent/actions/runs/99"
        assert any(signal["type"] == "dirty_worktree" for signal in data["riskSignals"])
        assert data["recentCommits"][0]["subject"] == "release: initial deploy"

    def test_detects_ci_sha_mismatch_as_high_risk(self) -> None:
        """CI/CD 提交和当前 HEAD 不一致时，应标记为高风险。"""

        repo = make_repo()
        service = ReleaseEvidenceService(
            repo_dir=repo,
            env={
                "GITHUB_RUN_ID": "100",
                "GITHUB_SHA": "deadbeef",
                "GITHUB_REF_NAME": "main",
            },
        )

        result = service.analyze(limit=3)
        signals = result["data"]["riskSignals"]

        assert result["status"] == "critical"
        assert any(signal["type"] == "ci_sha_mismatch" and signal["severity"] == "high" for signal in signals)
        assert any("暂停自动修复" in step for step in result["data"]["recommendedNextSteps"])
