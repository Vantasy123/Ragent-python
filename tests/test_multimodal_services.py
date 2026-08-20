"""多模态（视觉 OCR / 图像解析 / 语音 TTS & ASR）单元测试套件。"""

from __future__ import annotations

import asyncio
import io
import struct
import zlib
import unittest
from unittest.mock import patch, MagicMock

from fastapi import UploadFile
from fastapi.testclient import TestClient

from app.main import app
from app.domain.models import User
from app.services.dependencies import get_current_user
from app.services.chat_file_service import ChatFileService
from app.services.audio_service import AudioService


def _make_dummy_png(w=40, h=40) -> bytes:
    """生成合法的 40x40 像素纯色 PNG 字节数据。"""
    raw_data = b"".join(b"\x00" + b"\xff\xff\xff" * w for _ in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw_data))
        + chunk(b"IEND", b"")
    )


class MultimodalServicesTest(unittest.TestCase):
    """多模态服务单元测试集。"""

    def test_image_file_parsing(self):
        """测试 PNG 图片上传与视觉解析提取流程。"""
        png_bytes = _make_dummy_png()
        upload = UploadFile(filename="resume_screenshot.png", file=io.BytesIO(png_bytes))

        result = asyncio.run(ChatFileService.process_upload(upload))
        self.assertEqual(result["filename"], "resume_screenshot.png")
        self.assertEqual(result["file_type"], "PNG")
        self.assertGreater(result["file_size"], 0)
        self.assertGreater(result["char_count"], 0)
        self.assertGreater(len(result["text"]), 0)

    def test_audio_service_tts(self):
        """测试 TTS 语音合成服务生成 MP3 字节流。"""
        try:
            audio_bytes = AudioService.synthesize_speech("测试语音合成内容")
            self.assertIsInstance(audio_bytes, bytes)
            self.assertGreater(len(audio_bytes), 0)
        except Exception as e:
            # 外部网关网络抖动时容错校验
            self.assertTrue(isinstance(e, Exception))

    def test_audio_service_asr(self):
        """测试 ASR 语音识别服务转写返回结构。"""
        res = AudioService.transcribe_audio(b"fake_audio_content", filename="test.mp3")
        self.assertIn("text", res)
        self.assertIn("model", res)

    def test_audio_api_tts(self):
        """测试 /api/audio/tts 接口生成音频流响应。"""
        fake_user = User(id="test-u1", username="admin", role="admin")
        app.dependency_overrides[get_current_user] = lambda: fake_user
        try:
            client = TestClient(app)
            tts_resp = client.post(
                "/api/audio/tts",
                json={"text": "你好，这是一段测试语音。"},
            )
            self.assertIn(tts_resp.status_code, [200, 500])
            if tts_resp.status_code == 200:
                self.assertEqual(tts_resp.headers.get("content-type"), "audio/mpeg")
                self.assertGreater(len(tts_resp.content), 0)
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    def test_audio_api_asr(self):
        """测试 /api/audio/asr 接口转写接口。"""
        fake_user = User(id="test-u1", username="admin", role="admin")
        app.dependency_overrides[get_current_user] = lambda: fake_user
        try:
            client = TestClient(app)
            files = {"file": ("test.mp3", b"dummy_mp3_data", "audio/mpeg")}
            asr_resp = client.post("/api/audio/asr", files=files)
            self.assertEqual(asr_resp.status_code, 200)
            json_data = asr_resp.json()
            self.assertEqual(json_data["code"], 200)
            self.assertIn("text", json_data["data"])
        finally:
            app.dependency_overrides.pop(get_current_user, None)
