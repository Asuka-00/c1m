"""平台权限授权、平台菜单过滤、菜单停用、租户模拟令牌与内置名称测试。"""

import jwt
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core import security
from app.core.config import settings
from app.platform.auth.deps import platform_permission
from app.platform.menus.models import Menu
from app.platform.rbac.labels import permission_label
from app.platform.rbac.models import Permission
from app.platform.rbac.permissions import DEFAULT_PERMISSIONS
from app.platform.users import service as crud
from app.platform.users.schemas import UserCreate
from app.testing.utils import random_email, random_lower_string

API = settings.API_V1_STR


def _user_with(
    client: TestClient, su: dict[str, str], db: Session, codes: list[str]
) -> tuple[str, dict[str, str]]:
    """创建持有给定平台权限（经新建平台角色）的普通用户，返回 (id, 认证头)。"""
    email, pw = random_email(), random_lower_string()
    user = crud.create_user(
        session=db, user_create=UserCreate(email=email, password=pw)
    )
    if codes:
        role = client.post(
            f"{API}/platform/roles/",
            headers=su,
            json={"name": f"r{random_lower_string()[:8]}", "permission_codes": codes},
        ).json()
        r = client.put(
            f"{API}/platform/users/{user.id}/roles",
            headers=su,
            json={"role_ids": [role["id"]]},
        )
        assert r.status_code == 200
    tok = client.post(
        f"{API}/login/access-token", data={"username": email, "password": pw}
    ).json()["access_token"]
    return str(user.id), {"Authorization": f"Bearer {tok}"}


def test_platform_permission_mapping() -> None:
    """平台路径 -> 权限编码映射。"""
    assert platform_permission("GET", "/api/v1/platform/users/") == "users:read"
    assert platform_permission("PATCH", "/api/v1/platform/users/{id}") == "users:write"
    assert (
        platform_permission("DELETE", "/api/v1/platform/users/{id}") == "users:delete"
    )
    assert (
        platform_permission("PUT", "/api/v1/platform/users/{id}/roles") == "roles:write"
    )
    assert (
        platform_permission("GET", "/api/v1/platform/permission-tree") == "roles:read"
    )
    assert (
        platform_permission("POST", "/api/v1/platform/tenants/{id}/enter")
        == "tenants:write"
    )
    assert (
        platform_permission("PATCH", "/api/v1/platform/tenants/{id}/branding/{c}")
        == "platform.config:write"
    )
    assert (
        platform_permission("GET", "/api/v1/platform/ops-log") == "platform.audit:read"
    )
    assert platform_permission("GET", "/api/v1/platform/unknown") is None


