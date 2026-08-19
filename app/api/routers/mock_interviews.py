"""智能求职 Agent AI 模拟面试 API 路由。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domain.models import User
from app.services.dependencies import get_current_user
from app.services.mock_interview_service import MockInterviewService

router = APIRouter(prefix="/jobs/interviews", tags=["Mock Interviews"])


class CreateSessionRequest(BaseModel):
    target_role: str = "后端开发工程师"
    role_type: str = "tech_expert"
    difficulty: str = "intermediate"
    resume_id: Optional[str] = None
    job_id: Optional[str] = None


class GenerateQuestionRequest(BaseModel):
    round_number: Optional[int] = None
    question_type: Optional[str] = None


class EvaluateAnswerRequest(BaseModel):
    user_answer: str


@router.get("/sessions")
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = MockInterviewService(db)
    sessions = service.get_sessions_by_user(current_user.id)
    return {
        "items": [
            {
                "id": s.id,
                "targetRole": s.target_role,
                "roleType": s.role_type,
                "difficulty": s.difficulty,
                "status": s.status,
                "overallScore": s.overall_score,
                "feedbackSummary": s.feedback_summary,
                "detailedDimensions": s.detailed_dimensions,
                "roundsCount": len(s.records),
                "createdAt": s.created_at.isoformat() if s.created_at else None,
            }
            for s in sessions
        ]
    }


@router.get("/sessions/{session_id}")
def get_session_detail(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = MockInterviewService(db)
    session = service.get_session_by_id(session_id, user_id=current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="面试会话不存在")

    records = [
        {
            "id": r.id,
            "roundNumber": r.round_number,
            "questionType": r.question_type,
            "question": r.question,
            "expectedKeyPoints": r.expected_key_points,
            "userAnswer": r.user_answer,
            "score": r.score,
            "feedback": r.feedback,
            "modelAnswer": r.model_answer,
            "improvementTips": r.improvement_tips,
            "createdAt": r.created_at.isoformat() if r.created_at else None,
        }
        for r in session.records
    ]

    return {
        "id": session.id,
        "targetRole": session.target_role,
        "roleType": session.role_type,
        "difficulty": session.difficulty,
        "status": session.status,
        "overallScore": session.overall_score,
        "feedbackSummary": session.feedback_summary,
        "detailedDimensions": session.detailed_dimensions,
        "records": records,
        "createdAt": session.created_at.isoformat() if session.created_at else None,
    }


@router.post("/sessions")
def create_session(
    req: CreateSessionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = MockInterviewService(db)
    session = service.create_interview_session(
        user_id=current_user.id,
        target_role=req.target_role,
        role_type=req.role_type,
        difficulty=req.difficulty,
        resume_id=req.resume_id,
        job_id=req.job_id
    )
    return {"id": session.id, "status": session.status, "message": "模拟面试已开始"}


@router.post("/sessions/{session_id}/next-question")
def generate_next_question(
    session_id: str,
    req: GenerateQuestionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = MockInterviewService(db)
    record = service.generate_next_question(
        session_id=session_id,
        round_number=req.round_number,
        question_type=req.question_type
    )
    return {
        "id": record.id,
        "roundNumber": record.round_number,
        "questionType": record.question_type,
        "question": record.question,
        "expectedKeyPoints": record.expected_key_points,
        "modelAnswer": record.model_answer
    }


@router.post("/records/{record_id}/evaluate")
def evaluate_answer(
    record_id: str,
    req: EvaluateAnswerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = MockInterviewService(db)
    record = service.evaluate_answer(record_id=record_id, user_answer=req.user_answer)
    return {
        "id": record.id,
        "roundNumber": record.round_number,
        "score": record.score,
        "feedback": record.feedback,
        "modelAnswer": record.model_answer,
        "improvementTips": record.improvement_tips
    }


@router.post("/sessions/{session_id}/finish")
def finish_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    service = MockInterviewService(db)
    session = service.finish_session_and_generate_report(session_id=session_id)
    return {
        "id": session.id,
        "status": session.status,
        "overallScore": session.overall_score,
        "feedbackSummary": session.feedback_summary,
        "detailedDimensions": session.detailed_dimensions
    }
