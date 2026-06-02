"""模块导读：本文件位于 app/services/settings_service.py，属于服务层。

主要职责：承接路由层请求，组织数据库、缓存、Trace、Agent 和外部组件完成业务流程。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.time_utils import to_shanghai_iso
from app.domain.models import SystemSetting, SystemSettingAuditLog, User

EditableSettingKey = str
SettingsPayload = dict[str, Any]
SettingsMeta = dict[str, Any]


@dataclass(slots=True)
class RuntimeSettings:
    """RuntimeSettings 辅助类型：把相关字段和行为组织在一起，减少跨模块传递零散数据。"""
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
    """SettingDefinition 辅助类型：把相关字段和行为组织在一起，减少跨模块传递零散数据。"""
    key: EditableSettingKey
    group: str
    field: str
    label: str
    value_type: str
    restart_required: bool
    default_factory: Callable[[], Any]
    min_value: int | float | None
    max_value: int | float | None
    sensitive: bool


EDITABLE_SETTINGS: dict[EditableSettingKey, SettingDefinition] = {
    "rag.topK": {
        "key": "rag.topK",
        "group": "rag",
        "field": "topK",
        "label": "Top K",
        "value_type": "int",
        "restart_required": False,
        "default_factory": lambda: settings.DEFAULT_TOP_K,
        "min_value": 1,
        "max_value": 50,
    },
    "rag.temperature": {
        "key": "rag.temperature",
        "group": "rag",
        "field": "temperature",
        "label": "Temperature",
        "value_type": "float",
        "restart_required": False,
        "default_factory": lambda: settings.TEMPERATURE,
        "min_value": 0.0,
        "max_value": 2.0,
    },
    "memory.historyKeepTurns": {
        "key": "memory.historyKeepTurns",
        "group": "memory",
        "field": "historyKeepTurns",
        "label": "History Keep Turns",
        "value_type": "int",
        "restart_required": False,
        "default_factory": lambda: settings.HISTORY_KEEP_TURNS,
        "min_value": 1,
        "max_value": 50,
    },
    "memory.summaryEnabled": {
        "key": "memory.summaryEnabled",
        "group": "memory",
        "field": "summaryEnabled",
        "label": "Summary Enabled",
        "value_type": "bool",
        "restart_required": True,
        "default_factory": lambda: settings.SUMMARY_ENABLED,
        "min_value": None,
        "max_value": None,
    },
    "memory.summaryStartTurns": {
        "key": "memory.summaryStartTurns",
        "group": "memory",
        "field": "summaryStartTurns",
        "label": "Summary Start Turns",
        "value_type": "int",
        "restart_required": True,
        "default_factory": lambda: settings.SUMMARY_START_TURNS,
        "min_value": 1,
        "max_value": 100,
    },
    "memory.summaryMaxChars": {
        "key": "memory.summaryMaxChars",
        "group": "memory",
        "field": "summaryMaxChars",
        "label": "Summary Max Chars",
        "value_type": "int",
        "restart_required": True,
        "default_factory": lambda: settings.SUMMARY_MAX_CHARS,
        "min_value": 50,
        "max_value": 4000,
    },
    "memory.titleMaxLength": {
        "key": "memory.titleMaxLength",
        "group": "memory",
        "field": "titleMaxLength",
        "label": "Title Max Length",
        "value_type": "int",
        "restart_required": False,
        "default_factory": lambda: settings.TITLE_MAX_LENGTH,
        "min_value": 10,
        "max_value": 120,
    },
    "upload.maxFileSize": {
        "key": "upload.maxFileSize",
        "group": "upload",
        "field": "maxFileSize",
        "label": "Max File Size",
        "value_type": "int",
        "restart_required": False,
        "default_factory": lambda: settings.MAX_FILE_SIZE,
        "min_value": 1024,
        "max_value": 1024 * 1024 * 1024,
    },
    "upload.maxRequestSize": {
        "key": "upload.maxRequestSize",
        "group": "upload",
        "field": "maxRequestSize",
        "label": "Max Request Size",
        "value_type": "int",
        "restart_required": False,
        "default_factory": lambda: settings.MAX_REQUEST_SIZE,
        "min_value": 1024,
        "max_value": 2 * 1024 * 1024 * 1024,
    },
}

SENSITIVE_AUDIT_VALUE = "<redacted>"
SENSITIVE_SETTING_KEY_PARTS = (
    "password",
    "secret",
    "token",
    "credential",
    "apikey",
    "accesskey",
    "privatekey",
    "databaseurl",
    "connectionstring",
    "dsn",
)


def _coerce_value(raw_value: Any, value_type: str) -> Any:
    """_coerce_value 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
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


