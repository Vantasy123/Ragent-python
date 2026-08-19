"""多模态音频 API 路由：提供 TTS 语音合成与 ASR 语音识别转写接口。"""

from __future__ import annotations

import io
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app.domain.models import User
from app.services.audio_service import AudioService
from app.services.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audio", tags=["multimodal-audio"])


class TTSRequest(BaseModel):
    """TTS 语音合成请求。"""

    text: str = Field(..., description="待合成为语音的文本内容")
    voice: Optional[str] = Field(None, description="音色名称，如 FunAudioLLM/CosyVoice2-0.5B:alex")
    model: Optional[str] = Field(None, description="指定 TTS 模型")


@router.post("/tts")
def synthesize_tts(
    payload: TTSRequest,
    user: User = Depends(get_current_user),
):
    """将文本合成为 MP3 音频流，直接可供浏览器音频组件播放。"""
    try:
        audio_bytes = AudioService.synthesize_speech(
            text=payload.text,
            voice=payload.voice,
            model=payload.model,
        )
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=speech.mp3",
                "Cache-Control": "no-cache",
            },
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"语音合成失败: {exc}")


@router.post("/asr")
async def transcribe_asr(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """接收用户上传的音频文件并转写为文字。"""
    try:
        audio_bytes = await file.read()
        res = AudioService.transcribe_audio(
            audio_bytes=audio_bytes,
            filename=file.filename or "audio.mp3",
        )
        return {"code": 200, "message": "success", "data": res}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"语音转写失败: {exc}")
