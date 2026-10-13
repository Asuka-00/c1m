"""用户数据模型。"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from pydantic import EmailStr
from sqlmodel import Field, Relationship, SQLModel

from app.core.models import get_datetime_utc
from app.platform.rbac.models import Role, UserRole

# 共享属性
# 用户名（主身份、登录名）；不含 '@'，避免与邮箱混淆
USERNAME_RE = r"^[A-Za-z0-9_.-]{3,50}$"


class UserBase(SQLModel):
    # 用户名是主身份：必填、唯一（以小写存储，另有 lower(username) 唯一索引）
    username: str = Field(unique=True, index=True, max_length=50)
    # 邮箱可选；填写时唯一
    email: EmailStr | None = Field(
        default=None, unique=True, index=True, max_length=255
    )
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# 数据库模型，表名由类名推断
class User(UserBase, table=True):
    # 用户名不区分大小写唯一
    __table_args__ = (
        sa.Index("uq_user_username_lower", sa.text("lower(username)"), unique=True),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(default_factory=get_datetime_utc)
    # 最近一次由管理员修改的时间与操作人（用户名）
    updated_at: datetime | None = None
    updated_by: str | None = Field(default=None, max_length=255)
    roles: list[Role] = Relationship(back_populates="users", link_model=UserRole)