def _coerce_setting_value(definition: SettingDefinition, raw_value: Any) -> Any:
    """按配置定义完成类型转换和边界校验。"""

    value = _coerce_value(raw_value, definition["value_type"])
    min_value = definition.get("min_value")
    max_value = definition.get("max_value")
    if min_value is None and max_value is None:
        return value
    if min_value is not None and value < min_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{definition['label']} must be greater than or equal to {min_value}",
        )
    if max_value is not None and value > max_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{definition['label']} must be less than or equal to {max_value}",
        )
    return value


def _serialize_value(value: Any, value_type: str) -> str:
    """_serialize_value 函数：计算或整理一段辅助数据，让主流程保持清晰。"""
    if value_type == "bool":
        return "true" if bool(value) else "false"
    return str(value)


def _default_editable_values() -> dict[str, dict[str, Any]]:
    """_default_editable_values 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    grouped: dict[str, dict[str, Any]] = {}
    for definition in EDITABLE_SETTINGS.values():
        grouped.setdefault(definition["group"], {})[definition["field"]] = definition["default_factory"]()
    return grouped


def _readonly_values() -> dict[str, Any]:
    """_readonly_values 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    database_info = _redact_database_url(settings.DATABASE_URL)
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
            "backend": settings.VECTOR_BACKEND,
            "collectionName": settings.COLLECTION_NAME,
            "dimension": settings.VECTOR_DIMENSION,
            "metricType": "COSINE",
            "uri": settings.MILVUS_URI,
        },
        "storage": {
            "type": "local",
        },
        "trace": {
            "persistence": True,
        },
        "security": {
            "databaseConfigured": database_info["configured"],
            "databaseScheme": database_info["scheme"],
            "databaseHost": database_info["host"],
            "databaseUrl": database_info["redactedUrl"],
            "jwtSecretConfigured": bool(settings.JWT_SECRET),
        },
    }


def _redact_database_url(database_url: str) -> dict[str, Any]:
    """脱敏数据库连接串，只保留排障需要的协议和主机信息。"""

    if not database_url:
        return {
            "configured": False,
            "scheme": "",
            "host": "",
            "redactedUrl": "",
        }

    try:
        parsed = urlsplit(database_url)
    except ValueError:
        return {
            "configured": True,
            "scheme": "",
            "host": "",
            "redactedUrl": "<invalid-database-url>",
        }

    # SQLite 路径可能包含本机目录结构，后台展示时只说明使用本地文件。
    if parsed.scheme.startswith("sqlite"):
        return {
            "configured": True,
            "scheme": parsed.scheme,
            "host": "local-file",
            "redactedUrl": f"{parsed.scheme}:///<local-file>",
        }

    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{host}{port}"
    if parsed.username or parsed.password:
        netloc = f"***:***@{host}{port}"

    redacted_url = urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    return {
        "configured": True,
        "scheme": parsed.scheme,
        "host": host,
        "redactedUrl": redacted_url,
    }


