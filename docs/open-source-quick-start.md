# 开源部署快速开始

目标是让使用者下载项目后只改配置，不改源码，就能接入自己的模型、业务服务器和监控系统。

## 1. 准备配置

```bash
cp .env.example .env
cp config/servers.example.yml config/servers.yml
cp config/monitoring.example.yml config/monitoring.yml
```

如果直接运行启动脚本，脚本会在这些文件缺失时自动从示例生成。

必须修改：

- `.env` 中的 `OPENAI_API_KEY`、`OPENAI_API_BASE`、`CHAT_MODEL`
- `.env` 中的 `JWT_SECRET`、`DEFAULT_ADMIN_PASSWORD`
- `config/servers.yml` 中的业务服务器地址
- `config/monitoring.yml` 中的 Prometheus / Alertmanager 地址

## 2. 启动

Windows：

```powershell
scripts\start-project.bat monitoring -Build
```

Linux / macOS：

```bash
bash scripts/start-project.sh monitoring --build
```

最小后端模式：

```bash
bash scripts/start-project.sh monitoring-backend --build
```

## 3. 接入业务服务器

在 `config/servers.yml` 中添加业务服务：

```yaml
servers:
  - id: order-service
    name: 订单服务
    env: prod
    enabled: true
    base_url: http://order-service:8080
    health_url: http://order-service:8080/health
    metrics_url: http://order-service:8080/metrics
    owner: 交易团队
    tags:
      - order
      - core
```

保存后重启 `ragent-api`，后台“运维监控”会把该服务作为 HTTP 探测目标展示。

```bash
docker compose -f docker-compose.yml -f docker-compose.ops.yml -f docker-compose.monitoring.yml restart ragent-api
```

也可以通过后台配置 API 读写配置，供初始化向导或前端页面使用：

```text
GET /api/admin/project-config/status
GET /api/admin/project-config/servers
PUT /api/admin/project-config/servers
GET /api/admin/project-config/monitoring
PUT /api/admin/project-config/monitoring
POST /api/admin/project-config/probe-test
```

这些接口都会写入 `config/*.yml`，不改源码。

## 4. 接入 Prometheus 指标

如果业务应用已经暴露 `/metrics`，可以把 scrape 目标写入 `monitoring/prometheus/prometheus.yml`。第一版保持显式配置，避免后台自动改写用户监控文件。

```yaml
scrape_configs:
  - job_name: order-service
    metrics_path: /metrics
    static_configs:
      - targets:
          - order-service:8080
```

## 5. 常见地址

- 前端后台：http://localhost/
- 后端文档：http://localhost:8000/docs
- Prometheus：http://localhost:9090/
- Alertmanager：http://localhost:9093/
- Grafana：http://localhost:3001/，默认账号 `admin/admin`
