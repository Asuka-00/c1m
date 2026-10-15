"""菜单接口模型：菜单 CRUD、菜单树节点、当前用户菜单。"""

import uuid

from sqlmodel import Field, SQLModel

from app.platform.menus.models import MenuBase


class MenuCreate(MenuBase):
    parent_id: uuid.UUID | None = None


class MenuUpdate(SQLModel):
    title: str | None = Field(default=None, max_length=100)
    path: str | None = Field(default=None, max_length=255)
    icon: str | None = Field(default=None, max_length=50)
    component: str | None = Field(default=None, max_length=100)
    sort_order: int | None = None
    permission: str | None = Field(default=None, max_length=100)
    hidden: bool | None = None
    parent_id: uuid.UUID | None = None


class MenuPublic(MenuBase):
    id: uuid.UUID
    parent_id: uuid.UUID | None = None


class MenusPublic(SQLModel):
    data: list[MenuPublic]
    count: int


class MenuNode(SQLModel):
    key: str
    title: str
    path: str | None = None
    icon: str | None = None
    component: str | None = None
    permission: str | None = None
    children: list[MenuNode] = []


class MyMenus(SQLModel):
    menus: list[MenuNode]
    # 调用者无权打开的已知路径（前端显示 403 而非 404）
    forbidden_paths: list[str] = []
    permissions: list[str]
    tenant_id: uuid.UUID | None = None
    is_superuser: bool = False
