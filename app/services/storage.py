"""模块导读：本文件位于 app/services/storage.py，属于服务层。

主要职责：承接路由层请求，组织数据库、缓存、Trace、Agent 和外部组件完成业务流程。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import UploadFile

ALLOWED_UPLOAD_SUFFIXES = frozenset(
    {
        ".csv",
        ".doc",
        ".docx",
        ".json",
        ".log",
        ".markdown",
        ".md",
        ".pdf",
        ".txt",
        ".xls",
        ".xlsx",
        ".yaml",
        ".yml",
    }
)
UPLOAD_READ_CHUNK_SIZE = 1024 * 1024


class UploadValidationError(ValueError):
    """上传文件校验失败时携带 HTTP 状态码，便于路由层返回准确错误。"""

    def __init__(self, message: str, status_code: int = 400):
        """初始化上传校验错误。"""

        super().__init__(message)
        self.status_code = status_code


class LocalStorageService:
    """把上传的源文件保存到配置指定的本地上传目录。"""

    def __init__(self, base_dir: str):
        """构造函数：接收外部依赖并保存到实例中，后续方法会复用这些依赖完成业务处理。"""
        self.base_dir = Path(base_dir).expanduser()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save_upload(
        self,
        upload: UploadFile,
        max_file_size: int | None = None,
        max_request_size: int | None = None,
    ) -> tuple[str, int]:
        """save_upload 函数：把处理结果保存到文件、数据库或缓存中，作为后续流程的输入。"""
        suffix = self._normalize_upload_suffix(upload.filename)
        filename = f"{uuid.uuid4()}{suffix}"
        target = self.base_dir / filename
        content = await self._read_upload_content(upload, max_file_size, max_request_size)
        content_size = len(content)
        if content_size == 0:
            raise UploadValidationError("File is empty", status_code=400)
        existing = self._find_existing_by_hash(content)
        if existing is not None:
            return str(existing), content_size
        target.write_bytes(content)
        return str(target), content_size

    async def _read_upload_content(
        self,
        upload: UploadFile,
        max_file_size: int | None = None,
        max_request_size: int | None = None,
    ) -> bytes:
        """分块读取上传内容，并在超限时提前终止，避免大文件一次性进入内存。"""

        limit, error_message = self._effective_size_limit(max_file_size, max_request_size)
        content = bytearray()
        while True:
            chunk = await upload.read(UPLOAD_READ_CHUNK_SIZE)
            if not chunk:
                break
            content.extend(chunk)
            if limit is not None and len(content) > limit:
                raise UploadValidationError(error_message or "File exceeds size limit", status_code=413)
        return bytes(content)

    def _effective_size_limit(
        self,
        max_file_size: int | None = None,
        max_request_size: int | None = None,
    ) -> tuple[int | None, str | None]:
        """计算最严格的上传大小限制，并保持旧接口的错误信息优先级。"""

        if max_request_size is None and max_file_size is None:
            return None, None
        if max_request_size is None:
            return max_file_size, "File exceeds maxFileSize"
        if max_file_size is None:
            return max_request_size, "File exceeds maxRequestSize"
        if max_request_size <= max_file_size:
            return max_request_size, "File exceeds maxRequestSize"
        return max_file_size, "File exceeds maxFileSize"

    def _normalize_upload_suffix(self, filename: str | None) -> str:
        """校验并规范化上传文件扩展名，避免危险文件进入知识库处理链路。"""

        suffix = Path(filename or "").suffix.lower()
        if not suffix:
            raise UploadValidationError("Unsupported file type: missing extension", status_code=415)
        if suffix not in ALLOWED_UPLOAD_SUFFIXES:
            allowed = ", ".join(sorted(ALLOWED_UPLOAD_SUFFIXES))
            raise UploadValidationError(f"Unsupported file type: {suffix}; allowed: {allowed}", status_code=415)
        return suffix

    def delete_file(self, file_path: str) -> bool:
        """delete_file 函数：删除业务记录，并在需要时同步清理关联资源或缓存。"""
        target = Path(file_path).expanduser()
        if not target.is_absolute():
            target = self.base_dir / target.name

        try:
            resolved_base = self.base_dir.resolve()
            resolved_target = target.resolve()
        except OSError:
            return False

        if resolved_base not in resolved_target.parents:
            return False
        if not resolved_target.is_file():
            return False

        resolved_target.unlink()
        return True

    def _find_existing_by_hash(self, content: bytes) -> Path | None:
        """_find_existing_by_hash 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
        content_hash = hashlib.sha256(content).hexdigest()
        try:
            candidates = list(self.base_dir.iterdir())
        except OSError:
            return None
        for candidate in candidates:
            if not candidate.is_file() or candidate.name == ".gitkeep":
                continue
            try:
                if hashlib.sha256(candidate.read_bytes()).hexdigest() == content_hash:
                    return candidate
            except OSError:
                continue
        return None


def create_storage_service() -> LocalStorageService:
    """create_storage_service 函数：创建新的业务记录，负责组织入库字段并返回创建后的结果。"""
    from app.core.config import settings

    if settings.STORAGE_TYPE.lower() != "local":
        raise ValueError(f"Unsupported storage type: {settings.STORAGE_TYPE}")
    return LocalStorageService(settings.STORAGE_BASE_DIR)


