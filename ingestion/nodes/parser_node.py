"""Parser node for converting uploaded document bytes into text."""

from __future__ import annotations

import io
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ParserNode:
    """Parse PDF, Office and plain text uploads into raw text."""

    def execute(self, context, settings: dict[str, Any]) -> dict[str, Any]:
        try:
            if not context.raw_bytes:
                return {"success": False, "error": "No raw bytes to parse"}

            mime_type = context.mime_type or "application/octet-stream"
            logger.info("Parsing document: mime_type=%s, size=%s bytes", mime_type, len(context.raw_bytes))

            if "pdf" in mime_type:
                text = self._parse_pdf(context.raw_bytes)
            elif "word" in mime_type or "docx" in mime_type:
                text = self._parse_word(context.raw_bytes)
            elif "excel" in mime_type or "spreadsheet" in mime_type:
                text = self._parse_excel(context.raw_bytes)
            elif "text" in mime_type or "markdown" in mime_type:
                text = self._parse_text(context.raw_bytes)
            else:
                text = self._parse_text(context.raw_bytes)

            context.raw_text = text
            logger.info("Document parsed successfully: text_length=%s", len(text))
            return {"success": True}
        except Exception as exc:
            logger.error("Parser node failed: %s", exc, exc_info=True)
            return {"success": False, "error": str(exc)}

    def _parse_pdf(self, raw_bytes: bytes) -> str:
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(io.BytesIO(raw_bytes))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            logger.warning("PyPDF2 not installed, using text fallback")
            return self._decode_text(raw_bytes)

    def _parse_word(self, raw_bytes: bytes) -> str:
        try:
            from docx import Document

            doc = Document(io.BytesIO(raw_bytes))
            return "\n".join(paragraph.text for paragraph in doc.paragraphs)
        except ImportError:
            logger.warning("python-docx not installed, using text fallback")
            return self._decode_text(raw_bytes)

    def _parse_excel(self, raw_bytes: bytes) -> str:
        try:
            import pandas as pd

            df = pd.read_excel(io.BytesIO(raw_bytes))
            return df.to_string()
        except ImportError:
            logger.warning("pandas/openpyxl not installed, using text fallback")
            return self._decode_text(raw_bytes)

    def _parse_text(self, raw_bytes: bytes) -> str:
        return self._decode_text(raw_bytes)

    def _decode_text(self, raw_bytes: bytes) -> str:
        """Decode common text encodings used by uploads on Windows and Linux."""

        if raw_bytes.startswith(b"\xef\xbb\xbf"):
            return raw_bytes.decode("utf-8-sig")
        if raw_bytes.startswith(b"\xff\xfe") or raw_bytes.startswith(b"\xfe\xff"):
            return raw_bytes.decode("utf-16")

        candidates = (
            "utf-8",
            "gb18030",
            "gbk",
            "big5",
            "cp936",
            "cp1252",
            "latin-1",
        )
        for encoding in candidates:
            try:
                text = raw_bytes.decode(encoding)
                logger.info("Decoded text upload with encoding=%s", encoding)
                return text
            except UnicodeDecodeError:
                continue

        logger.warning("Failed to strictly decode text upload, falling back to utf-8 replacement")
        return raw_bytes.decode("utf-8", errors="replace")
