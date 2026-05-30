# Antigravity 前端交接：运维监控看板

## 页面目标

在后台新增“运维监控”页，对接 Codex 已提供的 `/api/admin/monitoring` 接口，展示系统健康、核心指标、活跃告警、采集目标、HTTP 探测和受控 PromQL 查询。

## 接口清单

所有接口都需要管理员登录态，响应外层格式沿用项目现有结构：

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

### 1. 监控总览

- 方法：`GET`
- 地址：`/api/admin/monitoring/overview`
- 用途：页面首屏总览卡片和主要列表。

关键字段：

| 字段 | 中文名 | 说明 |
| --- | --- | --- |
| `status` | 运行状态 | `healthy` / `degraded` / `critical` |
| `summary` | 状态摘要 | 中文摘要 |
| `updatedAt` | 最近更新时间 | ISO 时间字符串 |
| `cards` | 总览卡片 | CPU、内存、告警、服务健康 |
| `services` | 服务探测 | API、前端、Nginx 代理、测试服务 |
| `targets` | 采集目标 | Prometheus targets |
| `alerts` | 活跃告警 | Alertmanager 告警摘要 |
| `issues` | 降级原因 | 监控源不可用时展示 |

### 2. 采集目标

- 方法：`GET`
- 地址：`/api/admin/monitoring/targets`
- 用途：展示 Prometheus targets 表格。

表格字段建议：`job`（任务）、`instance`（实例）、`statusLabel`（运行状态）、`lastScrape`（最近采集时间）、`lastError`（最近错误）。

### 3. 活跃告警

- 方法：`GET`
- 地址：`/api/admin/monitoring/alerts`
- 用途：展示当前活跃告警。

表格字段建议：`displayName`（告警名称）、`severityLabel`（告警等级）、`summary`（告警摘要）、`startsAt`（开始时间）。

### 4. 指标趋势

- 方法：`GET`
- 地址：`/api/admin/monitoring/series/{metric}?minutes=30`
- 可用 `metric`：`cpu_percent`、`memory_percent`、`container_cpu`、`container_memory`、`redis_up`、`mysql_up`、`probe_success`。
- 用途：折线图。

返回 `data.points`，每个点包含 `timestamp` 和 `value`。

### 5. 服务探测

- 方法：`GET`
- 地址：`/api/admin/monitoring/probes`
- 用途：服务健康表。

字段建议：`displayName`（服务名称）、`statusLabel`（运行状态）、`statusCode`（状态码）、`durationMs`（响应时间）、`message`（探测结果）。

### 6. PromQL 调试

- 方法：`POST`
- 地址：`/api/admin/monitoring/query`
- 请求体：

```json
{
  "query": "up",
  "time": null
}
```

后端会做只读白名单校验。非法或过宽查询返回 `data.status = "degraded"`，页面应展示中文 `summary`，不要当作系统错误。

## 中文字段固定文案

页面内字段名统一使用：

- 服务名称
- 运行状态
- CPU 使用率
- 内存使用率
- 活跃告警
- 响应时间
- 最近更新时间
- 采集目标
- 告警等级
- 告警摘要
- PromQL 查询
- 降级原因

状态标签：

| 内部值 | 中文标签 | 视觉建议 |
| --- | --- | --- |
| `healthy` | 正常 | 绿色 |
| `degraded` | 降级 | 黄色 |
| `critical` | 异常 | 红色 |

## 页面结构建议

1. 顶部四个总览卡片：服务健康、活跃告警、CPU 使用率、内存使用率。
2. 中部双栏：左侧指标趋势，右侧活跃告警。
3. 下部两个表格：服务探测、Prometheus 采集目标。
4. 管理员工具区：PromQL 调试输入框和结果 JSON 预览。

## 错误态和移动端要求

- 监控未启用或 Prometheus 不可达时，页面展示“降级原因”，不要空白。
- 所有数值按两位小数展示，时间使用本地时区格式化。
- 移动端表格改为纵向卡片，中文字段不得溢出。
- PromQL 调试区默认折叠，避免普通巡检时占用首屏。
