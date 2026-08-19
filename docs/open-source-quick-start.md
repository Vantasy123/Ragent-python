# 智能求职 Agent 开源快速开始 (Quick Start)

目标是让使用者仅需修改基础配置，无需改动源码，即可在本地或服务器上一键拉起**智能求职 Agent 平台**与**大模型评测中心**。

---

## 1. 准备配置

复制示例环境变量与服务器配置：

```bash
cp .env.example .env
cp config/servers.example.yml config/servers.yml
```

主要修改项：
- `.env` 中的 `OPENAI_API_KEY`、`OPENAI_API_BASE`、`CHAT_MODEL`（支持通义千问、DeepSeek、OpenAI、SiliconFlow 等兼容接口）。
- `.env` 中的 `JWT_SECRET`、`DEFAULT_ADMIN_PASSWORD`。
- （可选）若需体验评测体系外部打分与追踪，配置 `OPENAI_EVALS_API_KEY` 或 `LANGCHAIN_API_KEY`。

---

## 2. 一键启动 (Docker Compose)

### Windows 用户：
```powershell
# 启动全栈服务（前后端 + 数据库 + 向量库 + Redis + 对象存储）
scripts\start-project.bat

# 修改代码后强制重新构建启动
scripts\start-project.bat -Build
```

### Linux / macOS 用户：
```bash
# 启动全栈服务
bash scripts/start-project.sh full

# 仅启动后端与存储底座（前端通过本地 npm run dev 调试）
bash scripts/start-project.sh backend
```

---

## 3. 本地独立启动 (开发者模式)

如果不使用 Docker，可以在本地直接运行：

### 后端环境 (Python 3.10+)：
```bash
# 1. 创建并激活虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\activate

# 2. 安装核心依赖
pip install -r requirements.txt

# 3. 启动 FastAPI 服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 前端环境 (Node 18+)：
```bash
cd frontend
npm install
npm run dev
```

---

## 4. 核心功能与页面入口

- 🏠 **前端主页**：`http://localhost/` 或 `http://localhost:5173/`
- 💬 **智能求职工作台**：`http://localhost/chat`（支持求职意图自动识别与 ReAct 6 大求职工具调度）
- 📄 **智能简历中枢**：`http://localhost/admin/resumes`（多维结构化解析、STAR 法则深度润色、多版本管理）
- 🎯 **岗位与人岗匹配**：`http://localhost/admin/job-matching`（0-100 全维度打分、破冰打招呼与求职信生成）
- 📋 **求职投递看板**：`http://localhost/admin/job-kanban`（流水线看板、面试日程与复盘笔记）
- 🎤 **AI 模拟面试厅**：`http://localhost/admin/mock-interviews`（4 类大厂面试官、多轮沉浸式出题、五维雷达图报告）
- ⚡ **网申自动填表**：`http://localhost/admin/job-autofill`（NowClaw Bridge 映射与自动填充 Payload 生成）
- 📊 **智能体评测中心**：`http://localhost/admin/evaluations`（评测集管理、批次对比、BLEU/ROUGE 统计与回归门禁）
- 📖 **API 文档 (Swagger)**：`http://localhost:8000/docs`
