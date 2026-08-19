from __future__ import annotations

import io
import unittest
from unittest.mock import MagicMock, patch

from fastapi import UploadFile
from fastapi.testclient import TestClient

from app.api.routers.unified_chat import AttachmentItem, UnifiedChatRequest
from app.main import app
from app.services.chat_file_service import ChatFileService


class ChatFileUploadTest(unittest.TestCase):
    """测试对话台文件上传与文本提取服务。"""

    def test_decode_plain_text_utf8(self) -> None:
        raw = "这是测试文本内容，包含中文字符与英文字符。".encode("utf-8")
        text = ChatFileService.extract_text(raw, ".txt")
        self.assertIn("测试文本内容", text)

    def test_decode_plain_text_gbk(self) -> None:
        raw = "GBK 编码的求职简历文件".encode("gbk")
        text = ChatFileService.extract_text(raw, ".txt")
        self.assertIn("求职简历文件", text)

    def test_extract_markdown_text(self) -> None:
        raw = "# 个人简历\n\n- 求职意向：全栈工程师\n- 熟练掌握 Vue3 与 Python FastAPI".encode("utf-8")
        text = ChatFileService.extract_text(raw, ".md")
        self.assertIn("全栈工程师", text)
        self.assertIn("FastAPI", text)

    def test_unsupported_file_extension(self) -> None:
        upload = UploadFile(filename="malicious.exe", file=io.BytesIO(b"fake binary"))
        with self.assertRaises(ValueError) as ctx:
            import asyncio
            asyncio.run(ChatFileService.process_upload(upload))
        self.assertIn("不支持的文件格式", str(ctx.exception))

    def test_empty_file_upload(self) -> None:
        upload = UploadFile(filename="empty.txt", file=io.BytesIO(b""))
        with self.assertRaises(ValueError) as ctx:
            import asyncio
            asyncio.run(ChatFileService.process_upload(upload))
        self.assertIn("为空", str(ctx.exception))

    def test_attachment_item_validation(self) -> None:
        item = AttachmentItem(
            filename="resume.pdf",
            file_type="PDF",
            file_size=1024,
            char_count=500,
            text="简历内容",
            summary="成功解析简历",
        )
        self.assertEqual(item.filename, "resume.pdf")
        self.assertEqual(item.file_type, "PDF")

        req = UnifiedChatRequest(
            message="帮我分析简历",
            attachments=[item],
        )
        self.assertEqual(len(req.attachments), 1)
        self.assertEqual(req.attachments[0].filename, "resume.pdf")


if __name__ == "__main__":
    unittest.main()
