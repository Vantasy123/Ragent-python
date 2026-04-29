"""应用配置定义，集中读取环境变量和默认运行参数。"""

from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# 默认 SQLite 文件固定在项目 data 目录，避免从不同工作目录启动时生成多份数据库。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data" / "ragent_python.db"


class Settings(BaseSettings):
    """应用配置中心，统一从环境变量和 .env 读取运行参数。"""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    APP_NAME: str = "Ragent Python API"
    APP_VERSION: str = "1.0.0"
    DEBUG: str = "false"
    ENVIRONMENT: str = "production"
    API_PREFIX: str = ""

    DATABASE_URL: str = f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"

    REDIS_ENABLED: bool = True
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_KEY_PREFIX: str = "ragent"
    REDIS_SOCKET_TIMEOUT: float = 1.5
    CHAT_STOP_TTL_SECONDS: int = 60 * 60
    CHAT_CONTEXT_TTL_SECONDS: int = 60 * 60 * 24
    JWT_REVOKED_TTL_SECONDS: int = 60 * 60 * 24 * 7
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 120
    CHAT_MAX_CONCURRENCY_PER_USER: int = 3
    OPS_AGENT_MAX_CONCURRENCY: int = 2
    CONCURRENCY_COUNTER_TTL_SECONDS: int = 60 * 30

    JWT_SECRET: str = "ragent-python-secret"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7

    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    CHAT_MODEL: str = "qwen-plus"
    EMBEDDING_MODEL: str = "text-embedding-v3"
    TEMPERATURE: float = 0.7
    SILICONFLOW_API_KEY: str = ""
    OLLAMA_API_BASE: str = "http://localhost:11434"

    COLLECTION_NAME: str = "ragent_knowledge"
    VECTOR_DIMENSION: int = 1024
    VECTOR_BACKEND: str = "milvus"
    MILVUS_URI: str = "http://localhost:19530"
    MILVUS_TOKEN: str = ""

    DEFAULT_TOP_K: int = 5
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    RERANK_THRESHOLD: float = 0.7

    HISTORY_KEEP_TURNS: int = 4
    SUMMARY_ENABLED: bool = True
    SUMMARY_START_TURNS: int = 5
    SUMMARY_MAX_CHARS: int = 200
    TITLE_MAX_LENGTH: int = 30

    MAX_FILE_SIZE: int = 50 * 1024 * 1024
    MAX_REQUEST_SIZE: int = 100 * 1024 * 1024
    STORAGE_TYPE: str = "local"
    STORAGE_BASE_DIR: str = "uploads"

    AGENT_MAX_STEPS: int = 10
    AGENT_MAX_SUB_AGENTS: int = 4
    AGENT_PLANNING_MODEL: str = ""
    AGENT_EXECUTION_TIMEOUT: int = 120
    AGENT_REQUIRE_APPROVAL_FOR_WRITE: bool = True
    AGENT_EXECUTOR_ENABLED: bool = False
    AGENT_COMPOSE_DIR: str = "/app"
    AGENT_COMPOSE_PROJECT: str = "ragent-python"

    ALLOWED_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:8000",
            "http://frontend:80",
        ]
    )

    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_PASSWORD: str = "admin123"
    DEFAULT_ADMIN_NICKNAME: str = "Administrator"

    WEATHER_API_URL: str = "https://wttr.in"


settings = Settings()
