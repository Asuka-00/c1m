"""仅开发环境的私有接口（直接创建用户，供测试 / 脚本使用）。"""

from typing import Any

from fastapi import APIRouter

from app.core.deps import SessionDep
from app.core.schemas import StrictBody
from app.core.security import get_password_hash
from app.platform.users.models import User
from app.platform.users.schemas import UserPublic

router = APIRouter(tags=["private"], prefix="/private")


class PrivateUserCreate(StrictBody):
    username: str
    email: str | None = None
    password: str
    full_name: str
    is_verified: bool = False


@router.post("/users/", response_model=UserPublic)
def create_user(user_in: PrivateUserCreate, session: SessionDep) -> Any:
    """
    Create a new user.
    """

    user = User(
        username=user_in.username.lower(),
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=get_password_hash(user_in.password),
    )

    session.add(user)
    session.commit()

    return user
