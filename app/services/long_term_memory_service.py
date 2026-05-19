"""长期记忆服务：从用户消息中抽取可复用偏好，并在后续问答中检索相关记忆。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.text_sanitizer import sanitize_text
from app.domain.models import UserMemory


@dataclass(slots=True)
class MemoryCandidate:
    """待写入长期记忆的候选内容。"""

    content: str
    memory_type: str
    weight: float
    keywords: list[str]


class LongTermMemoryService:
    """按用户维护长期记忆，避免只依赖 Redis 短期上下文。"""

    def __init__(self, db: Session):
        """构造函数：接收数据库会话，后续方法复用该会话读写记忆。"""
        self.db = db

    def remember_from_user_message(
        self,
        user_id: str | None,
        conversation_id: str,
        message_id: str,
        content: str,
    ) -> list[UserMemory]:
        """从用户消息中抽取长期记忆候选，命中显式偏好或个人事实才写入。"""

        if not settings.LONG_TERM_MEMORY_ENABLED or not user_id:
            return []
        candidates = self._extract_candidates(content)
        if not candidates:
            return []

        rows: list[UserMemory] = []
        for candidate in candidates:
            normalized = sanitize_text(candidate.content).strip()
            if not normalized or self._exists(user_id, normalized):
                continue
            row = UserMemory(
                user_id=user_id,
                conversation_id=conversation_id,
                source_message_id=message_id,
                memory_type=candidate.memory_type,
                content=normalized[:1000],
                weight=candidate.weight,
                meta_data={"keywords": candidate.keywords},
                enabled=True,
            )
            self.db.add(row)
            rows.append(row)
        if rows:
            self.db.commit()
            for row in rows:
                self.db.refresh(row)
        return rows

    def retrieve(self, user_id: str | None, query: str, limit: int | None = None) -> list[UserMemory]:
        """按轻量词项相关性检索当前问题最相关的长期记忆。"""

        if not settings.LONG_TERM_MEMORY_ENABLED or not user_id:
            return []
        safe_limit = max(1, int(limit or settings.LONG_TERM_MEMORY_TOP_K))
        rows = (
            self.db.query(UserMemory)
            .filter(UserMemory.user_id == user_id, UserMemory.enabled.is_(True))
            .order_by(UserMemory.updated_at.desc())
            .limit(200)
            .all()
        )
        if not rows:
            return []

        query_tokens = set(self._tokenize(query))
        scored: list[tuple[float, UserMemory]] = []
        for row in rows:
            memory_tokens = set(self._tokenize(row.content))
            keyword_tokens = set()
            metadata = row.meta_data or {}
            if isinstance(metadata, dict):
                keyword_tokens.update(str(item).lower() for item in metadata.get("keywords") or [])
            overlap = len(query_tokens.intersection(memory_tokens | keyword_tokens))
            recency_bonus = 0.05
            score = float(row.weight or 1.0) + overlap + recency_bonus
            if overlap > 0 or row.memory_type in {"profile", "instruction"}:
                scored.append((score, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [row for _, row in scored[:safe_limit]]

    def build_prompt_block(self, user_id: str | None, query: str) -> str:
        """把检索到的长期记忆压缩成可直接拼入 prompt 的文本块。"""

        rows = self.retrieve(user_id, query)
        if not rows:
            return ""

        max_chars = max(100, int(settings.LONG_TERM_MEMORY_MAX_CHARS))
        lines: list[str] = []
        total = 0
        for row in rows:
            line = f"- {row.content.strip()}"
            if total + len(line) > max_chars:
                break
            lines.append(line)
            total += len(line)
        return "\n".join(lines)

    def _extract_candidates(self, content: str) -> list[MemoryCandidate]:
        """用保守规则抽取长期记忆，避免把所有聊天内容都持久化。"""

        text = sanitize_text(content).strip()
        if not text or len(text) < 4:
            return []

        patterns: list[tuple[str, str, float]] = [
            (r"(?:请|麻烦)?(?:你)?(?:记住|记一下|以后记得)[:：]?\s*(.+)", "instruction", 2.0),
            (r"(?:以后|后续)(?:都|请)?(.{2,80})", "instruction", 1.6),
            (r"我(?:喜欢|偏好|更喜欢|习惯|希望|要求)(.{2,120})", "preference", 1.4),
            (r"我的(.{2,80})(?:是|为|叫)(.{1,80})", "profile", 1.3),
        ]
        candidates: list[MemoryCandidate] = []
        for pattern, memory_type, weight in patterns:
            for match in re.finditer(pattern, text):
                extracted = " ".join(part.strip() for part in match.groups() if part and part.strip())
                normalized = self._normalize_memory_text(extracted, memory_type)
                if normalized:
                    candidates.append(
                        MemoryCandidate(
                            content=normalized,
                            memory_type=memory_type,
                            weight=weight,
                            keywords=self._tokenize(normalized)[:20],
                        )
                    )
        return candidates[:3]

    def _normalize_memory_text(self, text: str, memory_type: str) -> str:
        """清理候选记忆，过滤过短或明显不适合长期保存的内容。"""

        normalized = re.sub(r"\s+", " ", sanitize_text(text)).strip(" ，,。.;；")
        if len(normalized) < 3:
            return ""
        if len(normalized) > 180:
            normalized = normalized[:180].rstrip()
        prefix = {
            "instruction": "用户要求",
            "preference": "用户偏好",
            "profile": "用户信息",
        }.get(memory_type, "用户记忆")
        return f"{prefix}：{normalized}"

    def _exists(self, user_id: str, content: str) -> bool:
        """避免重复写入完全相同的记忆。"""

        return (
            self.db.query(UserMemory.id)
            .filter(UserMemory.user_id == user_id, UserMemory.content == content, UserMemory.enabled.is_(True))
            .first()
            is not None
        )

    def _tokenize(self, text: str) -> list[str]:
        """中英文轻量分词，优先复用 jieba，缺失时回退正则切词。"""

        normalized = (text or "").lower()
        try:
            import jieba

            tokens = [token.strip() for token in jieba.cut(normalized) if token.strip()]
        except Exception:
            tokens = re.findall(r"[\w\u4e00-\u9fff]+", normalized)
        expanded = [token for token in tokens if len(token) > 1 or token.isdigit()]
        for span in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
            expanded.extend(span[index : index + 2] for index in range(0, len(span) - 1))
        return list(dict.fromkeys(expanded))
