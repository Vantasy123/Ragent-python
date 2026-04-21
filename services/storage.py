from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile


class LocalStorageService:
    """Store uploaded source files in the configured local upload directory."""

    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir).expanduser()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save_upload(
        self,
        upload: UploadFile,
        max_file_size: int | None = None,
        max_request_size: int | None = None,
    ) -> tuple[str, int]:
        suffix = Path(upload.filename or "").suffix
        filename = f"{uuid.uuid4()}{suffix}"
        target = self.base_dir / filename
        content = await upload.read()
        content_size = len(content)
        if max_request_size is not None and content_size > max_request_size:
            raise ValueError("File exceeds maxRequestSize")
        if max_file_size is not None and content_size > max_file_size:
            raise ValueError("File exceeds maxFileSize")
        target.write_bytes(content)
        return str(target), content_size


def create_storage_service() -> LocalStorageService:
    from config import settings

    if settings.STORAGE_TYPE.lower() != "local":
        raise ValueError(f"Unsupported storage type: {settings.STORAGE_TYPE}")
    return LocalStorageService(settings.STORAGE_BASE_DIR)
