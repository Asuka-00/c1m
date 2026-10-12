from sqlmodel import Session, select

from app.core.config import settings
from app.platform.users import service as crud
from app.platform.users.models import User
from app.platform.users.schemas import UserCreate

# make sure all SQLModel models are imported (app.models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/fastapi/full-stack-fastapi-template/issues/28


def init_db(session: Session) -> None:
    # Tables should be created with Alembic migrations
    # But if you don't want to use migrations, create
    # the tables un-commenting the next lines
    # from sqlmodel import SQLModel

    # This works because the models are already imported and registered from app.models
    # SQLModel.metadata.create_all(engine)

    from app.platform.rbac.permissions import ADMIN_ROLE
    from app.platform.rbac.service import assign_role, seed_rbac

    seed_rbac(session)
    user = session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).first()
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            username=settings.FIRST_SUPERUSER_USERNAME or None,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
        )
        user = crud.create_user(
            session=session, user_create=user_in, with_personal_tenant=False
        )
    elif not user.username and settings.FIRST_SUPERUSER_USERNAME:
        user.username = settings.FIRST_SUPERUSER_USERNAME
        session.add(user)
        session.commit()
    assign_role(session, user, ADMIN_ROLE)
    # Multi-tenancy: default tenant, FIRST_SUPERUSER is its owner
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
    # keep every tenant's default roles in sync with new default permissions
    from app.platform.tenants.models import Tenant
    from app.platform.tenants.service import seed_tenant_roles

    for t in session.exec(select(Tenant)).all():
        seed_tenant_roles(session, t)
    session.commit()
