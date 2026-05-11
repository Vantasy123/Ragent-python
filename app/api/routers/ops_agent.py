"""模块导读：本文件位于 app/api/routers/ops_agent.py，属于API 路由层。

主要职责：把 HTTP 请求转换成服务层调用，并把结果整理成前端可以直接使用的响应。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.domain.models import User
from app.services.common import success
from app.services.dependencies import require_admin
from app.services.ops_agent_service import OpsAgentService
from app.services.runtime_state import concurrency_slot

router = APIRouter(prefix="/agent/ops", tags=["ops-agent"])


class OpsChatRequest(BaseModel):
    """OpsChatRequest 请求模型：描述前端提交到接口的字段，FastAPI 会用它完成参数校验和类型转换。"""
    message: str
    conversationId: str | None = None
    autoExecuteReadOnly: bool = True


class ApprovalRequest(BaseModel):
    """ApprovalRequest 请求模型：描述前端提交到接口的字段，FastAPI 会用它完成参数校验和类型转换。"""
    approvalId: str
    approved: bool
    comment: str | None = None


@router.get("/tools")
def list_tools(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """list_tools 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
    return success(OpsAgentService(db).list_tools())


@router.get("/agents")
def list_agents(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """list_agents 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
    return success(OpsAgentService(db).list_agents())


@router.post("/chat")
async def ops_chat(payload: OpsChatRequest, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """ops_chat 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    async def event_stream():
        """event_stream 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        with concurrency_slot("ops:global", settings.OPS_AGENT_MAX_CONCURRENCY, settings.CONCURRENCY_COUNTER_TTL_SECONDS) as acquired:
            if not acquired:
                event = {"type": "error", "channel": "ops", "content": "运维 Agent 当前并发已满，请稍后再试"}
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                return
            async for event in OpsAgentService(db).stream_chat(
                payload.message,
                user,
                conversation_id=payload.conversationId,
                auto_execute_readonly=payload.autoExecuteReadOnly,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/runs/{run_id}/approve")
async def approve(run_id: str, payload: ApprovalRequest, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """approve 函数：处理高风险工具的审批结果，确保写操作不会被 Agent 自动绕过。"""
    return success(await OpsAgentService(db).approve(run_id, payload.approvalId, payload.approved, payload.comment, user))


@router.post("/runs/{run_id}/stop")
def stop(run_id: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """stop 函数：停止正在运行的任务，通常通过共享状态通知流式链路尽快结束。"""
    return success(OpsAgentService(db).stop(run_id, user))


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """get_run 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
    return success(OpsAgentService(db).get_run(run_id))
