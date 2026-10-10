from sqlmodel import Session, create_engine, select

from app import crud
from app.core.config import settings
from app.models import User, UserCreate

engine = create_engine(str(settings.DATABASE_URL), pool_pre_ping=True)
# Privileged engine (table owner) - only for migrations, tests setup, maintenance
admin_engine = create_engine(settings.migration_database_url, pool_pre_ping=True)


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

    from app.rbac import ADMIN_ROLE, assign_role, seed_rbac

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
    from app.menus import seed_menus
    from app.tenancy import add_member, ensure_default_tenant, get_membership

    seed_menus(session)
    from app.sysconfig import seed_config

    seed_config(session)
    tenant = ensure_default_tenant(session)
    if not get_membership(session, tenant.id, user.id):
        add_member(session, tenant, user, ["owner"])
        session.commit()
