from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.core.config import settings
from app.platform.rbac.models import Role
from app.platform.rbac.permissions import DEFAULT_PERMISSIONS, SERVICE_ONLY_PERMISSIONS
from app.platform.rbac.service import has_permissions
from app.platform.users import service as crud
from app.platform.users.models import User
from app.platform.users.schemas import UserCreate
from app.testing.user import create_owned_tenant
from app.testing.utils import (
    login_name,
    random_email,
    random_lower_string,
    username_for,
)

API = settings.API_V1_STR


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    r = client.post(
        f"{API}/login/access-token",
        data={"username": login_name(email), "password": password},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _new_user(client: TestClient, db: Session) -> tuple[User, dict[str, str]]:
    email, pw = random_email(), random_lower_string()
    user = crud.create_user(
        session=db,
        user_create=UserCreate(email=email, username=username_for(email), password=pw),
    )
    create_owned_tenant(db, user)
    return user, _login(client, email, pw)


def test_seeded_roles(db: Session) -> None:
    admin = db.exec(
        select(Role).where(Role.name == "admin", col(Role.tenant_id).is_(None))
    ).one()
    user = db.exec(
        select(Role).where(Role.name == "user", col(Role.tenant_id).is_(None))
    ).one()
    # 服务账号专用权限（mes.eap:write D54-1、mes.eap:read_master D65）不进平台 admin
    assert {p.code for p in admin.permissions} == set(
        DEFAULT_PERMISSIONS
    ) - SERVICE_ONLY_PERMISSIONS
    # business access is tenant-level; the platform "user" role carries no perms
    assert {p.code for p in user.permissions} == set()


def test_superuser_has_admin_role(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    r = client.get(f"{API}/users/me/permissions", headers=superuser_token_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["is_superuser"] is True
    assert "admin" in body["roles"]
    assert "roles:write" in body["permissions"]


def test_new_user_gets_user_role(client: TestClient, db: Session) -> None:
    _, headers = _new_user(client, db)
    body = client.get(f"{API}/users/me/permissions", headers=headers).json()
    assert body["roles"] == ["user"]
    assert "users:read" not in body["permissions"]


def test_normal_user_cannot_manage_roles(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    assert (
        client.get(
            f"{API}/platform/roles/", headers=normal_user_token_headers
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{API}/platform/roles/",
            headers=normal_user_token_headers,
            json={"name": "x"},
        ).status_code
        == 403
    )
    assert (
        client.get(
            f"{API}/platform/permissions/", headers=normal_user_token_headers
        ).status_code
        == 403
    )


def test_role_and_permission_crud(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    h = superuser_token_headers
    code = f"reports:{random_lower_string()[:8]}"
    p = client.post(
        f"{API}/platform/permissions/",
        headers=h,
        json={"code": code, "description": "d"},
    )
    assert p.status_code == 200
    pid = p.json()["id"]
    assert (
        client.post(
            f"{API}/platform/permissions/", headers=h, json={"code": code}
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"{API}/platform/permissions/{pid}", headers=h, json={"description": "new"}
        ).json()["description"]
        == "new"
    )

    name = f"role-{random_lower_string()[:8]}"
    r = client.post(
        f"{API}/platform/roles/",
        headers=h,
        json={"name": name, "permission_codes": ["users:read"]},
    )
    assert r.status_code == 200
    rid = r.json()["id"]
    assert [x["code"] for x in r.json()["permissions"]] == ["users:read"]

    r = client.post(f"{API}/platform/roles/{rid}/permissions/{pid}", headers=h)
    assert {x["code"] for x in r.json()["permissions"]} == {"users:read", code}
    r = client.delete(f"{API}/platform/roles/{rid}/permissions/{pid}", headers=h)
    assert {x["code"] for x in r.json()["permissions"]} == {"users:read"}

    assert (
        client.patch(
            f"{API}/platform/roles/{rid}", headers=h, json={"description": "x"}
        ).json()["description"]
        == "x"
    )
    assert any(
        x["name"] == name
        for x in client.get(
            f"{API}/platform/roles/", headers=h, params={"q": name}
        ).json()["data"]
    )
    assert client.delete(f"{API}/platform/roles/{rid}", headers=h).status_code == 200
    assert client.get(f"{API}/platform/roles/{rid}", headers=h).status_code == 404
    assert (
        client.delete(f"{API}/platform/permissions/{pid}", headers=h).status_code == 200
    )


def test_assign_role_grants_permission(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    h = superuser_token_headers
    user, uh = _new_user(client, db)
    assert client.get(f"{API}/platform/users/", headers=uh).status_code == 403

    role = client.post(
        f"{API}/platform/roles/",
        headers=h,
        json={
            "name": f"viewer-{random_lower_string()[:8]}",
            "permission_codes": ["users:read"],
        },
    ).json()
    r = client.post(f"{API}/platform/users/{user.id}/roles/{role['id']}", headers=h)
    assert r.status_code == 200
    assert {x["name"] for x in r.json()} == {"user", role["name"]}

    # 平台角色授予的权限：可读平台用户，但不能删除（缺 users:delete）
    me = client.get(f"{API}/users/me/permissions", headers=uh).json()
    assert "users:read" in me["permissions"]
    assert client.get(f"{API}/platform/users/", headers=uh).status_code == 200
    assert (
        client.delete(f"{API}/platform/users/{user.id}", headers=uh).status_code == 403
    )
    assert client.get(f"{API}/platform/roles/", headers=uh).status_code == 403
    # 停用角色后不再授予权限
    client.patch(
        f"{API}/platform/roles/{role['id']}", headers=h, json={"status": "disabled"}
    )
    me = client.get(f"{API}/users/me/permissions", headers=uh).json()
    assert "users:read" not in me["permissions"]
    assert client.get(f"{API}/platform/users/", headers=uh).status_code == 403

    r = client.delete(f"{API}/platform/users/{user.id}/roles/{role['id']}", headers=h)
    assert {x["name"] for x in r.json()} == {"user"}
    assert client.get(f"{API}/platform/users/", headers=uh).status_code == 403


def test_removing_tenant_roles_blocks_members(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    user, uh = _new_user(client, db)
    tenant = client.get(f"{API}/tenants/me", headers=uh).json()["data"][0]["tenant"]
    assert (
        client.get(f"{API}/tenants/{tenant['id']}/members", headers=uh).status_code
        == 200
    )
    # owner -> no tenant roles (another owner is added first, a tenant needs one)
    h = superuser_token_headers
    other, _ = _new_user(client, db)
    assert (
        client.post(
            f"{API}/tenants/{tenant['id']}/members",
            headers=uh,
            json={"username": other.username, "roles": ["owner"]},
        ).status_code
        == 200
    )
    r = client.put(
        f"{API}/tenants/{tenant['id']}/members/{user.id}/roles",
        headers=h,
        json={"roles": []},
    )
    assert r.status_code == 200, r.text
    hdr = {**uh, "X-Tenant-ID": tenant["id"]}
    assert (
        client.get(f"{API}/tenants/{tenant['id']}/members", headers=hdr).status_code
        == 403
    )
    assert client.get(f"{API}/menus/me", headers=hdr).json()["permissions"] == []


def test_superuser_bypass_without_roles() -> None:
    u = User(
        email=random_email(),
        username="su_" + random_lower_string()[:10],
        hashed_password="x",
        is_superuser=True,
    )
    assert u.roles == []
    assert has_permissions(u, "anything:at_all")


def test_seed_syncs_old_permission_description(db: Session) -> None:
    """旧库重跑 initial_data：内置权限的旧说明同步为当前三语说明；手工说明保留。"""
    from app.platform.rbac.labels import permission_description
    from app.platform.rbac.models import Permission
    from app.platform.rbac.service import seed_rbac

    p = db.exec(
        select(Permission).where(Permission.code == "mes.eap:read_master")
    ).one()
    q = db.exec(select(Permission).where(Permission.code == "members:read")).one()
    old_p, old_q = p.description, q.description
    p.description = "Allows: EAP master data read (service account)"
    q.description = "custom text"
    db.add(p)
    db.add(q)
    db.commit()
    seed_rbac(db)
    seed_rbac(db)  # 幂等
    db.refresh(p)
    db.refresh(q)
    assert p.description == permission_description("mes.eap:read_master")
    assert "|" in p.description and "EAP" in p.description
    assert q.description == "custom text"
    q.description = old_q
    db.add(q)
    db.commit()
    assert old_p is not None
