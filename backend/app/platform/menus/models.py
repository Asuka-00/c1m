"""菜单数据模型：系统菜单（注册表同步）与自定义菜单。"""

import uuid

from sqlmodel import Field, SQLModel


# ---------- Backend-driven menus / routes ----------
class MenuBase(SQLModel):
    key: str = Field(unique=True, index=True, max_length=100)
    title: str = Field(max_length=100)
    path: str | None = Field(default=None, max_length=255)  # None 表示分组节点
    icon: str | None = Field(default=None, max_length=50)  # lucide 图标名
    component: str | None = Field(default=None, max_length=100)  # 前端组件 key
    sort_order: int = 0
    permission: str | None = Field(default=None, max_length=100)  # 所需权限编码
    hidden: bool = False


class Menu(MenuBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    parent_id: uuid.UUID | None = Field(
        default=None, foreign_key="menu.id", ondelete="CASCADE", index=True
    )
