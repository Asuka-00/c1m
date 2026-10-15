"""用户服务：创建、更新、查询与认证。"""

from typing import Any

from sqlmodel import Session, func, select

from app.core.security import get_password_hash, verify_password
from app.platform.rbac.permissions import ADMIN_ROLE, DEFAULT_USER_ROLE
from app.platform.rbac.service import assign_role
from app.platform.users.models import User
from app.platform.users.schemas import UserCreate, UserUpdate


def create_user(*, session: Session, user_create: UserCreate) -> User:
    """创建用户。

    分配默认平台角色（超级用户为 admin，否则 user）。不会自动创建任何租户：
    租户（工厂 / 站点级作用域）由平台管理员创建，用户须被显式加入租户。

    Args:
        session: 数据库会话。
        user_create: 用户数据。

    Returns:
        新用户。
    """
    db_obj = User.model_validate(
        user_create, update={"hashed_password": get_password_hash(user_create.password)}
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    # RBAC：新用户获得默认角色；超级用户获得 admin
    assign_role(
        session, db_obj, ADMIN_ROLE if db_obj.is_superuser else DEFAULT_USER_ROLE
    )
    return db_obj


def update_user(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    """更新用户（提供密码时重新哈希）。"""
    user_data = user_in.model_dump(exclude_unset=True)
    if user_data.get("username", "") is None:  # 用户名必填，不能清空
        user_data.pop("username")
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
    """按邮箱精确查询用户。"""
    statement = select(User).where(func.lower(User.email) == email.lower())
    session_user = session.exec(statement).first()
    return session_user


# 用户不存在时使用的哑哈希，防止时序攻击
# 这是随机密码的 Argon2 哈希，保证比较耗时恒定
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


def get_user_by_username(*, session: Session, username: str) -> User | None:
    """按用户名查询用户（不区分大小写）。"""
    return session.exec(
        select(User).where(func.lower(User.username) == username.lower())
    ).first()


def identity_conflict(
    session: Session,
    username: str | None,
    email: str | None,
    exclude_id: Any = None,
) -> str | None:
    """用户名 / 邮箱重复检查（用户名不区分大小写；邮箱仅在填写时检查）。

    Args:
        session: 数据库会话。
        username: 用户名。
        email: 邮箱（可空）。
        exclude_id: 排除的用户 id（更新自身时）。

    Returns:
        冲突时的错误信息（前端按 backend.<detail> 翻译），否则 None。
    """
    if username:
        other = get_user_by_username(session=session, username=username)
        if other and other.id != exclude_id:
            return "User with this username already exists"
    if email:
        other = session.exec(
            select(User).where(func.lower(User.email) == email.lower())
        ).first()
        if other and other.id != exclude_id:
            return "User with this email already exists"
    return None


def authenticate(*, session: Session, username: str, password: str) -> User | None:
    """校验用户名与密码（仅支持用户名登录，不接受邮箱）。

    Args:
        session: 数据库会话。
        username: 用户名（不区分大小写）。
        password: 明文密码。

    Returns:
        认证成功的用户，否则 None。
    """
    db_user = get_user_by_username(session=session, username=username.strip())
    if not db_user:
        # 即使用户不存在也执行一次密码校验以防时序攻击，
        # 使用户名存在与否的响应时间相近
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
