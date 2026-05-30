# 共享智能体记忆 (Shared Agent Memory)

本文档用于存储多智能体（Antigravity 与 Codex 等）在本项目开发中沉淀的长期稳定事实、约定及常见陷阱。临时性的任务细节请记录在 `docs/task-log.md` 中。

## 稳定项目事实 (Stable Project Facts)

- **后端技术栈**：基于 Python 3.10+、FastAPI 和 Uvicorn 构建，使用 MySQL 作为主关系数据库，Redis 负责会话缓存和并发计数，Milvus 负责向量检索。
- **前端技术栈**：基于 Vue 3、Vite 和 Tailwind CSS（非主要样式，核心为 style.css 编写的原生亮色主题风格）。
- **运行方式**：核心服务以 Docker 容器在本地运行，前端映射到 `80` 端口，后端映射到 `8000` 端口。

## 团队开发约定 (Conventions)

1. **默认协作对象**：
   - **在本项目中，当用户提及“协作”时，默认指与 Codex 的多智能体协作。**
   - 两名核心 Agent（Antigravity 与 Codex）在开发时，必须严格执行 `AGENTS.md` 规定的协作机制，实现修改锁保护与隔离开发。
2. **文档规范**：
   - 项目根目录的 `AGENTS.md` 是开发引导的唯一入口。
   - 所有智能体在完成任务后，必须以**只追加（Append-only）**的格式向 `docs/task-log.md` 记录变更，严禁修改以往的历史日志。
   - 无法确认的信息必须标明为 `待人工确认`。

## 常见排版与开发陷阱 (Common Pitfalls)

- **1280px 下的分栏折行**：在修改 `style.css` 时要注意，系统包含 `@media (max-width: 1100px)` 的分栏单列折行。如果在 1100px 以上页面排版异常，请优先检查是否误触发了折行。
- **长 UUID 表格挤压**：Trace ID 和 Session ID 等表格必须应用 `.cell-id`、`.cell-truncate` 防折行辅助类限制最大宽度在 130px，否则会导致表格行高被拉伸崩溃。
- **自动登录守卫**：路由守卫在带有 `?autologin=true` URL 参数时会自动登录管理员账号 `admin/admin123`，在进行无头截图或 API 走查时可直接拼接该参数。

## 待人工确认事项 (Human Confirmation Needed)

- 目前无未确认的关键技术阻碍。
