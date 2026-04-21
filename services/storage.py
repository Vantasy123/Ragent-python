from __future__ import annotations

import hashlib
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
        existing = self._find_existing_by_hash(content)
        if existing is not None:
            return str(existing), content_size
        target.write_bytes(content)
        return str(target), content_size

    def delete_file(self, file_path: str) -> bool:
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
    from config import settings

    if settings.STORAGE_TYPE.lower() != "local":
        raise ValueError(f"Unsupported storage type: {settings.STORAGE_TYPE}")
    return LocalStorageService(settings.STORAGE_BASE_DIR)
