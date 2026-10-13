"""系统初始化（幂等）：RBAC、首个超级用户、菜单、系统配置、默认租户。"""

from sqlmodel import Session, select

# 必须先注册全部表 / 关系 / MES 规格
from app import models as _models  # noqa: F401
from app.core.config import settings
from app.platform.users import service as crud
from app.platform.users.models import User
from app.platform.users.schemas import UserCreate


def init_db(session: Session) -> None:
    """初始化基础数据，可重复执行。

    依次：同步默认权限与平台角色 → 创建/补全首个超级用户并授予 admin →
    同步菜单注册表 → 同步系统配置 → 确保默认租户且超级用户为 owner →
    同步每个租户的默认租户角色（新增权限自动下发）。

    Args:
        session: 数据库会话（使用 owner 或已设置租户上下文的连接）。
    """
    # 表应通过 Alembic 迁移创建
    # 如不使用迁移，可取消下面几行注释直接建表
    # （仅用于本地试验）
    # from sqlmodel import SQLModel

    # 模型已由 app.models 导入并注册，所以可以直接 create_all
    # SQLModel.metadata.create_all(engine)

    from app.platform.rbac.permissions import ADMIN_ROLE
    from app.platform.rbac.service import assign_role, seed_rbac

    seed_rbac(session)
    uname = (settings.FIRST_SUPERUSER_USERNAME or "admin").lower()
    user = session.exec(select(User).where(User.username == uname)).first()
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            username=uname,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
        )
        user = crud.create_user(session=session, user_create=user_in)
    assign_role(session, user, ADMIN_ROLE)
    # 多租户：默认租户，FIRST_SUPERUSER 为其 owner
    from app.platform.menus.service import seed_menus
    from app.platform.tenants.service import (
        add_member,
        ensure_default_tenant,
        get_membership,
    )

    seed_menus(session)
    from app.platform.config.service import seed_config

    seed_config(session)
    tenant = ensure_default_tenant(session)
    if not get_membership(session, tenant.id, user.id):
        add_member(session, tenant, user, ["owner"])
        session.commit()
    # 让每个租户的默认角色同步新增的默认权限
    from app.platform.tenants.models import Tenant
    from app.platform.tenants.service import seed_tenant_roles

    for t in session.exec(select(Tenant)).all():
        seed_tenant_roles(session, t)
    session.commit()
