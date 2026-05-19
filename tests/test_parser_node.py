from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.ingestion.nodes.parser_node import ParserNode


class ParserContext:
    """测试用最小流水线上下文，只保留 ParserNode 需要的字段。"""

    def __init__(self, raw_bytes: bytes, mime_type: str, source_path: str | None = None) -> None:
        self.raw_bytes = raw_bytes
        self.mime_type = mime_type
        self.raw_text: str | None = None
        self.metadata: dict[str, str] = {}
        if source_path:
            self.metadata["source_path"] = source_path


def fake_markitdown_module(text: str | None = None, error: Exception | None = None) -> types.ModuleType:
    """构造假的 markitdown 模块，避免测试依赖真实第三方包。"""

    module = types.ModuleType("markitdown")

    class FakeMarkItDown:
        """模拟 MarkItDown 的最小 Python API。"""

        def __init__(self, enable_plugins: bool = False) -> None:
            self.enable_plugins = enable_plugins

        def convert_local(self, path: str):
            if error:
                raise error
            return SimpleNamespace(text_content=text)

    module.MarkItDown = FakeMarkItDown
    return module


class ParserNodeMarkItDownTest(unittest.TestCase):
    """验证 MarkItDown 优先解析和 legacy 回退行为。"""

    def test_markitdown_success_sets_parser_metadata_and_sanitizes_text(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as handle:
            source_path = handle.name
            handle.write(b"ignored")
        self.addCleanup(lambda: Path(source_path).unlink(missing_ok=True))

        context = ParserContext(b"legacy text", "text/markdown", source_path)
        module = fake_markitdown_module("# 标题\x00\n正文")

        with patch.dict(sys.modules, {"markitdown": module}):
            result = ParserNode().execute(context, {})

        self.assertTrue(result["success"])
        self.assertEqual(context.metadata["parser"], "markitdown")
        self.assertIn("# 标题", context.raw_text or "")
        self.assertNotIn("\x00", context.raw_text or "")

    def test_markitdown_error_falls_back_to_legacy_text_parser(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as handle:
            source_path = handle.name
            handle.write(b"legacy text")
        self.addCleanup(lambda: Path(source_path).unlink(missing_ok=True))

        context = ParserContext("旧解析文本".encode("utf-8"), "text/plain", source_path)
        module = fake_markitdown_module(error=RuntimeError("boom"))

        with patch.dict(sys.modules, {"markitdown": module}):
            result = ParserNode().execute(context, {})

        self.assertTrue(result["success"])
        self.assertEqual(context.metadata["parser"], "legacy")
        self.assertIn("RuntimeError: boom", context.metadata["parser_fallback"])
        self.assertEqual(context.raw_text, "旧解析文本")

    def test_markitdown_empty_text_falls_back_to_legacy_parser(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as handle:
            source_path = handle.name
            handle.write(b"legacy text")
        self.addCleanup(lambda: Path(source_path).unlink(missing_ok=True))

        context = ParserContext(b"legacy text", "text/plain", source_path)
        module = fake_markitdown_module(text="   ")

        with patch.dict(sys.modules, {"markitdown": module}):
            result = ParserNode().execute(context, {})

        self.assertTrue(result["success"])
        self.assertEqual(context.metadata["parser"], "legacy")
        self.assertIn("empty text", context.metadata["parser_fallback"])
        self.assertEqual(context.raw_text, "legacy text")

    def test_missing_source_path_does_not_block_legacy_parser(self) -> None:
        context = ParserContext(b"plain text", "text/plain")

        result = ParserNode().execute(context, {})

        self.assertTrue(result["success"])
        self.assertEqual(context.metadata["parser"], "legacy")
        self.assertIn("source_path", context.metadata["parser_fallback"])
        self.assertEqual(context.raw_text, "plain text")

    def test_pdf_markitdown_failure_uses_pdf_legacy_branch(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            source_path = handle.name
            handle.write(b"%PDF fake")
        self.addCleanup(lambda: Path(source_path).unlink(missing_ok=True))

        context = ParserContext(b"%PDF fake", "application/pdf", source_path)
        module = fake_markitdown_module(error=RuntimeError("pdf convert failed"))

        with patch.dict(sys.modules, {"markitdown": module}):
            with patch.object(ParserNode, "_parse_pdf", return_value="pdf legacy text") as parse_pdf:
                result = ParserNode().execute(context, {})

        self.assertTrue(result["success"])
        parse_pdf.assert_called_once_with(b"%PDF fake")
        self.assertEqual(context.metadata["parser"], "legacy")
        self.assertEqual(context.raw_text, "pdf legacy text")


if __name__ == "__main__":
    unittest.main()
