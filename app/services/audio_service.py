"""多模态语音中枢服务：提供 AI 模拟面试官 TTS 语音播报合成与候选人 ASR 语音识别转写。"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


class AudioService:
    """提供基于 SiliconFlow 免费开源模型的 TTS 语音合成与 ASR 语音识别服务。"""

    @classmethod
    def synthesize_speech(
        cls,
        text: str,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        response_format: str = "mp3"
    ) -> bytes:
        """调用 SiliconFlow TTS 接口，将文本合成为高质量音频字节流（MP3）。"""
        if not text or not text.strip():
            raise ValueError("TTS 输入文本不能为空")

        api_key = settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY
        if not api_key or "test" in api_key.lower() or "your-api-key" in api_key.lower():
            # 测试环境返回空 MP3 音频伪数据
            return b"\xff\xfb\x90d\x00\x00\x00\x00" * 100

        tts_model = model or settings.TTS_MODEL or "FunAudioLLM/CosyVoice2-0.5B"
        tts_voice = voice or settings.TTS_VOICE or "FunAudioLLM/CosyVoice2-0.5B:alex"

        url = f"{settings.OPENAI_API_BASE.rstrip('/')}/audio/speech"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": tts_model,
            "input": text.strip()[:1000],  # 截断过长文本
            "voice": tts_voice,
            "response_format": response_format
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            if resp.status_code != 200:
                logger.warning(f"TTS 合成接口返回错误 {resp.status_code}: {resp.text}")
                raise RuntimeError(f"TTS 合成失败: {resp.status_code} - {resp.text}")
            return resp.content
        except Exception as exc:
            logger.error(f"TTS 语音合成异常: {exc}")
            raise exc

    @classmethod
    def transcribe_audio(
        cls,
        audio_bytes: bytes,
        filename: str = "audio.mp3",
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """调用 SiliconFlow ASR 接口，将用户语音录音识别转写为结构化文本。"""
        if not audio_bytes or len(audio_bytes) == 0:
            raise ValueError("上传的音频数据为空")

        api_key = settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY
        if not api_key or "test" in api_key.lower() or "your-api-key" in api_key.lower():
            return {"text": "（测试环境语音转写模拟结果）", "model": "mock"}

        asr_model = model or settings.ASR_MODEL or "FunAudioLLM/SenseVoiceSmall"
        url = f"{settings.OPENAI_API_BASE.rstrip('/')}/audio/transcriptions"
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        files = {
            "file": (filename, audio_bytes, "audio/mpeg")
        }
        data = {
            "model": asr_model
        }

        try:
            resp = requests.post(url, headers=headers, data=data, files=files, timeout=25)
            if resp.status_code != 200:
                logger.warning(f"ASR 转写接口返回错误 {resp.status_code}: {resp.text}")
                return {
                    "text": f"（语音识别返回状态码 {resp.status_code}）",
                    "model": asr_model,
                    "error": resp.text
                }
            result = resp.json()
            return {
                "text": result.get("text", "").strip(),
                "model": asr_model
            }
        except Exception as exc:
            logger.error(f"ASR 语音转写异常: {exc}")
            return {
                "text": f"（语音转写异常: {exc}）",
                "model": asr_model,
                "error": str(exc)
            }
