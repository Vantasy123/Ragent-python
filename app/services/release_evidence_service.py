"""Git 与 CI/CD 发布证据服务，用于把变更链路纳入 RCA。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Mapping


class ReleaseEvidenceService:
    """只读采集本地 Git 与 CI/CD 环境变量，辅助判断故障是否与发布相关。"""

    GITHUB_ENV_KEYS = {
        "runId": "GITHUB_RUN_ID",
        "runNumber": "GITHUB_RUN_NUMBER",
        "workflow": "GITHUB_WORKFLOW",
        "job": "GITHUB_JOB",
        "actor": "GITHUB_ACTOR",
        "repository": "GITHUB_REPOSITORY",
        "sha": "GITHUB_SHA",
        "ref": "GITHUB_REF_NAME",
        "serverUrl": "GITHUB_SERVER_URL",
    }
    GENERIC_ENV_KEYS = {
        "pipelineId": "CI_PIPELINE_ID",
        "jobUrl": "CI_JOB_URL",
        "buildNumber": "BUILD_NUMBER",
        "buildUrl": "BUILD_URL",
        "sha": "COMMIT_SHA",
        "gitCommit": "GIT_COMMIT",
        "deployEnv": "DEPLOY_ENV",
        "releaseVersion": "RELEASE_VERSION",
    }

    def __init__(self, repo_dir: Path | str | None = None, env: Mapping[str, str] | None = None) -> None:
        self.repo_dir = Path(repo_dir).resolve() if repo_dir else Path(__file__).resolve().parents[2]
        self.env = dict(env) if env is not None else dict(os.environ)

    def analyze(self, limit: int = 10) -> dict[str, Any]:
        """返回发布证据总览，所有 Git 命令均为只读命令。"""

        safe_limit = max(1, min(int(limit or 10), 50))
        inside = self._git(["rev-parse", "--is-inside-work-tree"])
        if not inside["success"] or inside["stdout"].strip().lower() != "true":
            return self._unavailable("当前目录不是 Git 工作区，无法采集发布证据", inside.get("stderr") or inside.get("stdout"))

        repo = self._repo_snapshot()
        commits = self._recent_commits(safe_limit)
        ci = self._ci_metadata()
        data_gaps = self._data_gaps(repo, ci)
        risk_signals = self._risk_signals(repo, ci, commits)
        rca_hints = self._root_cause_hints(repo, ci, commits, risk_signals)
        steps = self._recommended_steps(repo, ci, data_gaps, risk_signals)
        status = self._status_from_risks(risk_signals, data_gaps)

        return {
            "status": status,
            "displayName": "Git 与 CI/CD 发布证据",
            "summary": self._summary(repo, ci, risk_signals),
            "data": {
                "repo": repo,
                "recentCommits": commits,
                "ci": ci,
                "riskSignals": risk_signals,
                "rootCauseHints": rca_hints,
                "recommendedNextSteps": steps,
                "dataGaps": data_gaps,
            },
        }

    def _git(self, args: list[str], timeout: int = 5) -> dict[str, Any]:
        """执行只读 Git 命令，禁止 shell 展开，避免命令注入。"""

        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=self.repo_dir,
                shell=False,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            return {
                "success": completed.returncode == 0,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
                "returncode": completed.returncode,
            }
        except Exception as exc:
            return {"success": False, "stdout": "", "stderr": str(exc), "returncode": -1}

    def _repo_snapshot(self) -> dict[str, Any]:
        """采集分支、HEAD、上游分支、领先落后和工作区状态。"""

        branch_result = self._git(["rev-parse", "--abbrev-ref", "HEAD"])
        head_result = self._git(["rev-parse", "--short", "HEAD"])
        upstream_result = self._git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
        status_result = self._git(["status", "--short"])
        ahead_behind = self._ahead_behind(upstream_result["success"])
        status_lines = [line for line in status_result.get("stdout", "").splitlines() if line.strip()]

        return {
            "path": str(self.repo_dir),
            "branch": branch_result["stdout"] if branch_result["success"] else "unknown",
            "headSha": head_result["stdout"] if head_result["success"] else "",
            "upstream": upstream_result["stdout"] if upstream_result["success"] else "",
            "ahead": ahead_behind["ahead"],
            "behind": ahead_behind["behind"],
            "dirty": bool(status_lines),
            "statusLines": status_lines[:20],
            "hasUpstream": upstream_result["success"],
        }

    def _ahead_behind(self, has_upstream: bool) -> dict[str, int]:
        """解析当前分支相对 upstream 的领先和落后提交数。"""

        if not has_upstream:
            return {"ahead": 0, "behind": 0}
        result = self._git(["rev-list", "--left-right", "--count", "@{u}...HEAD"])
        if not result["success"]:
            return {"ahead": 0, "behind": 0}
        parts = result["stdout"].split()
        if len(parts) < 2:
            return {"ahead": 0, "behind": 0}
        return {"behind": self._safe_int(parts[0]), "ahead": self._safe_int(parts[1])}

    def _recent_commits(self, limit: int) -> list[dict[str, str]]:
        """读取近期提交摘要，作为发布诱因和回滚定位依据。"""

        fmt = "%h%x1f%an%x1f%ad%x1f%s"
        result = self._git(["log", "--max-count", str(limit), "--date=iso-strict", f"--pretty=format:{fmt}"])
        if not result["success"]:
            return []
        commits: list[dict[str, str]] = []
        for line in result["stdout"].splitlines():
            parts = line.split("\x1f")
            if len(parts) != 4:
                continue
            commits.append({"sha": parts[0], "author": parts[1], "date": parts[2], "subject": parts[3]})
        return commits

    def _ci_metadata(self) -> dict[str, Any]:
        """从常见 CI/CD 环境变量中抽取流水线和部署上下文。"""

        github = {key: self.env.get(env_key, "") for key, env_key in self.GITHUB_ENV_KEYS.items()}
        generic = {key: self.env.get(env_key, "") for key, env_key in self.GENERIC_ENV_KEYS.items()}
        provider = ""
        if any(github.values()):
            provider = "github_actions"
        elif self.env.get("GITLAB_CI") or generic.get("pipelineId"):
            provider = "gitlab_ci"
        elif self.env.get("CI") or any(generic.values()):
            provider = "generic_ci"

        sha = github.get("sha") or generic.get("sha") or generic.get("gitCommit") or ""
        run_url = ""
        if provider == "github_actions" and github.get("serverUrl") and github.get("repository") and github.get("runId"):
            run_url = f"{github['serverUrl'].rstrip('/')}/{github['repository']}/actions/runs/{github['runId']}"
        elif generic.get("jobUrl") or generic.get("buildUrl"):
            run_url = generic.get("jobUrl") or generic.get("buildUrl") or ""

        return {
            "provider": provider,
            "runId": github.get("runId") or generic.get("pipelineId") or "",
            "runNumber": github.get("runNumber") or generic.get("buildNumber") or "",
            "workflow": github.get("workflow") or "",
            "job": github.get("job") or "",
            "actor": github.get("actor") or "",
            "repository": github.get("repository") or "",
            "sha": sha,
            "ref": github.get("ref") or "",
            "url": run_url,
            "deployEnv": generic.get("deployEnv") or "",
            "releaseVersion": generic.get("releaseVersion") or "",
        }

    def _data_gaps(self, repo: dict[str, Any], ci: dict[str, Any]) -> list[str]:
        """生成发布证据缺口，指导后续接入 GitHub/GitLab 或发布系统。"""

        gaps: list[str] = []
        if not repo.get("hasUpstream"):
            gaps.append("当前分支没有 upstream，无法判断与远端发布分支的领先/落后关系")
        if not ci.get("provider"):
            gaps.append("未检测到 CI/CD 环境变量，无法确认本次部署流水线、产物和提交 SHA")
        if ci.get("provider") and not ci.get("sha"):
            gaps.append("CI/CD 元数据缺少提交 SHA，无法和当前 HEAD 做一致性校验")
        if ci.get("provider") and not ci.get("url"):
            gaps.append("CI/CD 元数据缺少流水线 URL，无法直接跳转复核构建和部署日志")
        return gaps

    def _risk_signals(self, repo: dict[str, Any], ci: dict[str, Any], commits: list[dict[str, str]]) -> list[dict[str, str]]:
        """把 Git/CI 状态转成 RCA 可消费的风险信号。"""

        signals: list[dict[str, str]] = []
        if repo.get("dirty"):
            signals.append({"severity": "medium", "type": "dirty_worktree", "message": "工作区存在未提交改动，发布前需要确认是否混入未审计变更"})
        if repo.get("ahead", 0) > 0:
            signals.append({"severity": "medium", "type": "ahead_remote", "message": f"当前分支领先 upstream {repo['ahead']} 个提交，需确认这些提交是否已经进入发布产物"})
        if repo.get("behind", 0) > 0:
            signals.append({"severity": "high", "type": "behind_remote", "message": f"当前分支落后 upstream {repo['behind']} 个提交，诊断证据可能不是线上最新代码"})
        if not repo.get("hasUpstream"):
            signals.append({"severity": "medium", "type": "missing_upstream", "message": "当前分支未配置 upstream，无法自动比对远端发布状态"})

        ci_sha = str(ci.get("sha") or "").strip()
        head_sha = str(repo.get("headSha") or "").strip()
        if ci_sha and head_sha and not (ci_sha.startswith(head_sha) or head_sha.startswith(ci_sha)):
            signals.append({"severity": "high", "type": "ci_sha_mismatch", "message": f"CI/CD 提交 {ci_sha[:12]} 与当前 HEAD {head_sha} 不一致"})

        for commit in commits[:5]:
            subject = str(commit.get("subject") or "").lower()
            if any(keyword in subject for keyword in ["revert", "rollback", "hotfix", "fix", "deploy", "release", "config", "schema"]):
                signals.append(
                    {
                        "severity": "low",
                        "type": "release_keyword",
                        "message": f"近期提交 {commit.get('sha')} 含发布/修复/配置关键词：{commit.get('subject')}",
                    }
                )
        return self._deduplicate_dicts(signals, "message")

    def _root_cause_hints(
        self,
        repo: dict[str, Any],
        ci: dict[str, Any],
        commits: list[dict[str, str]],
        risk_signals: list[dict[str, str]],
    ) -> list[str]:
        """生成面向诊断报告的根因初筛线索。"""

        hints: list[str] = []
        if ci.get("provider"):
            hints.append(f"检测到 {ci['provider']} 流水线证据，可把告警发生时间与流水线 {ci.get('runId') or ci.get('runNumber') or 'unknown'} 对齐")
        if commits:
            latest = commits[0]
            hints.append(f"当前 HEAD {repo.get('headSha')} 最近提交：{latest.get('subject')}，时间 {latest.get('date')}")
        for signal in risk_signals:
            if signal.get("severity") in {"high", "medium"}:
                hints.append(str(signal.get("message") or ""))
        return self._deduplicate(hints)

    def _recommended_steps(
        self,
        repo: dict[str, Any],
        ci: dict[str, Any],
        data_gaps: list[str],
        risk_signals: list[dict[str, str]],
    ) -> list[str]:
        """给出保守的复核、回滚和数据接入建议，执行仍交给审批链路。"""

        steps = [
            "把告警首次触发时间与最近提交时间、CI/CD 部署时间做时间线对齐",
            "核对线上镜像 tag、部署产物 SHA 与当前 Git HEAD 是否一致",
        ]
        if any(signal.get("type") == "ci_sha_mismatch" for signal in risk_signals):
            steps.append("暂停自动修复，优先人工确认线上版本、流水线产物和当前仓库代码是否一致")
        if repo.get("dirty") or repo.get("ahead", 0) > 0:
            steps.append("在发布或回滚前先保存 diff 并确认未提交改动、领先提交是否经过评审")
        if ci.get("url"):
            steps.append(f"打开流水线记录 {ci['url']}，复核构建、测试、部署和回滚步骤日志")
        if data_gaps:
            steps.append("在 CI/CD 流水线中注入 GITHUB_SHA/CI_PIPELINE_ID/RELEASE_VERSION 等变量，并同步到告警标签")
        return self._deduplicate(steps)

    def _summary(self, repo: dict[str, Any], ci: dict[str, Any], risk_signals: list[dict[str, str]]) -> str:
        """生成一行摘要，方便工具结果和前端直接展示。"""

        risk_count = len(risk_signals)
        ci_text = ci.get("provider") or "未检测到 CI/CD"
        return f"当前分支 {repo.get('branch')}@{repo.get('headSha')}，{ci_text}，识别 {risk_count} 条发布风险信号"

    def _status_from_risks(self, risk_signals: list[dict[str, str]], data_gaps: list[str]) -> str:
        """按风险等级映射前端状态。"""

        if any(signal.get("severity") == "high" for signal in risk_signals):
            return "critical"
        if risk_signals or data_gaps:
            return "degraded"
        return "healthy"

    def _unavailable(self, summary: str, error: str | None = None) -> dict[str, Any]:
        """Git 不可用时返回结构化降级结果。"""

        return {
            "status": "degraded",
            "displayName": "Git 与 CI/CD 发布证据",
            "summary": summary,
            "error": error or "git_not_available",
            "data": {
                "repo": {"path": str(self.repo_dir), "branch": "unknown", "headSha": "", "dirty": False},
                "recentCommits": [],
                "ci": self._ci_metadata(),
                "riskSignals": [],
                "rootCauseHints": [],
                "recommendedNextSteps": ["确认服务运行目录是 Git 工作区，并在部署环境挂载只读仓库元数据或发布清单"],
                "dataGaps": [summary],
            },
        }

    def _safe_int(self, value: str) -> int:
        """容错转换整数。"""

        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _deduplicate(self, items: list[str]) -> list[str]:
        """按原顺序去重文本列表。"""

        seen: set[str] = set()
        results: list[str] = []
        for item in items:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            results.append(text)
        return results

    def _deduplicate_dicts(self, items: list[dict[str, str]], key: str) -> list[dict[str, str]]:
        """按指定字段去重字典列表。"""

        seen: set[str] = set()
        results: list[dict[str, str]] = []
        for item in items:
            marker = str(item.get(key) or "").strip()
            if not marker or marker in seen:
                continue
            seen.add(marker)
            results.append(item)
        return results
