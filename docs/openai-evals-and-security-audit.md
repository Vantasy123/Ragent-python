# OpenAI Evals 与安全审计部署与配置指南

本指南介绍如何在 Ragent 项目中启用并配置 **LangSmith 链路追踪与评估反馈**、**OpenAI Evals 外部复评自动化** 以及 **安全审计中心**。

---

## 1. LangSmith 深度整合与评估反馈

### 1.1 核心机制
- **链路追踪 (Tracing)**：开启后，系统在通过 `stream_chat` 执行问答时会通过 `collect_runs()` 自动捕捉 LangChain 生成的 Root Run ID。
- **数据集增量同步**：执行离线评估时，本地的 `EvaluationDataset` 和 `EvaluationCase` 将自动增量同步到 LangSmith 云端（防止重复上传）。
- **指标反馈回传 (Feedback)**：评估完成后，本地计算出的检索命中率、检索召回率、MRR、回答忠实度、回答相关度、执行成功率、工具有效性等指标将作为 Feedback 自动回传挂载至 LangSmith 对应的 Run。

### 1.2 环境变量配置
在 `.env` 文件中配置以下参数以启用 LangSmith 整合：
```bash
# 启用 LangChain 链路追踪
LANGCHAIN_TRACING_V2=true
# 您的 LangSmith API 密钥
LANGCHAIN_API_KEY=lsv2_pt_...
# 追踪的项目名称
LANGCHAIN_PROJECT=ragent-python
# LangSmith 服务端点（国内或私有部署可修改）
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

---

## 2. OpenAI Evals 外部自动化复评

### 2.1 核心机制
- **本地复评**：离线批量评估运行完毕后，若开启了 OpenAI Evals 开关，后台线程会自动调用 OpenAI Evals API 创建远程测试集并触发复评运行。
- **自动轮询**：系统在后台以 3 秒间隔自动轮询复评状态，直到其变更为 `completed`（或失败），并将远程评测报告（包含报告 URL、各模型 Token 使用情况、各项指标结果等）回写到本地批次，无需前端人工点击同步。

### 2.2 环境变量配置
在 `.env` 文件中配置以下参数：
```bash
# 启用 OpenAI Evals
OPENAI_EVALS_ENABLED=true
# 专属 OpenAI API 密钥（留空时默认复用主 OPENAI_API_KEY）
OPENAI_EVALS_API_KEY=sk-proj-...
# OpenAI API 基础端点
OPENAI_EVALS_API_BASE=https://api.openai.com/v1
# 裁判打分模型（推荐使用 o3-mini 或 gpt-4o 等支持复杂裁判逻辑的模型）
OPENAI_EVALS_GRADER_MODEL=o3-mini
# 请求超时秒数
OPENAI_EVALS_TIMEOUT_SECONDS=30
```

---

## 3. 安全审计中心

### 3.1 核心机制
- **安全事件追踪**：对后台敏感操作进行全面审计。目前审计日志记录于 `security_audit_log` 数据库表中。
- **审计事件分类**：包含 `export` (数据导出)、`access` (配置与权限访问)、`security` (安全合规事件) 等领域。
- **安全合规**：所有审计记录包含操作人 ID、操作类型、时间戳以及操作详细信息快照（对敏感 Token 及密码信息自动打码脱敏）。
- **支持导出**：支持管理员在后台一键导出安全审计日志为规范的 CSV 文件。

### 3.2 权限控制
- 所有的安全审计 API 端点（`/api/admin/security-audit/*`）均严格要求 `require_admin` 权限，确保非管理员无法查看或篡改审计记录。

---

## 4. 常见问题与运维

### 4.1 离线测试集不触发 LangSmith 同步
请检查 `.env` 文件中的 `LANGCHAIN_TRACING_V2` 是否设为 `true` 且 `LANGCHAIN_API_KEY` 是否配置正确。系统具有**可空保护**，如果配置不完整，评估流程会自动降级跳过 LangSmith 同步，而不会导致本地评估中断。

### 4.2 OpenAI Evals 出现 401 报错
通常是因为 `OPENAI_EVALS_API_KEY` 未配置或配置的密钥无权调用相应的 API（例如在使用代理网关或专用 OpenAI 中转时，需要正确配置 `OPENAI_EVALS_API_BASE`）。
