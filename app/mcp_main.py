"""Ragent 独立 MCP (Model Context Protocol) API 服务。

独立运行在 8001 端口，与 8000 端口的主业务 API 解耦。
支持：
1. 标准 SSE (Server-Sent Events) 远程 MCP 协议 (`GET /mcp/sse`, `POST /mcp/messages`)；
2. HTTP JSON-RPC 2.0 协议 (`POST /mcp/jsonrpc`)；
3. RESTful 工具调用接口 (`GET /mcp/tools`, `POST /mcp/tools/{tool_name}/invoke`)；
4. 健康检查与状态监控 (`GET /health`)。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.mcp_server import MCP_TOOLS_DEFINITIONS, RagentMcpServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [Ragent-MCP-API] - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ragent-mcp-api")

app = FastAPI(
    title="Ragent Standalone MCP API Service",
    description="Ragent 专属求职与岗位数据 MCP 微服务（端口 8001），提供 SSE 与 RESTful 接口供外部 Agent 调用",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 活跃的 SSE 客户端会话队列字典
_active_sse_clients: Dict[str, asyncio.Queue] = {}
_server_instance = RagentMcpServer()


@app.get("/health")
def health_check():
    """MCP 服务健康检查端点。"""
    return {
        "status": "healthy",
        "service": "ragent-mcp-api",
        "version": "1.0.0",
        "port": 8001,
        "tools_count": len(MCP_TOOLS_DEFINITIONS)
    }


@app.get("/mcp/tools")
def list_mcp_tools():
    """REST API: 列出当前 MCP 服务暴露的所有专有工具。"""
    return {
        "status": "success",
        "total": len(MCP_TOOLS_DEFINITIONS),
        "tools": MCP_TOOLS_DEFINITIONS
    }


@app.post("/mcp/tools/{tool_name}/invoke")
def invoke_mcp_tool(tool_name: str, payload: Dict[str, Any]):
    """REST API: 通过 HTTP 直接调用指定 MCP 工具。"""
    valid_names = {t["name"] for t in MCP_TOOLS_DEFINITIONS}
    if tool_name not in valid_names:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_name}' not found. Available: {list(valid_names)}"
        )

    result = _server_instance.handle_tool_call(tool_name, payload)
    return result


@app.post("/mcp/jsonrpc")
async def handle_jsonrpc(request: Request):
    """HTTP JSON-RPC 2.0 端点。"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    req_id = body.get("id")
    method = body.get("method")
    params = body.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ragent-mcp-server", "version": "1.0.0"}
            }
        }
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": MCP_TOOLS_DEFINITIONS}
        }
    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        res = _server_instance.handle_tool_call(tool_name, tool_args)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False, indent=2)}],
                "isError": res.get("status") == "error"
            }
        }
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method '{method}' not found"}
        }


@app.get("/mcp/sse")
async def mcp_sse_endpoint(request: Request):
    """标准 MCP Server-Sent Events (SSE) 协议端点。"""
    session_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _active_sse_clients[session_id] = queue

    logger.info(f"New MCP SSE client connected. Session ID: {session_id}")

    async def event_generator():
        # 1. 建立连接并告知客户端消息回传端点
        endpoint_event = f"event: endpoint\ndata: /mcp/messages?sessionId={session_id}\n\n"
        yield endpoint_event

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # 等待队列中的消息
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: message\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # 心跳 ping 保持连接活跃
                    yield ": ping\n\n"
        finally:
            _active_sse_clients.pop(session_id, None)
            logger.info(f"MCP SSE client disconnected. Session ID: {session_id}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/mcp/messages")
async def mcp_messages_endpoint(request: Request, sessionId: Optional[str] = None):
    """处理来自 SSE 客户端的上行 JSON-RPC 消息。"""
    if not sessionId or sessionId not in _active_sse_clients:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session ID not found or expired"
        )

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    req_id = body.get("id")
    method = body.get("method")
    params = body.get("params", {})
    queue = _active_sse_clients[sessionId]

    if method == "initialize":
        res = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ragent-mcp-server", "version": "1.0.0"}
            }
        }
        await queue.put(res)
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        res = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": MCP_TOOLS_DEFINITIONS}
        }
        await queue.put(res)
    elif method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        tool_res = _server_instance.handle_tool_call(tool_name, tool_args)
        res = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(tool_res, ensure_ascii=False, indent=2)}],
                "isError": tool_res.get("status") == "error"
            }
        }
        await queue.put(res)
    elif method == "ping":
        await queue.put({"jsonrpc": "2.0", "id": req_id, "result": {}})
    else:
        await queue.put({
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method '{method}' not found"}
        })

    return Response(status_code=status.HTTP_202_ACCEPTED)
