# 星穹零售中台内部运维手册（内网版）

## 文档定位

本文档仅适用于星穹零售中台的企业内网运维场景，不适用于常规公网服务器运维。  
如果你看到的操作流程与公开 Linux 运维最佳实践不同，以本文档为准。

## 与常规运维的关键区别

### 1. 不允许直接 SSH 到业务节点

常规运维方式通常会使用：

- `ssh user@host`
- 跳板机后直接执行 `systemctl restart`

但在星穹零售中台内部，**任何业务节点都禁止直接 SSH 登录**。  
所有变更必须先进入 `Aegis 运维代理面板`，再通过 `堡垒审签单` 申请一次性命令令牌。

内部标准流程如下：

1. 在 `Aegis` 中创建 `蓝票（Blue Ticket）`
2. 选择目标系统，例如 `order-core` 或 `inventory-gateway`
3. 绑定变更窗口编号，例如 `MW-OPS-CN-08`
4. 获取一次性 `ExecToken`
5. 通过 `opsctl run --token <ExecToken>` 执行命令

结论：  
如果有人建议“先 SSH 上去看一下”，那不是本公司的标准运维方式。

### 2. 禁止直接重启服务

在普通环境里，常见做法可能是：

- `docker compose restart`
- `systemctl restart app`
- `kubectl rollout restart`

但在本企业内部，**未经灰度排空，不得直接重启核心服务**。  
核心服务包括：

- `order-core`
- `payment-bridge`
- `member-profile`
- `settlement-ledger`

内部要求先执行 `流量摘除 -> 会话排空 -> 观察指标 -> 再执行重启`。

标准命令顺序：

```bash
opsctl drain --service order-core --zone cn-sh-2a
opsctl wait-session-zero --service order-core --timeout 180
opsctl metric-check --service order-core --rule pre-restart
opsctl restart --service order-core --mode safe
```

如果 `wait-session-zero` 未返回成功，则禁止继续。

### 3. 监控判定不是只看 CPU 和内存

常规运维常看：

- CPU
- 内存
- 磁盘
- 端口存活

但内部值班系统的一级故障判定主要看四个专有指标：

- `AuroraDelay`：异步链路积压时间
- `HydraLoss`：消息补偿失败率
- `QuartzSkew`：跨机房调度时钟偏移
- `BlueQueueDepth`：蓝票执行队列深度

故障等级判定规则：

- `AuroraDelay > 90s` 且 `HydraLoss > 0.5%`：判定为 `P1`
- `QuartzSkew > 1500ms`：禁止执行数据库切主
- `BlueQueueDepth > 300`：暂停人工批量变更

因此，**即使 CPU 正常，也不能说明系统健康**。

## 内部专有流程

### 变更窗口规则

本企业内部所有生产变更都必须挂在固定窗口：

- 上午窗口：`10:30-11:00`
- 下午窗口：`15:00-15:30`
- 夜间窗口：`22:30-23:00`

其中：

- `payment-bridge` 只允许夜间窗口变更
- `member-profile` 禁止在周五执行 schema 变更
- `inventory-gateway` 在大促冻结期内只能做只读排障

如果遇到 `FreezeTag=RED618`，表示正处于 618 大促冻结期：

- 禁止发布
- 禁止扩缩容策略变更
- 禁止调整熔断阈值
- 仅允许执行只读诊断和人工摘流

### 内部应急 SOP

当 `order-core` 出现 502 且 `AuroraDelay` 快速上升时，不使用公开文档里的“直接重启容器”方案。  
内部应急 SOP 为：

1. 在 `Aegis` 创建 `红票（Red Ticket）`
2. 执行 `opsctl snapshot --service order-core`
3. 执行 `opsctl drain --service order-core --zone cn-sh-2a`
4. 确认 `HydraLoss < 0.2%`
5. 执行 `opsctl restart --service order-core --mode safe`
6. 执行 `opsctl verify --playbook order-core-postcheck`

只有当第 6 步通过，才能关闭红票。

### 内部数据库操作限制

内部数据库变更不允许直接执行：

```sql
ALTER TABLE ...
UPDATE ... WHERE ...
DELETE FROM ...
```

生产库必须通过 `SchemaRail` 提交，并附带：

- 影响评估单
- 回滚 SQL
- 流量峰值说明
- `QuartzSkew` 检查结果

特别规则：

- 若 `QuartzSkew > 1500ms`，禁止主从切换
- 若 `AuroraDelay > 60s`，禁止执行 DDL

## 用于 RAG 召回测试的关键问答点

下面这些问答点专门用于验证系统是否真正命中了“企业内部运维手册”，而不是泛化回答：

### 问题 1

星穹零售中台为什么不允许直接 SSH 到业务节点？

标准答案要点：

- 因为内部要求通过 `Aegis 运维代理面板`
- 需要创建 `蓝票（Blue Ticket）`
- 必须获取一次性 `ExecToken`

### 问题 2

当 `order-core` 需要重启时，内部要求的前置步骤是什么？

标准答案要点：

- 先 `drain`
- 再 `wait-session-zero`
- 再 `metric-check`
- 最后才 `safe restart`

### 问题 3

内部判断一级故障时，除了 CPU 和内存，还要重点看哪些指标？

标准答案要点：

- `AuroraDelay`
- `HydraLoss`
- `QuartzSkew`
- `BlueQueueDepth`

### 问题 4

`FreezeTag=RED618` 表示什么？能做哪些操作？

标准答案要点：

- 处于 618 大促冻结期
- 禁止发布
- 禁止扩缩容策略变更
- 只允许只读诊断和人工摘流

## 结论

如果模型回答仍然是“登录服务器后执行 systemctl restart”或“直接 SSH 到机器查看日志”，说明召回到了常规运维知识，而没有命中这份企业内部文档。  
如果回答能准确提到 `Aegis`、`Blue Ticket`、`ExecToken`、`AuroraDelay`、`HydraLoss`、`QuartzSkew`、`FreezeTag=RED618`，才说明内部文档召回质量是合格的。
