from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import unittest

from app.core.config import settings
from app.services.security import create_token, decode_token


def _b64url(data: bytes) -> str:
    """生成测试用 JWT 片段，保持和生产编码规则一致。"""

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _signed_token(header: dict, payload: dict) -> str:
    """按当前 JWT 密钥构造测试令牌，用于覆盖异常 header 和 payload。"""

    header_segment = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_segment = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        settings.JWT_SECRET.encode("utf-8"),
        f"{header_segment}.{payload_segment}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{header_segment}.{payload_segment}.{_b64url(signature)}"


class JwtSecurityTest(unittest.TestCase):
    """验证 JWT 解码阶段的生产安全边界。"""

    def test_create_token_round_trip(self) -> None:
        """系统签发的标准令牌应能正常解码。"""

        token = create_token({"sub": "user-1", "username": "admin", "role": "admin"}, expires_in_minutes=5)

        payload = decode_token(token)

        self.assertEqual(payload["sub"], "user-1")
        self.assertEqual(payload["username"], "admin")
        self.assertIn("jti", payload)

    def test_rejects_signed_token_with_unsupported_algorithm(self) -> None:
        """即使签名正确，也不能接受非白名单算法，避免算法混淆风险。"""

        token = _signed_token(
            {"alg": "RS256", "typ": "JWT"},
            {"sub": "user-1", "jti": "token-1", "exp": int(time.time()) + 300},
        )

        with self.assertRaisesRegex(ValueError, "algorithm"):
            decode_token(token)

    def test_rejects_signed_token_without_jti(self) -> None:
        """缺少 jti 的令牌无法进入撤销校验链路，应在解码阶段拒绝。"""

        token = _signed_token(
            {"alg": "HS256", "typ": "JWT"},
            {"sub": "user-1", "exp": int(time.time()) + 300},
        )

        with self.assertRaisesRegex(ValueError, "jti"):
            decode_token(token)

    def test_rejects_malformed_or_non_object_token_parts(self) -> None:
        """畸形令牌和非对象 JSON 片段应统一拒绝，避免后续代码收到异常结构。"""

        array_header = _signed_token(
            ["HS256", "JWT"],  # type: ignore[arg-type]
            {"sub": "user-1", "jti": "token-1", "exp": int(time.time()) + 300},
        )

        with self.assertRaisesRegex(ValueError, "Malformed"):
            decode_token("not-a-jwt")
        with self.assertRaisesRegex(ValueError, "header"):
            decode_token(array_header)

    def test_rejects_missing_or_invalid_exp(self) -> None:
        """exp 必须是整数时间戳，不能接受缺失或字符串占位。"""

        token = _signed_token(
            {"alg": "HS256", "typ": "JWT"},
            {"sub": "user-1", "jti": "token-1", "exp": "soon"},
        )

        with self.assertRaisesRegex(ValueError, "exp"):
            decode_token(token)


if __name__ == "__main__":
    unittest.main()
