"""模块导读：本文件位于 app/ingestion/nodes/fetcher_node.py，属于文档摄取流水线。

主要职责：把上传文件解析、分块、向量化并写入知识库索引。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any


class FetcherNode:
    """从本地存储读取上传文件。"""

    def execute(self, context, settings: dict[str, Any]) -> dict[str, Any]:
        """执行当前节点的核心逻辑，输入上下文并返回结构化处理结果。"""
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
