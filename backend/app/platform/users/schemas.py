"""用户接口模型：创建、注册、更新、改密与输出。"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, EmailStr, StringConstraints
from sqlmodel import Field, SQLModel

from app.platform.users.models import USERNAME_RE, UserBase

# 以小写存储，使唯一索引实际上不区分大小写
Username = Annotated[
    str, StringConstraints(pattern=USERNAME_RE), AfterValidator(str.lower)
]


# 创建时通过 API 接收的属性
class UserCreate(UserBase):
    username: Username = Field(max_length=50)
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(SQLModel):
    email: EmailStr | None = Field(default=None, max_length=255)
    username: Username | None = Field(default=None, max_length=50)
    is_active: bool | None = None
    is_superuser: bool | None = None
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    username: Username | None = Field(default=None, max_length=50)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# 通过 API 返回的属性，id 必有
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None
    # 平台角色（编码）；仅管理列表填充
    role_names: list[str] = []


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
