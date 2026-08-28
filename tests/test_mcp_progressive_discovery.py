"""测试 MCP 渐进式发现 (Progressive Discovery)、资源与 Prompt 模板协议。"""

from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.domain.models import Base, ResumeProfile, JobOpportunity, KnowledgeBase, KnowledgeChunk
from app.mcp_server import RagentMcpServer, MCP_TOOLS_DEFINITIONS, RAGENT_CAPABILITIES_CATALOG
from app.mcp_main import app


@pytest.fixture
def mock_db_session(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    init_session = TestingSessionLocal()
    resume = ResumeProfile(
        user_id="test_user_001",
        name="测试求职者",
        target_role="Python大模型工程师",
        score=92,
        is_default=True,
        parsed_data={
            "basic_info": {"name": "张三", "phone": "13800138000", "email": "zhangsan@example.com"},
            "educations": [{"school": "清华大学", "major": "计算机", "degree": "硕士"}],
            "work_experiences": [],
            "project_experiences": [{"project_name": "AI Agent 系统", "role": "负责人", "star_highlights": "QPS提升5倍"}]
        }
    )
    job = JobOpportunity(
        title="大模型算法工程师",
        company="智谱AI",
        city="北京",
        salary_min=30,
        salary_max=50,
        required_skills=["Python", "PyTorch", "LLM", "RAG"]
    )
    kb = KnowledgeBase(
        name="八股真题知识库",
        collection_name="test_collection",
        category="career"
    )
    init_session.add_all([resume, job, kb])
    init_session.commit()
    init_session.close()

    monkeypatch.setattr("app.mcp_server.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("app.mcp_main._server_instance", RagentMcpServer())
    return TestingSessionLocal


@pytest.fixture
def mcp_server(mock_db_session):
    return RagentMcpServer()


@pytest.fixture
def mcp_client(mock_db_session):
    return TestClient(app)


def test_discover_capabilities_layer1(mcp_server):
    """测试 Layer 1: 全景能力发现。"""
    res = mcp_server.handle_tool_call("ragent_discover_capabilities", {"category": "all"})
    assert res["status"] == "success"
    assert res["total_capabilities"] == 4
    assert len(res["capabilities"]) == 4
    cap_names = [c["name"] for c in res["capabilities"]]
    assert "job_market" in cap_names
    assert "interview_rag" in cap_names
    assert "resume_vault" in cap_names
    assert "autofill_bridge" in cap_names
    assert len(res["available_resources"]) >= 3
    assert len(res["available_prompts"]) >= 3


def test_inspect_capability_layer2(mcp_server):
    """测试 Layer 2: 目标领域按需深挖。"""
    res = mcp_server.handle_tool_call("ragent_inspect_capability", {"capability_name": "job_market"})
    assert res["status"] == "success"
    assert res["capability"]["name"] == "job_market"
    assert res["capability"]["tool_name"] == "ragent_sync_and_search_jobs"
    assert res["underlying_tool"]["name"] == "ragent_sync_and_search_jobs"
    assert "inputSchema" in res["underlying_tool"]

    # 测试未知能力报错
    err_res = mcp_server.handle_tool_call("ragent_inspect_capability", {"capability_name": "unknown_cap"})
    assert err_res["status"] == "error"


def test_resource_read_endpoints(mcp_server):
    """测试 MCP 动态资源读取。"""
    res1 = mcp_server.handle_resource_read("ragent://jobs/summary")
    assert res1["uri"] == "ragent://jobs/summary"
    assert res1["mimeType"] == "application/json"
    body1 = json.loads(res1["text"])
    assert "total_jobs" in body1

    res2 = mcp_server.handle_resource_read("ragent://knowledge/summary")
    assert res2["uri"] == "ragent://knowledge/summary"
    body2 = json.loads(res2["text"])
    assert "knowledge_bases" in body2


def test_mcp_api_progressive_discovery_rest(mcp_client):
    """测试 MCP API 独立微服务 REST 渐进式发现端点。"""
    # 1. GET /mcp/capabilities
    r1 = mcp_client.get("/mcp/capabilities")
    assert r1.status_code == 200
    data1 = r1.json()
    assert data1["total"] == 4
    assert len(data1["capabilities"]) == 4

    # 2. GET /mcp/capabilities/autofill_bridge
    r2 = mcp_client.get("/mcp/capabilities/autofill_bridge")
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["capability"]["tool_name"] == "ragent_export_autofill_payload"

    # 3. GET /mcp/resources
    r3 = mcp_client.get("/mcp/resources")
    assert r3.status_code == 200
    assert r3.json()["total"] >= 3

    # 4. GET /mcp/prompts
    r4 = mcp_client.get("/mcp/prompts")
    assert r4.status_code == 200
    assert r4.json()["total"] >= 3


def test_mcp_api_jsonrpc_progressive_discovery(mcp_client):
    """测试 MCP API 独立微服务 JSON-RPC 渐进式发现与资源请求。"""
    # 1. 发现能力调用
    r1 = mcp_client.post("/mcp/jsonrpc", json={
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "tools/call",
        "params": {
            "name": "ragent_discover_capabilities",
            "arguments": {"category": "all"}
        }
    })
    assert r1.status_code == 200
    res1 = r1.json()
    assert res1["id"] == "req-1"
    parsed1 = json.loads(res1["result"]["content"][0]["text"])
    assert parsed1["status"] == "success"
    assert parsed1["total_capabilities"] == 4

    # 2. 读取资源
    r2 = mcp_client.post("/mcp/jsonrpc", json={
        "jsonrpc": "2.0",
        "id": "req-2",
        "method": "resources/read",
        "params": {"uri": "ragent://jobs/summary"}
    })
    assert r2.status_code == 200
    assert r2.json()["id"] == "req-2"
    assert len(r2.json()["result"]["contents"]) == 1
