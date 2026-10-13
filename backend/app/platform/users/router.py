"""用户管理与个人资料接口。"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlmodel import Session, col, select

from app.core.config import settings
from app.core.deps import SessionDep
from app.core.models import Message, get_datetime_utc
from app.core.pagination import ListParamsDep, paginate
from app.core.security import get_password_hash, verify_password
from app.platform.auth.deps import CurrentUser, platform_api_router, require_permissions
from app.platform.auth.service import generate_new_account_email, send_email
from app.platform.rbac.models import UserRole
from app.platform.rbac.schemas import UserPermissionsPublic
from app.platform.rbac.service import has_permissions, user_permission_codes
from app.platform.users import service as crud
from app.platform.users.models import User
from app.platform.users.schemas import (
    UpdatePassword,
    UserCreate,
    UserPublic,
    UserRegister,
    UsersPublic,
    UserUpdate,
    UserUpdateMe,
)

router = APIRouter(prefix="/users", tags=["users"])
# 用户管理（仅在平台空间 /platform/users 下挂载）；本路由只保留自助接口（me / signup）
admin_router = APIRouter(prefix="/users", tags=["users"])


def _check_username(
    session: Session, username: str | None, exclude_id: uuid.UUID | None = None
) -> None:
    if not username:
        return
    other = crud.get_user_by_username(session=session, username=username)
    if other and other.id != exclude_id:
        raise HTTPException(
            status_code=409, detail="User with this username already exists"
        )


@admin_router.get(
    "/",
    dependencies=[Depends(require_permissions("users:read"))],
    response_model=UsersPublic,
)
def read_users(
    session: SessionDep,
    params: ListParamsDep,
    is_active: bool | None = None,
    is_superuser: bool | None = None,
    role_id: uuid.UUID | None = None,
    username: str | None = None,
    full_name: str | None = None,
) -> Any:
    """
    Retrieve users (paginated; sort_by: email, username, full_name, created_at, updated_at,
    is_active, is_superuser; q searches email/username/full_name; filters: is_active,
    is_superuser, role_id = platform role, username (username or email contains),
    full_name (contains)).
    """
    stmt = select(User)
    if username:
        like = f"%{username}%"
        stmt = stmt.where(
            or_(col(User.username).ilike(like), col(User.email).ilike(like))
        )
    if full_name:
        stmt = stmt.where(col(User.full_name).ilike(f"%{full_name}%"))
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    if is_superuser is not None:
        stmt = stmt.where(User.is_superuser == is_superuser)
    if role_id is not None:
        stmt = stmt.where(
            col(User.id).in_(
                select(UserRole.user_id).where(UserRole.role_id == role_id)
            )
        )
    users, count = paginate(
        session,
        stmt,
        params,
        {
            "email": User.email,
            "username": User.username,
            "full_name": User.full_name,
            "created_at": User.created_at,
            "updated_at": User.updated_at,
            "is_active": User.is_active,
            "is_superuser": User.is_superuser,
        },
        ("created_at", "desc"),
        User.id,
        search=[User.email, User.username, User.full_name],
    )

    users_public = [
        UserPublic.model_validate(
            user, update={"role_names": sorted(r.name for r in user.roles)}
        )
        for user in users
    ]
    return UsersPublic(data=users_public, count=count)


@admin_router.post(
    "/",
    dependencies=[Depends(require_permissions("users:write"))],
    response_model=UserPublic,
)
def create_user(
    *, session: SessionDep, current_user: CurrentUser, user_in: UserCreate
) -> Any:
    """
    Create new user.
    """
    _guard_superuser(current_user, None, user_in.is_superuser)
    user = crud.get_user_by_email(session=session, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )
    _check_username(session, user_in.username)

    user = crud.create_user(session=session, user_create=user_in)
    if settings.emails_enabled and user_in.email:
        email_data = generate_new_account_email(
            email_to=user_in.email, username=user_in.email, password=user_in.password
        )
        send_email(
            email_to=user_in.email,
            subject=email_data.subject,
            html_content=email_data.html_content,
        )
    return user


@router.patch("/me", response_model=UserPublic)
def update_user_me(
    *, session: SessionDep, user_in: UserUpdateMe, current_user: CurrentUser
) -> Any:
    """
    Update own user.
    """

    _check_username(session, user_in.username, current_user.id)
    if user_in.email:
        existing_user = crud.get_user_by_email(session=session, email=user_in.email)
        if existing_user and existing_user.id != current_user.id:
            raise HTTPException(
                status_code=409, detail="User with this email already exists"
            )
    user_data = user_in.model_dump(exclude_unset=True)
    current_user.sqlmodel_update(user_data)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return current_user


@router.patch("/me/password", response_model=Message)
def update_password_me(
    *, session: SessionDep, body: UpdatePassword, current_user: CurrentUser
) -> Any:
    """
    Update own password.
    """
    verified, _ = verify_password(body.current_password, current_user.hashed_password)
    if not verified:
        raise HTTPException(status_code=400, detail="Incorrect password")
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=400, detail="New password cannot be the same as the current one"
        )
    hashed_password = get_password_hash(body.new_password)
    current_user.hashed_password = hashed_password
    session.add(current_user)
    session.commit()
    return Message(message="Password updated successfully")


@router.get("/me", response_model=UserPublic)
def read_user_me(current_user: CurrentUser) -> Any:
    """
    Get current user.
    """
    return current_user


@router.get("/me/permissions", response_model=UserPermissionsPublic)
def read_user_me_permissions(current_user: CurrentUser) -> Any:
    """
    Get current user's roles and effective permissions.
    """
    return UserPermissionsPublic(
        user_id=current_user.id,
        is_superuser=current_user.is_superuser,
        roles=sorted(r.name for r in current_user.roles),
        permissions=sorted(user_permission_codes(current_user)),
    )


@router.delete("/me", response_model=Message)
def delete_user_me(session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Delete own user.
    """
    if current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="Super users are not allowed to delete themselves"
        )
    session.delete(current_user)
    session.commit()
    return Message(message="User deleted successfully")


