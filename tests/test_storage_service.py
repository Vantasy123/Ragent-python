from __future__ import annotations

from io import BytesIO
from pathlib import Path
import shutil
import unittest
import uuid

from fastapi import UploadFile

from app.services import storage as storage_module
from app.services.storage import LocalStorageService, UploadValidationError


class TrackingUpload:
    """记录读取进度的测试上传对象，用于验证超限时是否提前停止。"""

    def __init__(self, filename: str, content: bytes):
        """保存测试内容和读取统计。"""

        self.filename = filename
        self._file = BytesIO(content)
        self.bytes_read = 0
        self.read_calls = 0

    async def read(self, size: int = -1) -> bytes:
        """模拟 UploadFile.read，并统计已读取字节数。"""

        chunk = self._file.read(size)
        self.bytes_read += len(chunk)
        self.read_calls += 1
        return chunk


class LocalStorageServiceTest(unittest.IsolatedAsyncioTestCase):
    """验证本地上传存储的商业化安全边界。"""

    def setUp(self) -> None:
        """准备显式测试目录，避免 Windows 沙箱下 tempfile 目录权限异常。"""

        self.created_dirs: list[Path] = []

    def tearDown(self) -> None:
        """清理测试期间创建的本地目录。"""

        for directory in self.created_dirs:
            shutil.rmtree(directory, ignore_errors=True)

    def _make_directory(self) -> str:
        """创建本测试专用目录，并登记到清理列表。"""

        root = Path("scratch") / "test-storage-service"
        root.mkdir(parents=True, exist_ok=True)
        directory = root / uuid.uuid4().hex
        directory.mkdir(parents=True, exist_ok=False)
        self.created_dirs.append(directory)
        return str(directory)

    async def test_save_upload_allows_known_document_suffix_and_normalizes_case(self) -> None:
        """允许知识库可解析的文档格式，并把扩展名统一为小写。"""

        service = LocalStorageService(self._make_directory())
        file_path, file_size = await service.save_upload(UploadFile(filename="report.PDF", file=BytesIO(b"%PDF-1.4")))

        self.assertEqual(file_size, 8)
        self.assertTrue(file_path.endswith(".pdf"))

    async def test_save_upload_rejects_unsafe_suffix(self) -> None:
        """明显危险或不可解析的扩展名不应进入知识库处理链路。"""

        service = LocalStorageService(self._make_directory())

        with self.assertRaises(UploadValidationError) as context:
            await service.save_upload(UploadFile(filename="payload.exe", file=BytesIO(b"MZ")))

        self.assertEqual(context.exception.status_code, 415)
        self.assertIn("Unsupported file type", str(context.exception))

    async def test_save_upload_rejects_missing_suffix(self) -> None:
        """没有扩展名的上传无法稳定判断解析方式，应直接拒绝。"""

        service = LocalStorageService(self._make_directory())

        with self.assertRaises(UploadValidationError) as context:
            await service.save_upload(UploadFile(filename="README", file=BytesIO(b"hello")))

        self.assertEqual(context.exception.status_code, 415)

    async def test_save_upload_rejects_empty_file(self) -> None:
        """空文件不能进入摄取流水线，避免产生无效文档记录。"""

        service = LocalStorageService(self._make_directory())

        with self.assertRaises(UploadValidationError) as context:
            await service.save_upload(UploadFile(filename="empty.txt", file=BytesIO(b"")))

        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(str(context.exception), "File is empty")

    async def test_save_upload_keeps_size_limit_status_code(self) -> None:
        """大小超限仍应返回 413，便于路由层给出准确响应。"""

        service = LocalStorageService(self._make_directory())

        with self.assertRaises(UploadValidationError) as context:
            await service.save_upload(UploadFile(filename="large.txt", file=BytesIO(b"hello")), max_file_size=4)

        self.assertEqual(context.exception.status_code, 413)
        self.assertEqual(str(context.exception), "File exceeds maxFileSize")

    async def test_save_upload_prefers_request_size_limit_message(self) -> None:
        """总请求大小限制更严格时，应返回 maxRequestSize 的错误信息。"""

        service = LocalStorageService(self._make_directory())

        with self.assertRaises(UploadValidationError) as context:
            await service.save_upload(
                UploadFile(filename="large.txt", file=BytesIO(b"hello")),
                max_file_size=10,
                max_request_size=4,
            )

        self.assertEqual(context.exception.status_code, 413)
        self.assertEqual(str(context.exception), "File exceeds maxRequestSize")

    async def test_save_upload_stops_reading_after_size_limit_is_exceeded(self) -> None:
        """上传超限后应提前停止读取，避免恶意大文件完整进入内存。"""

        original_chunk_size = storage_module.UPLOAD_READ_CHUNK_SIZE
        storage_module.UPLOAD_READ_CHUNK_SIZE = 2
        try:
            directory = self._make_directory()
            service = LocalStorageService(directory)
            upload = TrackingUpload("large.txt", b"abcdef")

            with self.assertRaises(UploadValidationError) as context:
                await service.save_upload(upload, max_file_size=3)  # type: ignore[arg-type]

            self.assertEqual(str(context.exception), "File exceeds maxFileSize")
            self.assertEqual(upload.bytes_read, 4)
            self.assertLess(upload.bytes_read, 6)
            self.assertEqual(list(Path(directory).iterdir()), [])
        finally:
            storage_module.UPLOAD_READ_CHUNK_SIZE = original_chunk_size


if __name__ == "__main__":
    unittest.main()