def _build_meta() -> SettingsMeta:
    """_build_meta 函数：把内部数据整理成后续步骤需要的格式，避免业务逻辑到处重复拼装。"""
    editable_meta: dict[str, dict[str, Any]] = {}
    for definition in EDITABLE_SETTINGS.values():
        editable_meta.setdefault(definition["group"], {})[definition["field"]] = {
            "key": definition["key"],
            "label": definition["label"],
            "type": definition["value_type"],
            "editable": True,
            "restartRequired": definition["restart_required"],
            "min": definition.get("min_value"),
            "max": definition.get("max_value"),
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
    """_load_db_overrides 函数：从配置、数据库或外部系统读取数据，并转换成本模块可使用的结构。"""
    rows = db.query(SystemSetting).filter(SystemSetting.key.in_(list(EDITABLE_SETTINGS.keys()))).all()
    return {row.key: row for row in rows}


def _apply_overrides(values: dict[str, dict[str, Any]], overrides: dict[str, SystemSetting]) -> dict[str, dict[str, Any]]:
    """_apply_overrides 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
    merged = {
        group: dict(group_values)
        for group, group_values in values.items()
    }
    for key, row in overrides.items():
        definition = EDITABLE_SETTINGS[key]
        merged.setdefault(definition["group"], {})[definition["field"]] = _coerce_setting_value(definition, row.value)
    return merged


def _flatten_update_payload(payload: SettingsPayload) -> dict[EditableSettingKey, Any]:
    """_flatten_update_payload 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
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
    """_to_runtime_settings 函数：封装一个可复用的业务步骤，让调用方只关心输入和输出。"""
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
    """get_runtime_settings 函数：根据标识查询单条数据，找不到时由调用方或本函数返回空值/错误。"""
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
    """build_settings_payload 函数：把内部数据整理成后续步骤需要的格式，避免业务逻辑到处重复拼装。"""
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
    """update_settings 函数：更新已有业务记录，只修改调用方明确传入的字段。"""
    flattened = _flatten_update_payload(payload)
    overrides = _load_db_overrides(db)
    changed_keys: list[str] = []
    audit_logs: list[SystemSettingAuditLog] = []
    for key, raw_value in flattened.items():
        definition = EDITABLE_SETTINGS[key]
        coerced = _coerce_setting_value(definition, raw_value)
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
            audit_logs.append(_build_setting_audit_log(key, "", serialized, definition["value_type"], user))
            continue
        if row.value != serialized or row.value_type != definition["value_type"]:
            old_value = row.value
            row.value = serialized
            row.value_type = definition["value_type"]
            row.updated_by = user.id
            changed_keys.append(key)
            audit_logs.append(_build_setting_audit_log(key, old_value, serialized, definition["value_type"], user))
    if audit_logs:
        db.add_all(audit_logs)
    db.commit()
    restart_required = any(EDITABLE_SETTINGS[key]["restart_required"] for key in changed_keys)
    return {
        **build_settings_payload(db),
        "changedKeys": changed_keys,
        "restartRequired": restart_required,
    }


def list_setting_audit_logs(
    db: Session,
    page_no: int = 1,
    page_size: int = 20,
    key: str | None = None,
) -> dict[str, Any]:
    """分页查询后台设置变更审计日志。"""

    safe_page_no = max(1, int(page_no or 1))
    safe_page_size = min(max(1, int(page_size or 20)), 100)
    query = db.query(SystemSettingAuditLog)
    normalized_key = (key or "").strip()
    if normalized_key:
        query = query.filter(SystemSettingAuditLog.key == normalized_key)

    total = query.count()
    rows = (
        query.order_by(SystemSettingAuditLog.created_at.desc(), SystemSettingAuditLog.id.desc())
        .offset((safe_page_no - 1) * safe_page_size)
        .limit(safe_page_size)
        .all()
    )
    return {
        "items": [_serialize_setting_audit_log(row) for row in rows],
        "total": total,
        "pageNo": safe_page_no,
        "pageSize": safe_page_size,
    }


def _serialize_setting_audit_log(row: SystemSettingAuditLog) -> dict[str, Any]:
    """把设置审计 ORM 记录转换为前端友好的字段。"""

    return {
        "id": row.id,
        "key": row.key,
        "oldValue": _redact_setting_audit_value(row.key, row.old_value),
        "newValue": _redact_setting_audit_value(row.key, row.new_value),
        "valueType": row.value_type,
        "changedBy": row.changed_by,
        "createdAt": to_shanghai_iso(row.created_at),
    }


def _build_setting_audit_log(
    key: str,
    old_value: str,
    new_value: str,
    value_type: str,
    user: User,
) -> SystemSettingAuditLog:
    """构造设置变更审计记录，集中控制审计字段。"""

    return SystemSettingAuditLog(
        key=key,
        old_value=_redact_setting_audit_value(key, old_value),
        new_value=_redact_setting_audit_value(key, new_value),
        value_type=value_type,
        changed_by=user.id,
    )


def _redact_setting_audit_value(key: str, value: str | None) -> str:
    """敏感配置审计只记录发生过变更，不保留明文值。"""

    if value in (None, ""):
        return ""
    definition = EDITABLE_SETTINGS.get(key)
    if definition and definition.get("sensitive"):
        return SENSITIVE_AUDIT_VALUE
    normalized_key = "".join(ch for ch in key.lower() if ch.isalnum())
    if any(part in normalized_key for part in SENSITIVE_SETTING_KEY_PARTS):
        return SENSITIVE_AUDIT_VALUE
    return str(value)