@router.post("/signup", response_model=UserPublic)
def register_user(session: SessionDep, user_in: UserRegister) -> Any:
    """
    Create new user without the need to be logged in.
    """
    user = crud.get_user_by_email(session=session, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system",
        )
    user_create = UserCreate.model_validate(user_in)
    user = crud.create_user(session=session, user_create=user_create)
    return user


@admin_router.get("/{user_id}", response_model=UserPublic)
def read_user_by_id(
    user_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> Any:
    """
    Get a specific user by id.
    """
    user = session.get(User, user_id)
    if user == current_user:
        return user
    if not has_permissions(current_user, "users:read"):
        raise HTTPException(
            status_code=403,
            detail="The user doesn't have enough privileges",
        )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@admin_router.patch(
    "/{user_id}",
    dependencies=[Depends(require_permissions("users:write"))],
    response_model=UserPublic,
)
def update_user(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    user_in: UserUpdate,
) -> Any:
    """
    Update a user.
    """

    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="The user with this id does not exist in the system",
        )
    _guard_superuser(current_user, db_user, user_in.is_superuser)
    _check_username(session, user_in.username, user_id)
    if user_in.email:
        existing_user = crud.get_user_by_email(session=session, email=user_in.email)
        if existing_user and existing_user.id != user_id:
            raise HTTPException(
                status_code=409, detail="User with this email already exists"
            )

    db_user.updated_at = get_datetime_utc()
    db_user.updated_by = current_user.email
    db_user = crud.update_user(session=session, db_user=db_user, user_in=user_in)
    return db_user


@admin_router.delete(
    "/{user_id}", dependencies=[Depends(require_permissions("users:delete"))]
)
def delete_user(
    session: SessionDep, current_user: CurrentUser, user_id: uuid.UUID
) -> Message:
    """
    Delete a user.
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user == current_user:
        raise HTTPException(
            status_code=403, detail="Super users are not allowed to delete themselves"
        )
    _guard_superuser(current_user, user, None)
    session.delete(user)
    session.commit()
    return Message(message="User deleted successfully")


def _guard_superuser(
    actor: User, target: User | None, want_superuser: bool | None
) -> None:
    """非超级用户（仅持平台权限）不能创建 / 修改 / 删除超级用户，也不能授予超级用户。

    Raises:
        HTTPException: 越权（403）。
    """
    if actor.is_superuser:
        return
    if want_superuser or (target is not None and target.is_superuser):
        raise HTTPException(
            status_code=403, detail="Only superusers can manage superuser accounts"
        )


# 平台空间别名：/platform/users/...（仅超级用户）
platform_router = platform_api_router(admin_router)
