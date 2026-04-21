from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models import SystemSetting, User

EditableSettingKey = str
SettingsPayload = dict[str, Any]
SettingsMeta = dict[str, Any]


@dataclass(slots=True)
class RuntimeSettings:
    top_k: int
    temperature: float
    history_keep_turns: int
    summary_enabled: bool
    summary_start_turns: int
    summary_max_chars: int
    title_max_length: int
    max_file_size: int
    max_request_size: int


class SettingDefinition(dict):
    key: EditableSettingKey
    group: str
    field: str
    label: str
    value_type: str
    restart_required: bool
    default_factory: Callable[[], Any]


EDITABLE_SETTINGS: dict[EditableSettingKey, SettingDefinition] = {
    "rag.topK": {
        "key": "rag.topK",
        "group": "rag",
        "field": "topK",
        "label": "Top K",
        "value_type": "int",
        "restart_required": False,
        "default_factory": lambda: settings.DEFAULT_TOP_K,
    },
    "rag.temperature": {
        "key": "rag.temperature",
        "group": "rag",
        "field": "temperature",
        "label": "Temperature",
        "value_type": "float",
        "restart_required": False,
        "default_factory": lambda: settings.TEMPERATURE,
    },
    "memory.historyKeepTurns": {
        "key": "memory.historyKeepTurns",
        "group": "memory",
        "field": "historyKeepTurns",
        "label": "History Keep Turns",
        "value_type": "int",
        "restart_required": False,
        "default_factory": lambda: settings.HISTORY_KEEP_TURNS,
    },
    "memory.summaryEnabled": {
        "key": "memory.summaryEnabled",
        "group": "memory",
        "field": "summaryEnabled",
        "label": "Summary Enabled",
        "value_type": "bool",
        "restart_required": True,
        "default_factory": lambda: settings.SUMMARY_ENABLED,
    },
    "memory.summaryStartTurns": {
        "key": "memory.summaryStartTurns",
        "group": "memory",
        "field": "summaryStartTurns",
        "label": "Summary Start Turns",
        "value_type": "int",
        "restart_required": True,
        "default_factory": lambda: settings.SUMMARY_START_TURNS,
    },
    "memory.summaryMaxChars": {
        "key": "memory.summaryMaxChars",
        "group": "memory",
        "field": "summaryMaxChars",
        "label": "Summary Max Chars",
        "value_type": "int",
        "restart_required": True,
        "default_factory": lambda: settings.SUMMARY_MAX_CHARS,
    },
    "memory.titleMaxLength": {
        "key": "memory.titleMaxLength",
        "group": "memory",
        "field": "titleMaxLength",
        "label": "Title Max Length",
        "value_type": "int",
        "restart_required": False,
        "default_factory": lambda: settings.TITLE_MAX_LENGTH,
    },
    "upload.maxFileSize": {
        "key": "upload.maxFileSize",
        "group": "upload",
        "field": "maxFileSize",
        "label": "Max File Size",
        "value_type": "int",
        "restart_required": False,
        "default_factory": lambda: settings.MAX_FILE_SIZE,
    },
    "upload.maxRequestSize": {
        "key": "upload.maxRequestSize",
        "group": "upload",
        "field": "maxRequestSize",
        "label": "Max Request Size",
        "value_type": "int",
        "restart_required": False,
        "default_factory": lambda: settings.MAX_REQUEST_SIZE,
    },
}


def _coerce_value(raw_value: Any, value_type: str) -> Any:
    if value_type == "bool":
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, str):
            normalized = raw_value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid boolean value: {raw_value}")
    if value_type == "int":
        try:
            return int(raw_value)
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid integer value: {raw_value}") from exc
    if value_type == "float":
        try:
            return float(raw_value)
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid float value: {raw_value}") from exc
    return str(raw_value)


def _serialize_value(value: Any, value_type: str) -> str:
    if value_type == "bool":
        return "true" if bool(value) else "false"
    return str(value)


def _default_editable_values() -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for definition in EDITABLE_SETTINGS.values():
        grouped.setdefault(definition["group"], {})[definition["field"]] = definition["default_factory"]()
    return grouped


def _readonly_values() -> dict[str, Any]:
    return {
        "models": {
            "defaultChatModel": settings.CHAT_MODEL,
            "defaultEmbeddingModel": settings.EMBEDDING_MODEL,
            "providerCandidates": {
                "chat": [
                    {"id": "primary", "provider": "openai-compatible", "model": settings.CHAT_MODEL, "priority": 1, "enabled": True},
                    {"id": "ollama-local", "provider": "ollama", "model": "qwen2.5:7b", "priority": 2, "enabled": True},
                ],
                "embedding": [
                    {
                        "id": "default-embedding",
                        "provider": "openai-compatible",
                        "model": settings.EMBEDDING_MODEL,
                        "dimension": settings.VECTOR_DIMENSION,
                        "priority": 1,
                        "enabled": True,
                    }
                ],
            },
        },
        "vector": {
            "collectionName": settings.COLLECTION_NAME,
            "dimension": settings.VECTOR_DIMENSION,
            "metricType": "COSINE",
        },
        "storage": {
            "type": "local",
        },
        "trace": {
            "persistence": True,
        },
        "security": {
            "databaseUrl": settings.DATABASE_URL,
            "jwtSecretConfigured": bool(settings.JWT_SECRET),
        },
    }


