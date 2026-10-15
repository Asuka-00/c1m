"""安全工具：JWT 签发、密码哈希与校验（argon2；哈希参数变化时在登录时升级）。"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import settings

password_hash = PasswordHash((Argon2Hasher(),))


ALGORITHM = "HS256"


def create_access_token(
    subject: str | Any,
    expires_delta: timedelta,
    tenant_id: Any | None = None,
    impersonation: bool = False,
) -> str:
    """签发访问令牌。

    Args:
        subject: 令牌主体（用户 id）。
        expires_delta: 有效期。
        tenant_id: 可选，写入 ``tid`` 声明作为默认租户。
        impersonation: 是否为平台“以租户身份进入”的模拟令牌（写入 ``imp`` 声明，
            令牌只能访问 ``tid`` 租户，且不能调用平台接口）。

    Returns:
        编码后的 JWT。
    """
    expire = datetime.now(UTC) + expires_delta
    to_encode: dict[str, Any] = {"exp": expire, "sub": str(subject)}
    if tenant_id is not None:
        to_encode["tid"] = str(tenant_id)
    if impersonation:
        to_encode["imp"] = True
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
    """校验密码。

    Args:
        plain_password: 明文密码。
        hashed_password: 已存储的哈希。

    Returns:
        ``(是否匹配, 需要升级时的新哈希或 None)``。
    """
    return password_hash.verify_and_update(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """计算密码哈希。"""
    return password_hash.hash(password)
