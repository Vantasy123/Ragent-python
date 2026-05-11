"""模块导读：本文件位于 app/services/storage.py，属于服务层。

主要职责：承接路由层请求，组织数据库、缓存、Trace、Agent 和外部组件完成业务流程。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import UploadFile


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
        suffix = Path(upload.filename or "").suffix
        filename = f"{uuid.uuid4()}{suffix}"
        target = self.base_dir / filename
        content = await upload.read()
        content_size = len(content)
        if max_request_size is not None and content_size > max_request_size:
            raise ValueError("File exceeds maxRequestSize")
        if max_file_size is not None and content_size > max_file_size:
            raise ValueError("File exceeds maxFileSize")
        existing = self._find_existing_by_hash(content)
        if existing is not None:
            return str(existing), content_size
        target.write_bytes(content)
        return str(target), content_size

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


