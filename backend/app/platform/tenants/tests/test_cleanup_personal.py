"""一次性清理脚本：只删除明确的自动个人工作区且无业务数据者。"""

from sqlalchemy import text
from sqlmodel import Session

from app.cleanup_personal_tenants import cleanup
from app.core.db import admin_engine
from app.platform.tenants.service import create_tenant
from app.platform.users import service as crud
from app.platform.users.schemas import UserCreate
from app.testing.utils import random_lower_string


def _user(db: Session, name: str):  # type: ignore[no-untyped-def]
    return crud.create_user(
        session=db,
        user_create=UserCreate(username=name, password=random_lower_string()),
    )


def test_cleanup_personal_tenants(db: Session) -> None:
    a, b, c = (_user(db, f"{x}{random_lower_string()[:6]}") for x in "abc")
    empty = create_tenant(db, f"{a.username}'s workspace", f"{a.username}-0a1b2c", a)
    busy = create_tenant(db, f"{b.username}'s workspace", f"{b.username}-0d1e2f", b)
    # 名称像个人工作区，但 owner 不匹配 → 不是候选
    fake = create_tenant(db, "zz's workspace", f"zz-{random_lower_string()[:6]}", c)
    with admin_engine.begin() as conn:
        item = conn.execute(text("SELECT id FROM configitem LIMIT 1")).scalar()
        conn.execute(
            text(
                "INSERT INTO tenantconfigvalue (id, tenant_id, item_id, value) "
                "VALUES (gen_random_uuid(), :t, :i, 'null')"
            ),
            {"t": busy.id, "i": item},
        )
        dry = cleanup(conn, apply=False)
    assert empty.slug in dry["deleted"] and busy.slug in dry["kept"]
    assert fake.slug not in dry["deleted"] + dry["kept"]
    with admin_engine.begin() as conn:
        res = cleanup(conn, apply=True)
        left = {
            r[0]
            for r in conn.execute(
                text("SELECT slug FROM tenant WHERE id IN (:a, :b, :c)"),
                {"a": empty.id, "b": busy.id, "c": fake.id},
            )
        }
    assert left == {busy.slug, fake.slug}
    assert a.username in res["orphans"] and b.username not in res["orphans"]
