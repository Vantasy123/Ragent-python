"""Ragent 独立 MCP API 服务（FastAPI 8001 端口）测试。"""

from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.domain.models import Base, ResumeProfile
from app.mcp_main import app


@pytest.fixture
def client_with_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    init_session = TestingSessionLocal()
    resume = ResumeProfile(
        user_id="test_mcp_user",
        name="李四",
        target_role="Go架构师",
        score=95,
        is_default=True,
        parsed_data={
            "basic_info": {"name": "李四", "phone": "13900139000", "email": "lisi@example.com"},
            "educations": [{"school": "浙江大学", "major": "软件工程", "degree": "学士"}],
            "work_experiences": [],
            "project_experiences": [{"project_name": "分布式网关", "role": "架构师", "star_highlights": "亿级流量保障"}]
        }
    )
    init_session.add(resume)
    init_session.commit()
    init_session.close()

    monkeypatch.setattr("app.mcp_server.SessionLocal", TestingSessionLocal)
    client = TestClient(app)
    return client


def test_mcp_api_health(client_with_db):
    """测试 MCP 独立服务健康检查。"""
    resp = client_with_db.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "ragent-mcp-api"
    assert data["port"] == 8001
    assert data["tools_count"] == 4


def test_mcp_api_list_tools(client_with_db):
    """测试 REST API 获取 MCP 工具列表。"""
    resp = client_with_db.get("/mcp/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["total"] == 4
    names = [t["name"] for t in data["tools"]]
    assert "ragent_sync_and_search_jobs" in names
    assert "ragent_export_autofill_payload" in names


def test_mcp_api_invoke_tool(client_with_db):
    """测试 REST API 直接调用 MCP 工具。"""
    resp = client_with_db.post(
        "/mcp/tools/ragent_manage_resume_profile/invoke",
        json={"action": "get_active"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["active_resume"]["name"] == "李四"


def test_mcp_api_jsonrpc_tools_call(client_with_db):
    """测试 HTTP JSON-RPC 2.0 端点。"""
    req = {
        "jsonrpc": "2.0",
        "id": 101,
        "method": "tools/call",
        "params": {
            "name": "ragent_export_autofill_payload",
            "arguments": {"platform_name": "nowcoder", "add_to_kanban": False}
        }
    }
    resp = client_with_db.post("/mcp/jsonrpc", json=req)
    assert resp.status_code == 200
    res_json = resp.json()
    assert res_json["id"] == 101
    content_text = res_json["result"]["content"][0]["text"]
    tool_output = json.loads(content_text)
    assert tool_output["status"] == "success"
    assert tool_output["platform"] == "nowcoder"
    assert tool_output["autofill_payload"]["form_fields"]["name"] == "李四"
