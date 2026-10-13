"""菜单接口模型：菜单 CRUD、菜单树节点、当前用户菜单。"""

import uuid

from sqlmodel import Field, SQLModel

from app.platform.menus.models import MenuBase


class MenuCreate(MenuBase):
    parent_id: uuid.UUID | None = None
    space: str = Field(
        default="workspace", schema_extra={"pattern": r"^(workspace|platform)$"}
    )


class MenuUpdate(SQLModel):
    title: str | None = Field(default=None, max_length=100)
    path: str | None = Field(default=None, max_length=255)
    icon: str | None = Field(default=None, max_length=50)
    component: str | None = Field(default=None, max_length=100)
    sort_order: int | None = None
    permission: str | None = Field(default=None, max_length=100)
    hidden: bool | None = None
    space: str | None = Field(
        default=None, schema_extra={"pattern": r"^(workspace|platform)$"}
    )
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
    # 菜单空间：workspace（租户工作区）/ platform（平台管理控制台）
    space: str = "workspace"


class PermNode(SQLModel):
    """统一权限树节点：菜单（kind=menu，type=MENU）或权限（kind=perm，type=MENU/BUTTON/API）。"""

    id: str
    # menu / perm / group（"其他权限"等虚拟分组）
    kind: str
    type: str
    key: str | None = None
    name: str
    code: str = ""
    path: str | None = None
    icon: str | None = None
    component: str | None = None
    sort_order: int = 0
    visible: bool = True
    status: str = "active"
    scope: str | None = None
    space: str | None = None
    description: str | None = None
    # 菜单：父菜单 id；权限：所属菜单 id
    menu_id: str | None = None
    children: list[PermNode] = []
