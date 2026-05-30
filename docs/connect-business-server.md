# 接入业务服务器

Ragent 的运维平台按三层接入业务服务器：健康检查、指标、告警。

## 健康检查

最小接入只需要业务服务提供一个 HTTP 健康接口，例如：

```text
GET /health
```

然后在 `config/servers.yml` 中配置：

```yaml
servers:
  - id: payment-service
    name: 支付服务
    env: prod
    enabled: true
    base_url: http://payment-service:8080
    health_url: http://payment-service:8080/health
    metrics_url: http://payment-service:8080/metrics
    owner: 支付团队
    tags:
      - payment
      - critical
```

后端会把启用的 `health_url` 自动加入 `/api/admin/monitoring/probes`。

如果不想手写 YAML，可以调用后台配置 API：

```http
PUT /api/admin/project-config/servers
Content-Type: application/json

{
  "servers": [
    {
      "id": "payment-service",
      "name": "支付服务",
      "env": "prod",
      "enabled": true,
      "base_url": "http://payment-service:8080",
      "health_url": "http://payment-service:8080/health",
      "metrics_url": "http://payment-service:8080/metrics",
      "owner": "支付团队",
      "tags": ["payment", "critical"]
    }
  ]
}
```

正式保存前可以先测试连通性：

```http
POST /api/admin/project-config/probe-test
Content-Type: application/json

{
  "name": "支付服务",
  "url": "http://payment-service:8080/health"
}
```

## 指标

推荐业务应用暴露 Prometheus 格式指标：

```text
GET /metrics
```

常见指标包括：

- 请求量：`http_requests_total`
- 错误量：`http_requests_total{status=~"5.."}`
- 延迟：`http_request_duration_seconds_bucket`
- 业务队列积压：`queue_pending_total`
- 数据库连接池：`db_pool_active`

## 告警

告警仍由 Prometheus 规则和 Alertmanager 管理。Ragent 后台只读取 Alertmanager API 展示当前告警，不直接替代告警系统。

## 配置原则

- 开源用户只改 `.env` 和 `config/*.yml`。
- 不要把真实 API Key、内网地址和密码提交到仓库。
- 生产环境建议把 Prometheus、Alertmanager、Grafana 的账号密码改成强密码。
