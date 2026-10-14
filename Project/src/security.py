"""密码哈希与会话 token。

- 密码用 PBKDF2-HMAC-SHA256 加盐哈希（标准库 hashlib 就有，不额外引依赖）；
- 登录成功后发一个随机 token，存 Redis（带过期时间），用它换 user_id。
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

ITERATIONS = 200_000
SALT_BYTES = 16


def make_salt() -> str:
    return secrets.token_hex(SALT_BYTES)


def hash_password(password: str, salt: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), ITERATIONS)
    return dk.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    actual = hash_password(password, salt)
    # 用 compare_digest 做定长比较，避免时序侧信道
    return hmac.compare_digest(actual, expected_hash)


def new_token() -> str:
    return os.urandom(32).hex()
