from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from app.core.security_headers import SecurityHeadersMiddleware


class SecurityHeadersMiddlewareTest(unittest.TestCase):
    """验证统一安全响应头中间件。"""

    def _client(self) -> TestClient:
        """构造仅包含测试路由的最小应用。"""

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/ok")
        def ok():
            return {"status": "ok"}

        @app.get("/custom")
        def custom():
            return JSONResponse({"status": "ok"}, headers={"X-Frame-Options": "SAMEORIGIN"})

        return TestClient(app)

    def test_adds_baseline_security_headers(self) -> None:
        """普通 API 响应应带上浏览器安全基线头。"""

        response = self._client().get("/ok")

        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")
        self.assertIn("frame-ancestors", response.headers["content-security-policy"])
        self.assertIn("camera=()", response.headers["permissions-policy"])

    def test_preserves_existing_security_headers(self) -> None:
        """业务响应已显式设置安全头时，中间件不应覆盖。"""

        response = self._client().get("/custom")

        self.assertEqual(response.headers["x-frame-options"], "SAMEORIGIN")

    def test_adds_hsts_only_for_https_requests(self) -> None:
        """HSTS 只应在 HTTPS 或代理声明 HTTPS 时返回，避免本地 HTTP 调试被污染。"""

        client = self._client()
        http_response = client.get("/ok")
        https_response = client.get("/ok", headers={"X-Forwarded-Proto": "https"})

        self.assertNotIn("strict-transport-security", http_response.headers)
        self.assertEqual(https_response.headers["strict-transport-security"], "max-age=31536000; includeSubDomains")


if __name__ == "__main__":
    unittest.main()
