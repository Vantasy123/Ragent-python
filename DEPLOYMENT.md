# Docker 部署指南

## 📋 前置要求

- Docker 20.10+
- Docker Compose 2.0+

## 🚀 快速启动

### 方式 1: Docker Compose（推荐）

#### 1. 配置环境变量

创建 `.env` 文件：

```bash
# LLM API 配置
OPENAI_API_KEY=your-api-key-here
OPENAI_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
CHAT_MODEL=qwen-plus

# 应用配置
DEBUG=false
```

#### 2. 启动所有服务

```bash
docker-compose up -d
```

这将启动：

- PostgreSQL (含 pgvector) - 端口 5432
- Ragent API - 端口 8000
- Redis (可选) - 端口 6379

#### 3. 验证服务

```bash
# 检查容器状态
docker-compose ps

# 查看日志
docker-compose logs -f ragent-api

# 健康检查
curl http://localhost:8000/api/health
```

#### 4. 访问 API 文档

浏览器打开：http://localhost:8000/docs

### 方式 2: 单独构建和运行

#### 1. 构建镜像

```bash
docker build -t ragent-python:latest .
```

#### 2. 运行容器

```bash
docker run -d \
  --name ragent-api \
  -p 8000:8000 \
  -e DATABASE_URL=postgresql://postgres:postgres@host.docker.internal:5432/ragent \
  -e OPENAI_API_KEY=your-api-key \
  ragent-python:latest
```

## 🔧 常用命令

### 服务管理

```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看日志
docker-compose logs -f [service_name]

# 进入容器
docker-compose exec ragent-api bash
```

### 数据库管理

```bash
  # 连接数据库
docker-compose exec postgres psql -U postgres -d ragent

# 备份数据库
docker-compose exec postgres pg_dump -U postgres ragent > backup.sql

# 恢复数据库
cat backup.sql | docker-compose exec -T postgres psql -U postgres ragent

# 查看数据库大小
docker-compose exec postgres psql -U postgres -d ragent -c "SELECT pg_size_pretty(pg_database_size('ragent'));"
```

### 清理

```bash
# 停止并删除容器、网络
docker-compose down

# 同时删除数据卷（⚠️ 会丢失所有数据）
docker-compose down -v

# 删除镜像
docker rmi ragent-python:latest
```

## 📊 监控和维护

### 查看资源使用

```bash
# 查看所有容器资源使用
docker stats

# 查看特定容器
docker stats ragent-api
```

### 健康检查

```bash
# API 健康检查
curl http://localhost:8000/api/health

# 数据库健康检查
docker-compose exec postgres pg_isready

# Redis 健康检查（如果启用）
docker-compose exec redis redis-cli ping
```

### 日志管理

```bash
# 查看实时日志
docker-compose logs -f ragent-api

# 查看最近 100 行日志
docker-compose logs --tail=100 ragent-api

# 导出日志到文件
docker-compose logs ragent-api > logs.txt
```

## 🔐 安全配置

### 生产环境建议

1. **修改默认密码**

在 `docker-compose.yml` 中修改：

```yaml
environment:
  POSTGRES_PASSWORD: your-strong-password
```

2. **使用 Docker Secrets**

```yaml
secrets:
  db_password:
    file: ./secrets/db_password.txt
  api_key:
    file: ./secrets/api_key.txt

services:
  ragent-api:
    secrets:
      - api_key
```

3. **限制资源使用**

已在 `docker-compose.yml` 中配置：

```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 2G
```

4. **启用 HTTPS**

使用 Nginx 反向代理：

```yaml
nginx:
  image: nginx:alpine
  ports:
    - "443:443"
  volumes:
    - ./nginx.conf:/etc/nginx/nginx.conf
    - ./ssl:/etc/nginx/ssl
```

## 🔄 更新部署

### 更新应用代码

```bash
# 1. 拉取最新代码
git pull

# 2. 重新构建镜像
docker-compose build ragent-api

# 3. 重启服务
docker-compose up -d ragent-api

# 4. 验证
curl http://localhost:8000/api/health
```

### 数据库迁移

如果需要更新数据库结构：

```bash
# 1. 备份数据库
docker-compose exec postgres pg_dump -U postgres ragent > backup_$(date +%Y%m%d).sql

# 2. 执行迁移脚本
docker-compose exec postgres psql -U postgres -d ragent -f /path/to/migration.sql

# 3. 验证数据
docker-compose exec postgres psql -U postgres -d ragent -c "\dt"
```

## 🐛 故障排查

### 问题 1: 容器无法启动

```bash
# 查看详细日志
docker-compose logs ragent-api

# 检查配置文件
docker-compose config

# 验证镜像
docker images | grep ragent
```

### 问题 2: 数据库连接失败

```bash
# 检查 PostgreSQL 状态
docker-compose exec postgres pg_isready

# 查看 PostgreSQL 日志
docker-compose logs postgres

# 测试连接
docker-compose exec ragent-api python -c "
from database import engine
print(engine.connect())
"
```

### 问题 3: 内存不足

```bash
# 查看资源使用
docker stats

# 调整资源限制
# 编辑 docker-compose.yml 中的 deploy.resources.limits
```

### 问题 4: 端口冲突

```bash
# 查看端口占用
netstat -tuln | grep 8000

# 修改端口映射
# 编辑 docker-compose.yml:
# ports:
#   - "8001:8000"  # 将宿主机的 8001 映射到容器的 8000
```

## 📈 性能优化

### 1. 启用持久化连接池

在 `config.py` 中配置：

```python
DATABASE_URL = "postgresql://...?pool_size=20&max_overflow=40"
```

### 2. 使用 Redis 缓存

启动 Redis 服务：

```bash
docker-compose --profile optional up -d
```

### 3. 优化 Docker 镜像

- 使用多阶段构建（已实现）
- 减小镜像体积
- 利用层缓存

### 4. 日志轮转

创建 `docker-compose.override.yml`:

```yaml
services:
  ragent-api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## 🌐 生产部署示例

### Kubernetes 部署

创建 `k8s-deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ragent-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ragent-api
  template:
    metadata:
      labels:
        app: ragent-api
    spec:
      containers:
      - name: ragent-api
        image: ragent-python:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: url
---
apiVersion: v1
kind: Service
metadata:
  name: ragent-service
spec:
  selector:
    app: ragent-api
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

### Swarm 部署

```bash
# 初始化 Swarm
docker swarm init

# 部署堆栈
docker stack deploy -c docker-compose.yml ragent
```

## 📝 环境变量参考

| 变量名          | 说明             | 默认值                                              |
| --------------- | ---------------- | --------------------------------------------------- |
| DATABASE_URL    | 数据库连接字符串 | postgresql://postgres:postgres@postgres:5432/ragent |
| OPENAI_API_KEY  | LLM API 密钥     | your-api-key-here                                   |
| OPENAI_API_BASE | LLM API 地址     | https://dashscope.aliyuncs.com/compatible-mode/v1   |
| CHAT_MODEL      | 聊天模型名称     | qwen-plus                                           |
| DEBUG           | 调试模式         | false                                               |
| ALLOWED_ORIGINS | CORS 允许的源    | ["http://localhost:5173"]                           |

## 🎯 下一步

- 配置 CI/CD 自动化部署
- 设置监控告警（Prometheus + Grafana）
- 实现蓝绿部署或滚动更新
- 添加负载均衡器

## 📞 需要帮助？

- 查看项目文档：README.md
- 查看 API 文档：http://localhost:8000/docs
- 提交 Issue：GitHub Issues
