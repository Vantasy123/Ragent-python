from __future__ import annotations

import unittest

from app.core.config import settings
from app.services.security import validate_production_security_settings


class ProductionSecuritySettingsTest(unittest.TestCase):
    """验证生产环境启动前的关键凭证门禁。"""

    def setUp(self) -> None:
        """保存全局 settings，避免测试之间互相影响。"""

        self.original_environment = settings.ENVIRONMENT
        self.original_debug = settings.DEBUG
        self.original_jwt_secret = settings.JWT_SECRET
        self.original_admin_password = settings.DEFAULT_ADMIN_PASSWORD

    def tearDown(self) -> None:
        """恢复全局 settings。"""

        settings.ENVIRONMENT = self.original_environment
        settings.DEBUG = self.original_debug
        settings.JWT_SECRET = self.original_jwt_secret
        settings.DEFAULT_ADMIN_PASSWORD = self.original_admin_password

    def test_production_rejects_default_credentials(self) -> None:
        """生产环境不能使用默认 JWT 密钥和默认管理员密码。"""

        settings.ENVIRONMENT = "production"
        settings.DEBUG = "false"
        settings.JWT_SECRET = "ragent-python-secret"
        settings.DEFAULT_ADMIN_PASSWORD = "admin123"

        with self.assertRaisesRegex(RuntimeError, "JWT_SECRET.*DEFAULT_ADMIN_PASSWORD"):
            validate_production_security_settings()

    def test_production_accepts_strong_credentials(self) -> None:
        """生产环境强密钥和强管理员密码应通过启动校验。"""

        settings.ENVIRONMENT = "production"
        settings.DEBUG = "false"
        settings.JWT_SECRET = "ragent-production-secret-32-chars-min"
        settings.DEFAULT_ADMIN_PASSWORD = "StrongAdminPassword2026!"

        validate_production_security_settings()

    def test_production_rejects_example_placeholders(self) -> None:
        """生产环境复制示例占位值但未替换时应启动失败。"""

        settings.ENVIRONMENT = "production"
        settings.DEBUG = "false"
        settings.JWT_SECRET = "replace-with-at-least-32-random-characters"
        settings.DEFAULT_ADMIN_PASSWORD = "replace-with-a-strong-admin-password"

        with self.assertRaisesRegex(RuntimeError, "占位值"):
            validate_production_security_settings()

    def test_debug_environment_allows_local_defaults(self) -> None:
        """调试环境保留本地默认值，避免开发启动成本升高。"""

        settings.ENVIRONMENT = "production"
        settings.DEBUG = "true"
        settings.JWT_SECRET = "ragent-python-secret"
        settings.DEFAULT_ADMIN_PASSWORD = "admin123"

        validate_production_security_settings()


if __name__ == "__main__":
    unittest.main()
