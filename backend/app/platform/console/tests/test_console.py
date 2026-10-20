"""平台管理控制台测试：仅超级用户、租户管理、以租户身份进入、日志与权限作用域。"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.platform.users import service as crud
from app.platform.users.schemas import UserCreate
from app.testing.user import create_owned_tenant
from app.testing.utils import (
    login_name,
    random_email,
    random_lower_string,
    username_for,
)

API = settings.API_V1_STR


def _user(client: TestClient, db: Session) -> tuple[str, dict[str, str]]:
    email, pw = random_email(), random_lower_string()
    _u = crud.create_user(
        session=db,
        user_create=UserCreate(email=email, username=username_for(email), password=pw),
    )
    create_owned_tenant(db, _u)
    tok = client.post(
        f"{API}/login/access-token",
        data={"username": login_name(email), "password": pw},
    ).json()["access_token"]
    return email, {"Authorization": f"Bearer {tok}"}


def _slug() -> str:
    return "t-" + random_lower_string()[:12]


def test_platform_api_superuser_only(client: TestClient, db: Session) -> None:
    _, h = _user(client, db)
    for path in (
        "/platform/tenants",
        "/platform/users/",
        "/platform/roles/",
        "/platform/permissions/",
        "/platform/menus/",
        "/platform/config/groups",
        "/platform/login-log",
        "/platform/ops-log",
        "/platform/audit",
        "/platform/notify-channels",
    ):
        assert client.get(f"{API}{path}", headers=h).status_code == 403, path
        assert client.get(f"{API}{path}").status_code == 401, path


def test_tenant_lifecycle(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    sh = superuser_token_headers
    owner_email, ho = _user(client, db)
    slug = _slug()
    r = client.post(
        f"{API}/platform/tenants",
        headers=sh,
        json={
            "name": "Acme",
            "slug": slug,
            "plan": "trial",
            "owner": username_for(owner_email),
        },
    )
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["plan"] == "trial" and t["owners"] == [username_for(owner_email)]
    tid = t["id"]
    # 内置租户角色模板自动创建
    roles = client.get(f"{API}/platform/tenants/{tid}/roles", headers=sh).json()
    assert {x["name"] for x in roles["data"]} >= {"owner", "admin", "member"}
    # 列表：搜索 + 筛选
    lst = client.get(
        f"{API}/platform/tenants", headers=sh, params={"q": slug, "plan": "trial"}
    ).json()
    assert lst["count"] == 1 and lst["data"][0]["member_count"] == 1
    # 成员与 owner 指定
    other_email, _ = _user(client, db)
    r = client.put(
        f"{API}/platform/tenants/{tid}/owner",
        headers=sh,
        json={"username": username_for(other_email)},
    )
    assert r.status_code == 200 and "owner" in r.json()["roles"]
    members = client.get(f"{API}/platform/tenants/{tid}/members", headers=sh).json()
    assert members["count"] == 2
    # 到期后非超级用户不能进入
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    r = client.patch(
        f"{API}/platform/tenants/{tid}", headers=sh, json={"expires_at": past}
    )
    assert r.status_code == 200
    r = client.get(f"{API}/tenants/{tid}", headers=ho)
    assert (
        r.status_code == 403 and r.json()["detail"]["message"] == "Tenant has expired"
    )
    # 停用
    r = client.patch(
        f"{API}/platform/tenants/{tid}",
        headers=sh,
        json={"status": "suspended", "expires_at": None, "plan": "enterprise"},
    )
    assert r.json()["status"] == "suspended" and r.json()["plan"] == "enterprise"
    assert client.get(f"{API}/tenants/{tid}", headers=ho).status_code == 403
    # 品牌覆盖
    r = client.patch(
        f"{API}/platform/tenants/{tid}/branding/branding",
        headers=sh,
        json={"values": {"app_name": "Acme MES"}},
    )
    assert r.status_code == 200, r.text
    b = client.get(f"{API}/platform/tenants/{tid}/branding", headers=sh).json()
    item = next(i for i in b["data"][0]["items"] if i["code"] == "app_name")
    assert item["value"] == "Acme MES" and item["overridden"]
    ops = client.get(
        f"{API}/platform/ops-log", headers=sh, params={"page_size": 100}
    ).json()["data"]
    mine = {o["action"] for o in ops if o["tenant_id"] == tid}
    assert {"tenant.create", "tenant.update", "tenant.owner", "tenant.branding"} <= mine


def test_enter_tenant_is_audited(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    sh = superuser_token_headers
    tid = client.post(
        f"{API}/platform/tenants", headers=sh, json={"name": "Imp", "slug": _slug()}
    ).json()["id"]
    r = client.post(f"{API}/platform/tenants/{tid}/enter", headers=sh)
    assert r.status_code == 200
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    me = client.get(f"{API}/menus/me", headers=h).json()
    assert me["tenant_id"] == tid
    ops = client.get(
        f"{API}/platform/ops-log", headers=sh, params={"action": "tenant.enter"}
    ).json()["data"]
    assert any(o["tenant_id"] == tid for o in ops)
    _, uh = _user(client, db)
    assert (
        client.post(f"{API}/platform/tenants/{tid}/enter", headers=uh).status_code
        == 403
    )


def test_login_log(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    email, _ = _user(client, db)
    client.post(
        f"{API}/login/access-token",
        data={"username": username_for(email), "password": "nope-nope"},
    )
    rows = client.get(
        f"{API}/platform/login-log",
        headers=superuser_token_headers,
        params={"q": username_for(email)},
    ).json()["data"]
    assert {r["success"] for r in rows} == {True, False}
    failed = client.get(
        f"{API}/platform/login-log",
        headers=superuser_token_headers,
        params={"q": username_for(email), "success": False},
    ).json()
    assert failed["count"] == 1 and failed["data"][0]["reason"] == "bad_credentials"


def test_cross_tenant_audit_and_channels(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    sh = superuser_token_headers
    r = client.get(f"{API}/platform/audit", headers=sh, params={"page_size": 5})
    assert r.status_code == 200 and len(r.json()["data"]) <= 5
    ops = client.get(
        f"{API}/platform/ops-log",
        headers=sh,
        params={"action": "audit.cross_tenant_read"},
    ).json()
    assert ops["count"] >= 1
    ch = client.get(f"{API}/platform/notify-channels", headers=sh).json()["data"]
    assert {c["code"] for c in ch} >= {"in_app"}
    r = client.put(
        f"{API}/platform/notify-channels/in_app", headers=sh, json={"enabled": False}
    )
    assert r.json()["enabled"] is False
    ch = client.get(f"{API}/platform/notify-channels", headers=sh).json()["data"]
    assert next(c for c in ch if c["code"] == "in_app")["enabled"] is False
    client.put(
        f"{API}/platform/notify-channels/in_app", headers=sh, json={"enabled": True}
    )
    assert (
        client.put(
            f"{API}/platform/notify-channels/nope", headers=sh, json={"enabled": True}
        ).status_code
        == 404
    )


def test_permission_scope_split(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    sh = superuser_token_headers
    code = f"platform:x{random_lower_string()[:6]}"
    r = client.post(
        f"{API}/platform/permissions/",
        headers=sh,
        json={"code": code, "scope": "tenant"},
    )
    assert r.status_code == 400
    perms = client.get(
        f"{API}/platform/permissions/", headers=sh, params={"q": "tenants:read"}
    ).json()["data"]
    pid = next(p["id"] for p in perms if p["code"] == "tenants:read")
    r = client.patch(
        f"{API}/platform/permissions/{pid}", headers=sh, json={"scope": "tenant"}
    )
    assert r.status_code == 400
    # 租户角色只能授予租户作用域权限
    _, ho = _user(client, db)
    tid = client.get(f"{API}/tenants/me", headers=ho).json()["data"][0]["tenant"]["id"]
    tree = client.get(f"{API}/tenants/{tid}/permission-tree", headers=ho).json()

    def walk(ns: list[dict]) -> set[str]:  # type: ignore[type-arg]
        return {
            c
            for n in ns
            for c in ([n["code"]] if n["kind"] == "perm" else [])
            + list(walk(n["children"]))
        }

    codes = walk(tree)
    assert "members:read" in codes and not codes & {"users:read", "tenants:write"}
    r = client.post(
        f"{API}/tenants/{tid}/roles",
        headers=ho,
        json={"name": "x", "permission_codes": ["tenants:write"]},
    )
    assert r.status_code == 400


def test_menu_space_validated(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    r = client.post(
        f"{API}/platform/menus/",
        headers=superuser_token_headers,
        json={"key": f"x-{random_lower_string()[:8]}", "title": "X", "space": "moon"},
    )
    assert r.status_code == 422
    plat = client.get(
        f"{API}/platform/menus/",
        headers=superuser_token_headers,
        params={"space": "platform", "page_size": 100},
    ).json()
    assert plat["count"] == 13 and {m["space"] for m in plat["data"]} == {"platform"}
