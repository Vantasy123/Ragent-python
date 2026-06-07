"""HTTP 安全响应头中间件。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


DEFAULT_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Content-Security-Policy": "frame-ancestors 'none'; base-uri 'self'",
    "Cross-Origin-Opener-Policy": "same-origin",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """为所有 HTTP 响应补齐浏览器安全基线头。"""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """处理请求并在响应阶段补充安全头。"""

        response = await call_next(request)
        for header, value in DEFAULT_SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if _is_https_request(request):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


def _is_https_request(request: Request) -> bool:
    """识别 HTTPS 请求；反向代理部署时优先信任标准转发头。"""

    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if forwarded_proto:
        return forwarded_proto.split(",", 1)[0].strip().lower() == "https"
    return request.url.scheme == "https"