def test_platform_roles_grant_access(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """持有平台权限即可访问对应平台接口与菜单；不能越权管理超级用户。"""
    su = superuser_token_headers
    _, none = _user_with(client, su, db, [])
    assert client.get(f"{API}/platform/users/", headers=none).status_code == 403
    assert (
        client.get(
            f"{API}/menus/me", headers=none, params={"space": "platform"}
        ).status_code
        == 403
    )
    assert (
        client.get(f"{API}/menus/me", headers=none).json()["platform_access"] is False
    )

    _, h = _user_with(client, su, db, ["users:read", "users:write"])
    assert client.get(f"{API}/platform/users/", headers=h).status_code == 200
    assert client.get(f"{API}/platform/roles/", headers=h).status_code == 403
    assert client.get(f"{API}/menus/me", headers=h).json()["platform_access"] is True
    pm = client.get(f"{API}/menus/me", headers=h, params={"space": "platform"}).json()
    paths = {c["path"] for g in pm["menus"] for c in g["children"]}
    assert paths == {"/platform/users"}
    assert "/platform/roles" in pm["forbidden_paths"]
    # 不能创建 / 修改超级用户
    body = {"email": random_email(), "password": "x" * 10, "is_superuser": True}
    assert (
        client.post(f"{API}/platform/users/", headers=h, json=body).status_code == 403
    )
    su_id = client.get(f"{API}/users/me", headers=su).json()["id"]
    r = client.patch(
        f"{API}/platform/users/{su_id}", headers=h, json={"full_name": "x"}
    )
    assert r.status_code == 403


def test_enter_tenant_impersonation(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """进入租户签发短期模拟令牌：仅能访问该租户，不能调用平台接口；退出记入日志。"""
    su = superuser_token_headers
    slug = f"imp-{random_lower_string()[:6]}"
    t = client.post(
        f"{API}/platform/tenants", headers=su, json={"name": "Imp", "slug": slug}
    ).json()
    other = client.post(
        f"{API}/platform/tenants",
        headers=su,
        json={"name": "Other", "slug": f"o{slug}"},
    ).json()
    _, h = _user_with(client, su, db, ["tenants:read", "tenants:write"])
    r = client.post(f"{API}/platform/tenants/{t['id']}/enter", headers=h)
    assert r.status_code == 200
    tok = r.json()["access_token"]
    claims = jwt.decode(tok, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
    assert claims["imp"] is True and claims["tid"] == t["id"]
    assert claims["exp"] - claims.get("iat", claims["exp"] - 1) <= 60 * 60
    ih = {"Authorization": f"Bearer {tok}"}
    me = client.get(f"{API}/menus/me", headers=ih).json()
    assert me["tenant_id"] == t["id"] and me["platform_access"] is False
    assert client.get(f"{API}/platform/tenants", headers=ih).status_code == 403
    assert (
        client.get(
            f"{API}/menus/me", headers={**ih, "X-Tenant-ID": other["id"]}
        ).status_code
        == 403
    )
    assert client.get(f"{API}/tenants/{t['id']}/members", headers=ih).status_code == 200
    assert (
        client.post(f"{API}/platform/tenants/{t['id']}/exit", headers=h).status_code
        == 200
    )
    for action in ("tenant.enter", "tenant.exit"):
        log = client.get(
            f"{API}/platform/ops-log", headers=su, params={"action": action}
        ).json()["data"]
        assert any(str(x.get("target_id")) == t["id"] for x in log), action


def test_disabled_menu_hidden_and_denied(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """停用的菜单对超级用户也隐藏，其路径进入 forbidden_paths。"""
    su = superuser_token_headers
    m = db.exec(select(Menu).where(Menu.key == "notifications")).one()
    assert (
        client.patch(
            f"{API}/platform/menus/{m.id}", headers=su, json={"status": "disabled"}
        ).status_code
        == 200
    )
    try:
        me = client.get(f"{API}/menus/me", headers=su).json()

        def walk(ns: list[dict]) -> set[str]:
            return {n["path"] for n in ns} | {
                p for n in ns for p in walk(n["children"])
            }

        assert "/notifications" not in walk(me["menus"])
        assert "/notifications" in me["forbidden_paths"]
        tree = client.get(f"{API}/platform/permission-tree", headers=su).json()
        flat = []
        stack = list(tree)
        while stack:
            n = stack.pop()
            flat.append(n)
            stack += n["children"]
        assert any(
            n["key"] == "notifications" and n["status"] == "disabled" for n in flat
        )
    finally:
        client.patch(
            f"{API}/platform/menus/{m.id}", headers=su, json={"status": "active"}
        )


def test_builtin_names_and_links(db: Session) -> None:
    """内置权限均有三语名称并已补齐 name；tenant:manage 挂到租户设置菜单。"""
    for code in DEFAULT_PERMISSIONS:
        lbl = permission_label(code)
        assert lbl and all(lbl.split("|")), code
    perms = {p.code: p for p in db.exec(select(Permission))}
    assert all(perms[c].name for c in DEFAULT_PERMISSIONS)
    cfg = db.exec(select(Menu).where(Menu.key == "config")).one()
    assert perms["tenant:manage"].menu_id == cfg.id
