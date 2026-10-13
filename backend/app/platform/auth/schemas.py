"""认证接口模型：访问令牌与 JWT 载荷。"""

from sqlmodel import SQLModel


# 包含访问令牌的 JSON 载荷
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# JWT 令牌内容
class TokenPayload(SQLModel):
    sub: str | None = None
    tid: str | None = None
    # 平台“以租户身份进入”签发的短期模拟令牌
    imp: bool = False
