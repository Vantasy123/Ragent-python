"""MCP HTTP JSON-RPC 协议行为测试。"""

from fastapi.testclient import TestClient

from app.mcp_main import app


client = TestClient(app)


def test_jsonrpc_rejects_non_object_request():
    response = client.post("/mcp/jsonrpc", json=[])

    assert response.status_code == 200
    payload = response.json()
    assert payload["error"]["code"] == -32600


def test_jsonrpc_notification_has_no_response():
    response = client.post(
        "/mcp/jsonrpc",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )

    assert response.status_code == 204


def test_jsonrpc_prompt_get_returns_rendered_prompt():
    response = client.post(
        "/mcp/jsonrpc",
        json={
            "jsonrpc": "2.0",
            "id": "prompt-1",
            "method": "prompts/get",
            "params": {
                "name": "tailor_resume_for_job",
                "arguments": {"job_title": "后端工程师", "job_requirements": "Python、FastAPI"},
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "prompt-1"
    assert "messages" in payload["result"]
    assert "后端工程师" in payload["result"]["messages"][0]["content"]["text"]


def test_jsonrpc_rejects_null_tool_params():
    response = client.post(
        "/mcp/jsonrpc",
        json={"jsonrpc": "2.0", "id": "invalid-params", "method": "tools/call", "params": None},
    )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32600
