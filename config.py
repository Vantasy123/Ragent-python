"""
应用配置模块 (Application Configuration Module)

本模块使用 Pydantic Settings 管理 Ragent Python 应用的所有配置项。
配置项可以从环境变量、.env 文件或默认值中获取，支持类型验证和自动转换。

配置分类：
1. 应用基本信息：名称、版本、调试模式
2. 数据库配置：连接字符串
3. 认证配置：JWT 密钥和过期时间
4. AI 模型配置：OpenAI、SiliconFlow、Ollama 等
5. 向量数据库配置：集合名称、维度等
6. RAG 配置：检索参数、分块策略
7. 会话管理：历史轮数、摘要配置
8. 文件上传：大小限制
9. 安全配置：允许的源域名
10. 默认账户：管理员账户信息

环境变量支持：
- 所有配置项都可以通过环境变量覆盖
- 变量名与字段名相同，使用大写字母
- 示例：DATABASE_URL=postgresql://user:pass@localhost/db

.env 文件支持：
- 在项目根目录创建 .env 文件
- 格式：KEY=VALUE
- 会自动加载到配置中
"""

from __future__ import annotations

from typing import List  # 类型提示：列表类型

from pydantic import Field  # Pydantic 字段定义
from pydantic_settings import BaseSettings, SettingsConfigDict  # Pydantic 设置框架


class Settings(BaseSettings):
    """
    应用设置类。

    继承自 BaseSettings，提供配置项的定义、验证和加载功能。
    所有字段都有默认值，可以通过环境变量或 .env 文件覆盖。
    """

    # 配置模型设置：从 .env 文件加载，区分大小写
    model_config = SettingsConfigDict(
        env_file=".env",      # 指定环境变量文件
        case_sensitive=True   # 环境变量名区分大小写
    )

    # ========== 应用基本信息 ==========
    APP_NAME: str = "Ragent Python API"  # 应用名称，用于 API 文档标题
    APP_VERSION: str = "1.0.0"          # 应用版本，用于 API 文档版本
    DEBUG: str = "false"                # 调试模式开关（字符串类型）
    ENVIRONMENT: str = "production"     # Runtime environment: development / production
    API_PREFIX: str = ""                # API 前缀（通常为空）

    # ========== 数据库配置 ==========
    DATABASE_URL: str = "sqlite:///./ragent_python.db"  # 数据库连接字符串
    # 支持的格式：
    # - SQLite: sqlite:///./ragent_python.db
    # - PostgreSQL: postgresql://user:password@localhost/dbname
    # - MySQL: mysql://user:password@localhost/dbname

    # ========== 认证配置 ==========
    JWT_SECRET: str = "ragent-python-secret"  # JWT 签名密钥（生产环境必须修改）
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7     # JWT token 过期时间（7天）

    # ========== AI 模型配置 ==========
    # OpenAI 兼容接口配置（主要用于通义千问）
    OPENAI_API_KEY: str = ""                              # API 密钥
    OPENAI_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # API 基础 URL
    CHAT_MODEL: str = "qwen-plus"                         # 聊天模型名称
    EMBEDDING_MODEL: str = "text-embedding-v3"            # 嵌入模型名称
    TEMPERATURE: float = 0.7                              # 生成温度（0-1，控制随机性）

    # 备用模型提供商
    SILICONFLOW_API_KEY: str = ""                         # SiliconFlow API 密钥
    OLLAMA_API_BASE: str = "http://localhost:11434"       # Ollama 本地服务地址

    # ========== 向量数据库配置 ==========
    COLLECTION_NAME: str = "ragent_knowledge"             # 向量集合名称
    VECTOR_DIMENSION: int = 1024                          # 向量维度（取决于嵌入模型）

    # ========== RAG（检索增强生成）配置 ==========
    DEFAULT_TOP_K: int = 5                                # 默认检索文档数量
    CHUNK_SIZE: int = 500                                 # 文档分块大小（字符数）
    CHUNK_OVERLAP: int = 50                               # 分块重叠大小（字符数）
    RERANK_THRESHOLD: float = 0.7                         # 重排阈值（相似度阈值）

    # ========== 会话管理配置 ==========
    HISTORY_KEEP_TURNS: int = 4                           # 保留的历史对话轮数
    SUMMARY_ENABLED: bool = True                          # 是否启用对话摘要
    SUMMARY_START_TURNS: int = 5                          # 开始生成摘要的轮数
    SUMMARY_MAX_CHARS: int = 200                          # 摘要最大字符数
    TITLE_MAX_LENGTH: int = 30                            # 会话标题最大长度

    # ========== 文件上传配置 ==========
    MAX_FILE_SIZE: int = 50 * 1024 * 1024                 # 最大文件大小（50MB）
    MAX_REQUEST_SIZE: int = 100 * 1024 * 1024            # 最大请求大小（100MB）
    STORAGE_TYPE: str = "local"                          # 存储类型：local
    STORAGE_BASE_DIR: str = "uploads"                    # 本地上传目录

    # ========== 安全配置 ==========
    # CORS 允许的源域名列表
    ALLOWED_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",  # Vite 开发服务器默认端口
            "http://localhost:3000",  # React 开发服务器默认端口
            "http://localhost:8000",  # 可能的其他开发端口
        ]
    )

    # ========== 默认账户配置 ==========
    DEFAULT_ADMIN_USERNAME: str = "admin"                 # 默认管理员用户名
    DEFAULT_ADMIN_PASSWORD: str = "admin123"              # 默认管理员密码（生产环境必须修改）
    DEFAULT_ADMIN_NICKNAME: str = "Administrator"         # 默认管理员昵称

    # ========== 外部服务配置 ==========
    WEATHER_API_URL: str = "https://wttr.in"              # 天气 API 服务地址


# 创建全局设置实例
# 这个实例会在模块导入时创建，并从环境变量和 .env 文件中加载配置
settings = Settings()
