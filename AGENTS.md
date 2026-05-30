# AGENTS.md

## 目的 (Purpose)

本项目已启用轻量级多智能体协作规范（Lightweight Multi-Agent Collaboration）。
此文件是所有协作智能体（如 Antigravity, Codex 等）的唯一入口引导指南。
请在开始任何任务前，务必先阅读此文件，并遵守底部的协作规范。

## 默认协作工作流 (Default Workflow)

1. **阅读引导**：阅读此 `AGENTS.md` 确认最新的开发规范与架构设计文件。
2. **加锁声明**：在开始任务前，检查 `.agent/locks/` 是否有文件冲突。确认无冲突后，在 `.agent/locks/` 目录下创建一个锁文件（例如 `.agent/locks/<task-name>.lock`），声明锁定你要修改的文件列表，避免与其它 Agent 产生修改冲突。
3. **分支隔离**：遵循“一个任务一个 Git 分支”的原则，开始前必须新建 Git 分支 (`git checkout -b <branch-name>`)。
4. **按需读取**：根据修改的任务域，只读取相关的设计文档，防止上下文过载。
5. **最小验证**：在独立分支上开发，并进行最小验证（通过运行测试/构建）。
6. **合并前检查**：在提交/合并前，顺序执行并确认：
   - `git status`
   - `git diff`
   - `git pull --rebase`
7. **日志追加与解锁**：在 `docs/task-log.md` 中以追加模式记录本次任务摘要（禁止修改任何历史日志）。然后删除锁文件。

## 按需读取索引 (Read-on-demand Index)

- 架构设计与核心模块：`docs/architecture.md`
- API、控制器及路由设计：`docs/api.md`
- 数据库与 ORM 模型设计：`docs/db-design.md`
- 历史任务进展日志：`docs/task-log/index.md`（仅限阅读最新的 5 条记录）
- 共享长期事实与约定：`.agent/memory.md`

## 核心协作规范

- 严禁修改其它锁文件中已锁定的文件。
- 一个任务对应一个 Git 分支，并在合并前进行 Rebase。
- 任务日志 `docs/task-log.md` 必须为**只追加（Append-only）**，严禁篡改历史。
- 凡是不确定的信息或需要用户决定的，在文档中明确标记为 `待人工确认`。
