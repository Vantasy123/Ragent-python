"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

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
    message: str
    conversationId: str | None = None
    autoExecuteReadOnly: bool = True


class ApprovalRequest(BaseModel):
    approvalId: str
    approved: bool
    comment: str | None = None


@router.get("/tools")
def list_tools(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return success(OpsAgentService(db).list_tools())


@router.get("/agents")
def list_agents(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return success(OpsAgentService(db).list_agents())


@router.post("/chat")
async def ops_chat(payload: OpsChatRequest, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    async def event_stream():
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
    return success(await OpsAgentService(db).approve(run_id, payload.approvalId, payload.approved, payload.comment, user))


@router.post("/runs/{run_id}/stop")
def stop(run_id: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return success(OpsAgentService(db).stop(run_id, user))


@router.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return success(OpsAgentService(db).get_run(run_id))
