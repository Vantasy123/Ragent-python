from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers.auth import router as auth_router
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.redis_client import get_redis_client
from app.domain.models import User
from app.services import auth as auth_service
from app.services.runtime_state import _local_counters, _local_values
from app.services.security import hash_password


class LoginRateLimitTest(unittest.TestCase):
    """验证登录失败限速，降低暴力破解和账号枚举风险。"""

    def setUp(self) -> None:
        """创建独立内存库，并把运行时状态固定为本地降级模式。"""

        self.original_limit = auth_service.LOGIN_FAILURE_LIMIT
        self.original_window = auth_service.LOGIN_FAILURE_WINDOW_SECONDS
        self.original_lock = auth_service.LOGIN_LOCK_SECONDS
        self.original_redis_enabled = settings.REDIS_ENABLED
        auth_service.LOGIN_FAILURE_LIMIT = 3
        auth_service.LOGIN_FAILURE_WINDOW_SECONDS = 60
        auth_service.LOGIN_LOCK_SECONDS = 60
        settings.REDIS_ENABLED = False
        get_redis_client.cache_clear()
        _local_counters.clear()
        _local_values.clear()

        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.user = User(
            id="user-1",
            username="admin",
            nickname="管理员",
            password_hash=hash_password("CorrectPassword2026!"),
            role="admin",
            is_active=True,
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self) -> None:
        """恢复全局状态，避免影响其他测试。"""

        self.db.close()
        auth_service.LOGIN_FAILURE_LIMIT = self.original_limit
        auth_service.LOGIN_FAILURE_WINDOW_SECONDS = self.original_window
        auth_service.LOGIN_LOCK_SECONDS = self.original_lock
        settings.REDIS_ENABLED = self.original_redis_enabled
        get_redis_client.cache_clear()
        _local_counters.clear()
        _local_values.clear()

    def test_failed_login_locks_identity_and_blocks_correct_password(self) -> None:
        """连续失败达到阈值后，同一账号和来源在锁定期内不能继续尝试。"""

        for _ in range(auth_service.LOGIN_FAILURE_LIMIT - 1):
            with self.assertRaises(ValueError):
                auth_service.login(self.db, "admin", "wrong", client_host="127.0.0.1")

        with self.assertRaises(auth_service.LoginRateLimitExceeded):
            auth_service.login(self.db, "admin", "wrong", client_host="127.0.0.1")
        with self.assertRaises(auth_service.LoginRateLimitExceeded):
            auth_service.login(self.db, "admin", "CorrectPassword2026!", client_host="127.0.0.1")

    def test_successful_login_clears_previous_failures(self) -> None:
        """成功登录应清理失败计数，避免一次误输长期影响正常用户。"""

        for _ in range(auth_service.LOGIN_FAILURE_LIMIT - 1):
            with self.assertRaises(ValueError):
                auth_service.login(self.db, "admin", "wrong", client_host="127.0.0.1")

        payload = auth_service.login(self.db, "admin", "CorrectPassword2026!", client_host="127.0.0.1")
        with self.assertRaises(ValueError):
            auth_service.login(self.db, "admin", "wrong", client_host="127.0.0.1")

        self.assertIn("token", payload)

    def test_login_router_returns_429_with_retry_after(self) -> None:
        """HTTP 登录接口在锁定时应返回 429，并告知客户端重试时间。"""

        app = FastAPI()
        app.include_router(auth_router)
        app.dependency_overrides[get_db] = lambda: self.db
        client = TestClient(app)

        responses = [
            client.post("/auth/login", json={"username": "admin", "password": "wrong"})
            for _ in range(auth_service.LOGIN_FAILURE_LIMIT)
        ]

        self.assertEqual(responses[-1].status_code, 429)
        self.assertEqual(responses[-1].headers["retry-after"], str(auth_service.LOGIN_LOCK_SECONDS))
        self.assertIn("登录失败次数过多", responses[-1].json()["detail"])


if __name__ == "__main__":
    unittest.main()
