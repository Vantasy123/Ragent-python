"""解析节点：把上传文档的字节内容转换为文本。"""

from __future__ import annotations

import io
import logging
import re
from typing import Any
import zipfile
from xml.etree import ElementTree

from app.core.text_sanitizer import sanitize_text

logger = logging.getLogger(__name__)


class ParserNode:
    """解析 PDF、Office 和纯文本上传文件，产出原始文本。"""

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

            # PDF/Office 解析器可能产生 NUL 等控制字符，进入分块前必须统一清理。
            context.raw_text = sanitize_text(text)
            logger.info("Document parsed successfully: text_length=%s", len(context.raw_text))
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
            text = "\n".join(paragraph.text for paragraph in doc.paragraphs)
            if text.strip():
                return text
            return self._parse_openxml_text(raw_bytes)
        except ImportError:
            logger.warning("python-docx not installed, using text fallback")
            return self._parse_openxml_text(raw_bytes)
        except Exception as exc:
            logger.warning("python-docx failed, trying OpenXML fallback: %s", exc)
            return self._parse_openxml_text(raw_bytes)

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
        """解码 Windows 和 Linux 上传文件中常见的文本编码。"""

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

    def _parse_openxml_text(self, raw_bytes: bytes) -> str:
        if not zipfile.is_zipfile(io.BytesIO(raw_bytes)):
            text = self._decode_text(raw_bytes).strip()
            if text:
                return text
            raise ValueError("Word document is not a readable docx/openxml package")

        text_parts: list[str] = []
        ignored_suffixes = (
            ".rels",
            "theme/theme1.xml",
            "themeManager.xml",
            "settings.xml",
            "styles.xml",
            "fontTable.xml",
            "webSettings.xml",
            "[Content_Types].xml",
        )

        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as package:
            names = package.namelist()
            preferred = [name for name in names if name == "word/document.xml"]
            fallback = [
                name
                for name in names
                if name.lower().endswith(".xml")
                and not any(name.endswith(suffix) for suffix in ignored_suffixes)
            ]
            for name in preferred + [item for item in fallback if item not in preferred]:
                try:
                    xml_bytes = package.read(name)
                    text = self._extract_xml_text(xml_bytes)
                except Exception as exc:
                    logger.debug("Failed to extract XML text from %s: %s", name, exc)
                    continue
                if text:
                    text_parts.append(text)

        text = "\n".join(part for part in text_parts if part.strip()).strip()
        if not text:
            raise ValueError("Word document package does not contain extractable body text")
        return text

    def _extract_xml_text(self, xml_bytes: bytes) -> str:
        root = ElementTree.fromstring(xml_bytes)
        texts: list[str] = []
        for element in root.iter():
            if element.text and element.text.strip():
                texts.append(element.text.strip())
        return re.sub(r"\s+", " ", " ".join(texts)).strip()


