from __future__ import annotations

from io import BytesIO
from tempfile import TemporaryDirectory
import unittest

from fastapi import UploadFile

from app.services.storage import LocalStorageService, UploadValidationError


class LocalStorageServiceTest(unittest.IsolatedAsyncioTestCase):
    """验证本地上传存储的商业化安全边界。"""

    async def test_save_upload_allows_known_document_suffix_and_normalizes_case(self) -> None:
        """允许知识库可解析的文档格式，并把扩展名统一为小写。"""

        with TemporaryDirectory() as directory:
            service = LocalStorageService(directory)
            file_path, file_size = await service.save_upload(UploadFile(filename="report.PDF", file=BytesIO(b"%PDF-1.4")))

            self.assertEqual(file_size, 8)
            self.assertTrue(file_path.endswith(".pdf"))

    async def test_save_upload_rejects_unsafe_suffix(self) -> None:
        """明显危险或不可解析的扩展名不应进入知识库处理链路。"""

        with TemporaryDirectory() as directory:
            service = LocalStorageService(directory)

            with self.assertRaises(UploadValidationError) as context:
                await service.save_upload(UploadFile(filename="payload.exe", file=BytesIO(b"MZ")))

            self.assertEqual(context.exception.status_code, 415)
            self.assertIn("Unsupported file type", str(context.exception))

    async def test_save_upload_rejects_missing_suffix(self) -> None:
        """没有扩展名的上传无法稳定判断解析方式，应直接拒绝。"""

        with TemporaryDirectory() as directory:
            service = LocalStorageService(directory)

            with self.assertRaises(UploadValidationError) as context:
                await service.save_upload(UploadFile(filename="README", file=BytesIO(b"hello")))

            self.assertEqual(context.exception.status_code, 415)

    async def test_save_upload_rejects_empty_file(self) -> None:
        """空文件不能进入摄取流水线，避免产生无效文档记录。"""

        with TemporaryDirectory() as directory:
            service = LocalStorageService(directory)

            with self.assertRaises(UploadValidationError) as context:
                await service.save_upload(UploadFile(filename="empty.txt", file=BytesIO(b"")))

            self.assertEqual(context.exception.status_code, 400)
            self.assertEqual(str(context.exception), "File is empty")

    async def test_save_upload_keeps_size_limit_status_code(self) -> None:
        """大小超限仍应返回 413，便于路由层给出准确响应。"""

        with TemporaryDirectory() as directory:
            service = LocalStorageService(directory)

            with self.assertRaises(UploadValidationError) as context:
                await service.save_upload(UploadFile(filename="large.txt", file=BytesIO(b"hello")), max_file_size=4)

            self.assertEqual(context.exception.status_code, 413)
            self.assertEqual(str(context.exception), "File exceeds maxFileSize")


if __name__ == "__main__":
    unittest.main()
