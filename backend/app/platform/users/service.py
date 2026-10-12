from collections.abc import Callable
from typing import Any

from sqlmodel import Session, func, select

from app.core.security import get_password_hash, verify_password
from app.platform.rbac.permissions import ADMIN_ROLE, DEFAULT_USER_ROLE
from app.platform.rbac.service import assign_role
from app.platform.users.models import User
from app.platform.users.schemas import UserCreate, UserUpdate

#: hooks run after a user is created (registered by higher-level modules,
#: e.g. tenants creates the personal workspace); args: session, user
USER_CREATED_HOOKS: list[Callable[[Session, User], None]] = []


def create_user(
    *, session: Session, user_create: UserCreate, with_personal_tenant: bool = True
) -> User:
    db_obj = User.model_validate(
        user_create, update={"hashed_password": get_password_hash(user_create.password)}
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    # RBAC: every new user gets the default role; superusers also get admin
    assign_role(
        session, db_obj, ADMIN_ROLE if db_obj.is_superuser else DEFAULT_USER_ROLE
    )
    # Multi-tenancy: every new user (signup or admin-created) gets a personal tenant
    # where they are the owner. They can be invited to other tenants afterwards.
    if with_personal_tenant:
        for hook in USER_CREATED_HOOKS:
            hook(session, db_obj)
        session.refresh(db_obj)
    return db_obj


def update_user(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    extra_data = {}
    if "password" in user_data:
        password = user_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["hashed_password"] = hashed_password
    db_user.sqlmodel_update(user_data, update=extra_data)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


def get_user_by_email(*, session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    session_user = session.exec(statement).first()
    return session_user


# Dummy hash to use for timing attack prevention when user is not found
# This is an Argon2 hash of a random password, used to ensure constant-time comparison
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


def get_user_by_username(*, session: Session, username: str) -> User | None:
    return session.exec(
        select(User).where(func.lower(User.username) == username.lower())
    ).first()


def get_user_by_login(*, session: Session, login: str) -> User | None:
    """Login identifier: an email (contains '@') or a username."""
    if "@" in login:
        return get_user_by_email(session=session, email=login)
    return get_user_by_username(session=session, username=login)


def authenticate(*, session: Session, email: str, password: str) -> User | None:
    """`email` may also be a username (see get_user_by_login)."""
    db_user = get_user_by_login(session=session, login=email.strip())
    if not db_user:
        # Prevent timing attacks by running password verification even when user doesn't exist
        # This ensures the response time is similar whether or not the email exists
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    return db_user