def _build_meta() -> SettingsMeta:
    editable_meta: dict[str, dict[str, Any]] = {}
    for definition in EDITABLE_SETTINGS.values():
        editable_meta.setdefault(definition["group"], {})[definition["field"]] = {
            "key": definition["key"],
            "label": definition["label"],
            "type": definition["value_type"],
            "editable": True,
            "restartRequired": definition["restart_required"],
        }
    return {
        "rag": editable_meta.get("rag", {}),
        "memory": editable_meta.get("memory", {}),
        "upload": editable_meta.get("upload", {}),
        "readonly": {
            "models": {"editable": False},
            "vector": {"editable": False},
            "storage": {"editable": False},
            "trace": {"editable": False},
            "security": {"editable": False},
        },
    }


def _load_db_overrides(db: Session) -> dict[str, SystemSetting]:
    rows = db.query(SystemSetting).filter(SystemSetting.key.in_(list(EDITABLE_SETTINGS.keys()))).all()
    return {row.key: row for row in rows}


def _apply_overrides(values: dict[str, dict[str, Any]], overrides: dict[str, SystemSetting]) -> dict[str, dict[str, Any]]:
    merged = {
        group: dict(group_values)
        for group, group_values in values.items()
    }
    for key, row in overrides.items():
        definition = EDITABLE_SETTINGS[key]
        merged.setdefault(definition["group"], {})[definition["field"]] = _coerce_value(row.value, row.value_type)
    return merged


def _flatten_update_payload(payload: SettingsPayload) -> dict[EditableSettingKey, Any]:
    flattened: dict[EditableSettingKey, Any] = {}
    allowed_groups = {"rag", "memory", "upload"}
    unknown_groups = set(payload.keys()) - allowed_groups
    if unknown_groups:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported settings groups: {', '.join(sorted(unknown_groups))}",
        )
    for group, group_values in payload.items():
        if not isinstance(group_values, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid payload for group: {group}")
        for field, value in group_values.items():
            dotted_key = f"{group}.{field}"
            if dotted_key not in EDITABLE_SETTINGS:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported setting key: {dotted_key}")
            flattened[dotted_key] = value
    return flattened


def _to_runtime_settings(values: dict[str, dict[str, Any]]) -> RuntimeSettings:
    rag_values = values.get("rag", {})
    memory_values = values.get("memory", {})
    upload_values = values.get("upload", {})
    return RuntimeSettings(
        top_k=int(rag_values.get("topK", settings.DEFAULT_TOP_K)),
        temperature=float(rag_values.get("temperature", settings.TEMPERATURE)),
        history_keep_turns=int(memory_values.get("historyKeepTurns", settings.HISTORY_KEEP_TURNS)),
        summary_enabled=bool(memory_values.get("summaryEnabled", settings.SUMMARY_ENABLED)),
        summary_start_turns=int(memory_values.get("summaryStartTurns", settings.SUMMARY_START_TURNS)),
        summary_max_chars=int(memory_values.get("summaryMaxChars", settings.SUMMARY_MAX_CHARS)),
        title_max_length=int(memory_values.get("titleMaxLength", settings.TITLE_MAX_LENGTH)),
        max_file_size=int(upload_values.get("maxFileSize", settings.MAX_FILE_SIZE)),
        max_request_size=int(upload_values.get("maxRequestSize", settings.MAX_REQUEST_SIZE)),
    )


def get_runtime_settings(db: Session | None = None) -> RuntimeSettings:
    if db is not None:
        values = _apply_overrides(_default_editable_values(), _load_db_overrides(db))
        return _to_runtime_settings(values)

    local_db = SessionLocal()
    try:
        values = _apply_overrides(_default_editable_values(), _load_db_overrides(local_db))
        return _to_runtime_settings(values)
    finally:
        local_db.close()


def build_settings_payload(db: Session) -> dict[str, Any]:
    values = _apply_overrides(_default_editable_values(), _load_db_overrides(db))
    return {
        "values": {
            **values,
            "readonly": _readonly_values(),
        },
        "meta": _build_meta(),
        "restartRequired": False,
    }


def update_settings(db: Session, user: User, payload: SettingsPayload) -> dict[str, Any]:
    flattened = _flatten_update_payload(payload)
    overrides = _load_db_overrides(db)
    changed_keys: list[str] = []
    for key, raw_value in flattened.items():
        definition = EDITABLE_SETTINGS[key]
        coerced = _coerce_value(raw_value, definition["value_type"])
        serialized = _serialize_value(coerced, definition["value_type"])
        row = overrides.get(key)
        if row is None:
            row = SystemSetting(
                key=key,
                value=serialized,
                value_type=definition["value_type"],
                updated_by=user.id,
            )
            db.add(row)
            changed_keys.append(key)
            continue
        if row.value != serialized or row.value_type != definition["value_type"]:
            row.value = serialized
            row.value_type = definition["value_type"]
            row.updated_by = user.id
            changed_keys.append(key)
    db.commit()
    restart_required = any(EDITABLE_SETTINGS[key]["restart_required"] for key in changed_keys)
    return {
        **build_settings_payload(db),
        "changedKeys": changed_keys,
        "restartRequired": restart_required,
    }
