import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.platform.users import service as crud
from app.platform.users.models import User
from app.platform.users.schemas import UserCreate, UserUpdate
from app.testing.utils import (
    login_name,
    random_email,
    random_lower_string,
    username_for,
)


def user_authentication_headers(
    *, client: TestClient, email: str, password: str
) -> dict[str, str]:
    data = {"username": login_name(email), "password": password}

    r = client.post(f"{settings.API_V1_STR}/login/access-token", data=data)
    response = r.json()
    auth_token = response["access_token"]
    headers = {"Authorization": f"Bearer {auth_token}"}
    return headers


def create_random_user(db: Session) -> User:
    email = random_email()
    password = random_lower_string()
    user_in = UserCreate(email=email, username=username_for(email), password=password)
    user = crud.create_user(session=db, user_create=user_in)
    return user


def authentication_token_from_email(
    *, client: TestClient, email: str, db: Session
) -> dict[str, str]:
    """
    Return a valid token for the user with given email.

    If the user doesn't exist it is created first.
    """
    password = random_lower_string()
    user = crud.get_user_by_email(session=db, email=email)
    if not user:
        user_in_create = UserCreate(
            email=email, username=username_for(email), password=password
        )
        user = crud.create_user(session=db, user_create=user_in_create)
    else:
        user_in_update = UserUpdate(password=password)
        if not user.id:
            raise Exception("User id not set")
        user = crud.update_user(session=db, db_user=user, user_in=user_in_update)

    return user_authentication_headers(client=client, email=email, password=password)


def create_owned_tenant(db: Session, owner: User) -> uuid.UUID:
    """测试用：创建一个以 ``owner`` 为所有者的租户（系统不再自动创建个人工作区）。"""
    from app.platform.tenants.service import create_tenant

    slug = "t-" + random_lower_string()[:12]
    return create_tenant(db, f"{owner.username} tenant", slug, owner=owner).id
