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


class MenuTab(SQLModel):
    """合并菜单的页签（原独立菜单）。"""

    key: str
    title: str
    # 原独立菜单路径（旧链接重定向到 合并页?tab=key）
    path: str | None = None
    component: str | None = None
    permission: str | None = None


class MenuNode(SQLModel):
    key: str
    title: str
    path: str | None = None
    icon: str | None = None
    component: str | None = None
    # 权限编码；多个以逗号分隔表示“任一即可”（合并菜单）
    permission: str | None = None
    # 合并菜单的页签（已按权限过滤）
    tabs: list[MenuTab] = []
    children: list[MenuNode] = []


class MyMenus(SQLModel):
    menus: list[MenuNode]
    # 调用者无权打开的已知路径（前端显示 403 而非 404）
    forbidden_paths: list[str] = []
    # 已并入合并菜单的旧路径 -> 新路径（含 ?tab=）
    redirects: dict[str, str] = {}
    permissions: list[str]
    tenant_id: uuid.UUID | None = None
    is_superuser: bool = False
