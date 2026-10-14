"""D83 补充二：prestart 的 app.initial_data 可重复执行、不覆盖已有用户数据、不改库权限。"""

import inspect
import re

from sqlmodel import Session, select

from app import bootstrap, initial_data
from app.core.config import settings
from app.core.db import engine
from app.platform.users.models import User


def test_init_db_repeatable_keeps_passwords() -> None:
    uname = (settings.FIRST_SUPERUSER_USERNAME or "admin").lower()
    with Session(engine) as s:
        u = s.exec(select(User).where(User.username == uname)).one()
        before = (u.hashed_password, u.email, u.full_name, u.is_active)
        count = len(s.exec(select(User)).all())
    initial_data.init()
    initial_data.init()
    with Session(engine) as s:
        u = s.exec(select(User).where(User.username == uname)).one()
        assert (u.hashed_password, u.email, u.full_name, u.is_active) == before
        assert len(s.exec(select(User)).all()) == count


def test_init_db_no_role_or_grant_sql() -> None:
    src = inspect.getsource(bootstrap) + inspect.getsource(initial_data)
    assert not re.search(r"\b(ALTER\s+ROLE|CREATE\s+ROLE|GRANT|REVOKE)\b", src, re.I)
    assert "setup_db_roles" not in src
