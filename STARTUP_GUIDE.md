# 🚀 Ragent-Python 完整启动指南

## 📋 前置要求

- Python 3.10+
- Node.js 18+ (用于前端)
- PostgreSQL 14+ (含 pgvector 扩展)
- Docker & Docker Compose (可选，用于容器化部署)

---

## 🎯 方式 1: 本地开发模式（推荐用于开发）

### 步骤 1: 准备数据库

```bash
# 创建数据库
createdb ragent

# 启用 pgvector 扩展
psql -d ragent -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 步骤 2: 配置环境变量

创建 `.env` 文件：

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ragent
OPENAI_API_KEY=your-api-key-here
OPENAI_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
CHAT_MODEL=qwen-plus
```

### 步骤 3: 安装 Python 依赖

```bash
cd ragent-python
pip install -r requirements.txt
```

### 步骤 4: 启动后端服务

```bash
python main.py
```

后端将在 http://localhost:8000 启动

### 步骤 5: 启动前端界面

**新开一个终端窗口**：

```bash
# Windows
start-frontend.bat

# Linux/Mac
chmod +x start-frontend.sh
./start-frontend.sh
```

或者手动启动：

```bash
cd frontend
npm install
npm run dev
```

前端将在 http://localhost:5173 启动

### 步骤 6: 访问应用

- **前端界面**: http://localhost:5173
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/api/health

---

## 🐳 方式 2: Docker 部署（推荐用于生产）

### 步骤 1: 配置环境变量

创建 `.env` 文件：

```env
OPENAI_API_KEY=your-api-key-here
OPENAI_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
CHAT_MODEL=qwen-plus
DEBUG=false
```

### 步骤 2: 启动完整栈（含前端）

```bash
# 启动所有服务（PostgreSQL + Backend + Frontend）
docker-compose --profile full up -d
```

这将启动：
- PostgreSQL (端口 5432)
- Ragent API (端口 8000)
- Frontend (端口 80)

### 步骤 3: 访问应用

- **前端界面**: http://localhost
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/api/health

### 常用命令

```bash
# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看服务状态
docker-compose ps
```

---

## 🔧 方式 3: 仅后端 API（无前端）

### 步骤 1: 准备数据库

同方式 1

### 步骤 2: 启动后端

```bash
python main.py
```

### 步骤 3: 使用 API

通过 curl 或 Postman 测试：

```bash
# 健康检查
curl http://localhost:8000/api/health

# 创建知识库
curl -X POST http://localhost:8000/api/knowledge-base \
  -H "Content-Type: application/json" \
  -d '{"name": "测试知识库", "description": "测试"}'

# 智能对话
curl "http://localhost:8000/api/workflow/chat?message=你好"
```

访问 API 文档: http://localhost:8000/docs

---

## 📱 前端功能使用

### 1. 智能对话

1. 打开 http://localhost:5173
2. 在底部输入框输入问题
3. 按 Enter 发送
4. 查看实时流式响应

**示例问题**:
- "公司的报销政策是什么？"
- "Python 和 Java 有什么区别？"
- "如何配置数据库？"

### 2. 知识库管理

#### 创建知识库
1. 点击左侧"知识库管理"
2. 点击右上角"+ 创建知识库"
3. 输入名称和描述
4. 点击"创建"

#### 上传文档
1. 点击知识库卡片上的"管理文档"
2. 选择文件（PDF、Word、TXT、Markdown）
3. 点击"上传"

#### 开始分块
1. 在文档列表中找到已上传的文档
2. 点击"开始分块"按钮
3. 等待处理完成

---

## 🐛 故障排查

### 问题 1: 后端启动失败

**可能原因**:
- 数据库未启动
- 端口被占用
- 依赖未安装

**解决方案**:
```bash
# 检查数据库连接
psql -U postgres -d ragent -c "SELECT 1;"

# 检查端口占用
netstat -tuln | grep 8000

# 重新安装依赖
pip install -r requirements.txt
```

---

### 问题 2: 前端无法连接后端

**检查项**:
1. 后端是否正在运行
2. API 地址是否正确
3. CORS 配置是否正确

**解决方案**:
```bash
# 测试后端
curl http://localhost:8000/api/health

# 检查浏览器控制台
# F12 -> Console 查看错误信息
```

---

### 问题 3: 对话没有响应

**可能原因**:
- API Key 无效
- 网络连接问题
- 模型服务不可用

**解决方案**:
```bash
# 检查 .env 文件
cat .env

# 测试模型 API
curl -X POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-plus","messages":[{"role":"user","content":"Hi"}]}'
```

---

### 问题 4: Docker 启动失败

**解决方案**:
```bash
# 查看详细日志
docker-compose logs

# 清理并重新启动
docker-compose down -v
docker-compose --profile full up -d

# 检查容器状态
docker-compose ps
```

---

## 📊 系统架构

```
┌──────────────┐
│   Browser    │ ← 用户访问
└──────┬───────┘
       │
       ↓
┌──────────────┐
│   Frontend   │ ← Vue 3 (端口 5173 或 80)
│  (Vue 3)     │
└──────┬───────┘
       │ API 请求
       ↓
┌──────────────┐
│   Backend    │ ← FastAPI (端口 8000)
│  (FastAPI)   │
└──────┬───────┘
       │
       ↓
┌──────────────┐
│  PostgreSQL  │ ← 数据库 (端口 5432)
│  + pgvector  │
└──────────────┘
```

---

## 🎯 下一步

### 开发建议
1. 阅读 [FRONTEND_GUIDE.md](FRONTEND_GUIDE.md) 了解前端开发
2. 查看 [DEPLOYMENT.md](DEPLOYMENT.md) 了解生产部署
3. 访问 http://localhost:8000/docs 查看完整 API 文档

### 功能扩展
- 添加新的 MCP 工具
- 自定义检索策略
- 集成更多数据源
- 添加用户认证

### 性能优化
- 启用 Redis 缓存
- 配置 CDN
- 优化数据库查询
- 启用 HTTP/2

---

## 📞 获取帮助

- 📖 查看项目文档
- 🐛 提交 GitHub Issue
- 💬 查看浏览器控制台错误
- 📊 检查后端日志

---

**祝使用愉快！** 🎉
