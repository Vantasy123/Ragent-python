"""模块说明：本文件属于 Ragent Python 后端，提供对应业务能力。"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any


class FetcherNode:
    """从本地存储读取上传文件。"""

    def execute(self, context, settings: dict[str, Any]) -> dict[str, Any]:
        source = settings.get("source_location") or settings.get("source")
        if not source:
            return {"success": False, "error": "缺少文件路径"}
        path = Path(source)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            return {"success": False, "error": f"文件不存在：{path}"}
        context.raw_bytes = path.read_bytes()
        context.mime_type = settings.get("mime_type") or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        context.metadata["source_path"] = str(path)
        return {"success": True, "size": len(context.raw_bytes)}
