"""Ragent 独立 MCP (Model Context Protocol) API 服务。

独立运行在 8001 端口，与 8000 端口的主业务 API 解耦。
全面支持「渐进式发现 (Progressive Discovery)」架构：
1. 标准 SSE (Server-Sent Events) 远程 MCP 协议 (`GET /mcp/sse`, `POST /mcp/messages`)；
2. HTTP JSON-RPC 2.0 协议 (`POST /mcp/jsonrpc`)；
3. 渐进式能力发现 REST 端点 (`GET /mcp/capabilities`, `GET /mcp/capabilities/{name}`)；
4. RESTful 工具调用接口 (`GET /mcp/tools`, `POST /mcp/tools/{tool_name}/invoke`)；
5. 资源与 Prompt 模板端点 (`GET /mcp/resources`, `GET /mcp/prompts`)；
6. 健康检查与状态监控 (`GET /health`)。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.mcp_server import (
    MCP_TOOLS_DEFINITIONS,
    MCP_RESOURCES_DEFINITIONS,
    MCP_PROMPTS_DEFINITIONS,
    RAGENT_CAPABILITIES_CATALOG,
    RagentMcpServer,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [Ragent-MCP-API] - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ragent-mcp-api")

app = FastAPI(
    title="Ragent Standalone MCP API Service",
    description="Ragent 专属求职与岗位数据 MCP 微服务（端口 8001），提供 Progressive Discovery 渐进式发现、SSE 与 RESTful 接口供外部 Agent 调用",
    version="1.1.0"
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
MCP_SERVER_VERSION = "1.1.0"


def _jsonrpc_error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _prompt_message(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    prompts = {prompt["name"]: prompt for prompt in MCP_PROMPTS_DEFINITIONS}
    prompt = prompts.get(name)
    if not prompt:
        raise ValueError(f"Prompt '{name}' not found")
    missing = [arg["name"] for arg in prompt.get("arguments", []) if arg.get("required") and not arguments.get(arg["name"])]
    if missing:
        raise ValueError(f"Missing required prompt arguments: {', '.join(missing)}")
    supplied = "\n".join(f"{key}: {value}" for key, value in arguments.items())
    return {
        "description": prompt["description"],
        "messages": [{
            "role": "user",
            "content": {"type": "text", "text": f"{prompt['description']}\n{supplied}".strip()},
        }],
    }


def _dispatch_jsonrpc(body: Any) -> Optional[Dict[str, Any]]:
    """统一分发 HTTP 与 SSE 的 JSON-RPC 请求；通知不生成响应。"""
    if not isinstance(body, dict):
        return _jsonrpc_error(None, -32600, "Invalid Request")
    request_id = body.get("id")
    is_notification = "id" not in body
    method = body.get("method")
    params = body.get("params", {})
    if not isinstance(method, str) or not isinstance(params, dict):
        return None if is_notification else _jsonrpc_error(request_id, -32600, "Invalid Request")

    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                "serverInfo": {"name": "ragent-mcp-server", "version": MCP_SERVER_VERSION},
            }
        elif method == "tools/list":
            result = {"tools": MCP_TOOLS_DEFINITIONS}
        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            if not isinstance(tool_name, str) or not isinstance(tool_args, dict):
                return None if is_notification else _jsonrpc_error(request_id, -32602, "Invalid tool parameters")
            output = _server_instance.handle_tool_call(tool_name, tool_args)
            result = {
                "content": [{"type": "text", "text": json.dumps(output, ensure_ascii=False, indent=2)}],
                "isError": output.get("status") in {"error", "failed"},
            }
        elif method == "resources/list":
            result = {"resources": MCP_RESOURCES_DEFINITIONS}
        elif method == "resources/read":
            uri = params.get("uri")
            if not isinstance(uri, str):
                return None if is_notification else _jsonrpc_error(request_id, -32602, "Resource URI is required")
            content = _server_instance.handle_resource_read(uri)
            if content.get("status") in {"error", "failed"} or content.get("error"):
                return None if is_notification else _jsonrpc_error(request_id, -32002, content.get("error", "Resource not found"))
            result = {"contents": [content]}
        elif method == "prompts/list":
            result = {"prompts": MCP_PROMPTS_DEFINITIONS}
        elif method == "prompts/get":
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return None if is_notification else _jsonrpc_error(request_id, -32602, "Invalid prompt parameters")
            result = _prompt_message(name, arguments)
        elif method == "ping":
            result = {}
        elif method == "notifications/initialized":
            return None
        else:
            return None if is_notification else _jsonrpc_error(request_id, -32601, f"Method '{method}' not found")
    except ValueError as exc:
        return None if is_notification else _jsonrpc_error(request_id, -32602, str(exc))
    except Exception as exc:
        logger.exception("MCP JSON-RPC dispatch failed: %s", exc)
        return None if is_notification else _jsonrpc_error(request_id, -32603, "Internal error")

    return None if is_notification else {"jsonrpc": "2.0", "id": request_id, "result": result}


@app.get("/health")
def health_check():
    """MCP 服务健康检查端点。"""
    return {
        "status": "healthy",
        "service": "ragent-mcp-api",
        "version": "1.1.0",
        "protocol": "Progressive-Discovery-v1",
        "port": 8001,
        "capabilities_count": len(RAGENT_CAPABILITIES_CATALOG),
        "tools_count": len(MCP_TOOLS_DEFINITIONS)
    }


# =====================================================================
# 渐进式发现 REST 接口 (Progressive Discovery REST API)
# =====================================================================

@app.get("/mcp/capabilities")
def list_capabilities(category: str = "all"):
    """【渐进式发现-Layer 1】全景列出系统拥有的能力域、推荐流程与资源清单。"""
    if category == "all":
        caps = list(RAGENT_CAPABILITIES_CATALOG.values())
    else:
        target = RAGENT_CAPABILITIES_CATALOG.get(category)
        caps = [target] if target else []

    return {
        "status": "success",
        "protocol": "Progressive-Discovery-v1",
        "total": len(caps),
        "capabilities": caps,
        "resources": [r["uri"] for r in MCP_RESOURCES_DEFINITIONS],
        "prompts": [p["name"] for p in MCP_PROMPTS_DEFINITIONS]
    }


@app.get("/mcp/capabilities/{capability_name}")
def inspect_capability(capability_name: str):
    """【渐进式发现-Layer 2】按需获取指定能力域的完整 Schema、参数说明与调用示例。"""
    if capability_name not in RAGENT_CAPABILITIES_CATALOG:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability '{capability_name}' not found. Available: {list(RAGENT_CAPABILITIES_CATALOG.keys())}"
        )

    cap_info = RAGENT_CAPABILITIES_CATALOG[capability_name]
    tool_def = next((t for t in MCP_TOOLS_DEFINITIONS if t["name"] == cap_info["tool_name"]), None)

    return {
        "status": "success",
        "capability": cap_info,
        "underlying_tool": tool_def
    }


@app.get("/mcp/resources")
def list_resources():
    """列出当前 MCP 服务暴露的所有动态资源。"""
    return {
        "status": "success",
        "total": len(MCP_RESOURCES_DEFINITIONS),
        "resources": MCP_RESOURCES_DEFINITIONS
    }


@app.get("/mcp/prompts")
def list_prompts():
    """列出当前 MCP 服务暴露的 Prompt 模板。"""
    return {
        "status": "success",
        "total": len(MCP_PROMPTS_DEFINITIONS),
        "prompts": MCP_PROMPTS_DEFINITIONS
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
        return JSONResponse(content=_jsonrpc_error(None, -32700, "Parse error"), status_code=status.HTTP_400_BAD_REQUEST)

    response = _dispatch_jsonrpc(body)
    if response is None:
        return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)
    return JSONResponse(content=response)


# =====================================================================
# Server-Sent Events (SSE) 协议端点
# =====================================================================

@app.get("/mcp/sse")
async def mcp_sse_endpoint(request: Request):
    """标准 MCP Server-Sent Events (SSE) 协议端点。"""
    session_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _active_sse_clients[session_id] = queue

    logger.info(f"New MCP SSE client connected. Session ID: {session_id}")

    async def event_generator():
        endpoint_event = f"event: endpoint\ndata: /mcp/messages?sessionId={session_id}\n\n"
        yield endpoint_event

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: message\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
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
        return JSONResponse(content=_jsonrpc_error(None, -32700, "Parse error"), status_code=status.HTTP_400_BAD_REQUEST)

    response = _dispatch_jsonrpc(body)
    if response is not None:
        queue = _active_sse_clients[sessionId]
        try:
            queue.put_nowait(response)
        except asyncio.QueueFull:
            logger.warning("MCP SSE client queue full; dropping response for session %s", sessionId)
            return JSONResponse(content={"status": "backpressure"}, status_code=status.HTTP_429_TOO_MANY_REQUESTS)
    return JSONResponse(content={"status": "accepted"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
