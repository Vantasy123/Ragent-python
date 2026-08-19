# 🔌 Ragent MCP 服务接入与架构拆分指南

为了实现高内聚、低耦合与系统稳定性，Ragent 将 **用户求职业务 API** 与 **Agent 专属 MCP 服务** 彻底拆分为两个独立的微服务：

---

## 🏗️ 双服务微服务拆分架构

```mermaid
graph TD
    User[求职者 & 管理员] -->|HTTP:80| Frontend[Ragent Web 前端 (Nginx)]
    
    subgraph 服务 A: 主业务应用服务 (Port 8000)
        Frontend -->|REST API| CoreAPI[Ragent Core API<br/>app.main:app<br/>对话 / 简历 / 面试 / 投递看板 / 审计]
        CoreAPI --> DB[(MySQL / Milvus / Redis)]
    end

    subgraph 服务 B: 独立 MCP API 服务 (Port 8001)
        ExternalAgents[外部 AI Agent<br/>Claude Code / Cursor / Codex / Cline] -->|SSE 协议: GET /mcp/sse<br/>JSON-RPC: POST /mcp/jsonrpc<br/>REST: POST /mcp/tools/:name/invoke| McpAPI[Ragent Standalone MCP API<br/>app.mcp_main:app]
        McpAPI --> DB
    end
```

### 为什么进行微服务拆分？
1. **故障与性能隔离**：外部 Agent 进行高频岗位抓取、大批量 RAG 语义检索或长耗时计算时，运行在独立端口 `8001`，**完全不会占用或阻塞主业务系统 `8000` 端口的用户界面与交互**；
2. **独立扩缩容与部署**：在 `docker-compose.yml` 中被定义为独立的 `ragent-mcp-api` 容器，可按需单独重启、更新与监控；
3. **同时支持远程 SSE 与本地 stdio**：外部 Agent 既可通过网络直接连接 `http://localhost:8001/mcp/sse`，也可在本地通过 `python -m app.mcp_server` stdio 管道运行。

---

## 🌟 4 大不可替代的 MCP 专有工具

| 工具名称 | 核心职责 |
| :--- | :--- |
| **`ragent_sync_and_search_jobs`** | 实时多招聘平台（BOSS直聘/猎聘/51job/牛客网）岗位采集、薪资规范化与本地检索 |
| **`ragent_query_interview_rag`** | 本地 Milvus 八股面经与大厂真题知识库向量与语义混合检索 |
| **`ragent_manage_resume_profile`** | 读写持久化求职者结构化简历档案、STAR 项目经历与岗位定制版本 |
| **`ragent_export_autofill_payload`** | 生成对齐「牛客网申助手」/ Moka / 北森的标准填表 Payload 并加入看板 |

---

## 🚀 外部 Agent 接入方式

### 方式 1：通过 SSE (Server-Sent Events) 远程网络接入（推荐）
当 MCP 独立服务运行在 `8001` 端口时，任何外部 Agent（甚至在局域网其它机器或云端）均可通过标准 SSE 接入：

在 `.mcp.json` 或 Agent 设置中：
```json
{
  "mcpServers": {
    "ragent-career-hub": {
      "url": "http://localhost:8001/mcp/sse"
    }
  }
}
```

### 方式 2：通过 stdio 管道本地按需调起
```json
{
  "mcpServers": {
    "ragent-career-hub": {
      "command": "python",
      "args": ["-m", "app.mcp_server"],
      "env": {
        "PYTHONPATH": "."
      }
    }
  }
}
```

### 方式 3：直接通过 REST API 跨语言调用
- **健康检查**：`GET http://localhost:8001/health`
- **查看所有工具**：`GET http://localhost:8001/mcp/tools`
- **直接调用工具**：
  ```http
  POST http://localhost:8001/mcp/tools/ragent_manage_resume_profile/invoke
  Content-Type: application/json

  {
    "action": "get_active"
  }
  ```

---

## 🧪 启动与验证命令

### 本地启动独立 MCP API 服务：
```bash
uvicorn app.mcp_main:app --host 0.0.0.0 --port 8001 --reload
```

### 运行全量测试套件：
```bash
python -m pytest tests/test_mcp_api_service.py tests/test_mcp_server.py -v
```
