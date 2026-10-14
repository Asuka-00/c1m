"""用户名主身份：租户内建用户、独占租户才可重置密码、平台分配租户、操作人记用户名。"""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.platform.tenants.tests.test_tenants import _user
from app.testing.utils import random_lower_string

API = settings.API_V1_STR


def _login(client: TestClient, ident: str, pw: str) -> int:
    return client.post(
        f"{API}/login/access-token", data={"username": ident, "password": pw}
    ).status_code


def test_tenant_owner_creates_and_manages_user(client: TestClient, db: Session) -> None:
    owner, ho, t = _user(client, db)
    name, pw = "Op_" + random_lower_string()[:8], random_lower_string()
    body = {
        "username": name,
        "full_name": "操作员",
        "password": pw,
        "roles": ["member"],
    }
    r = client.post(f"{API}/tenants/{t}/members/new", headers=ho, json=body)
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["username"] == name.lower() and m["email"] is None and m["sole_tenant"]
    assert _login(client, name, pw) == 200
    # 用户名不区分大小写唯一
    dup = client.post(
        f"{API}/tenants/{t}/members/new",
        headers=ho,
        json={**body, "username": name.upper()},
    )
    assert dup.status_code == 409
    assert dup.json()["detail"] == "User with this username already exists"
    # 不能创建超级用户（D65 补充 4：多余字段 422 unknown_field）
    r2 = client.post(
        f"{API}/tenants/{t}/members/new",
        headers=ho,
        json={**body, "username": name + "x", "is_superuser": True},
    )
    assert r2.status_code == 422
    assert r2.json()["detail"][0]["loc"] == ["body", "is_superuser"]
    assert r2.json()["detail"][0]["code"] == "unknown_field"
    r2 = client.post(
        f"{API}/tenants/{t}/members/new",
        headers=ho,
        json={**body, "username": name + "x"},
    )
    assert r2.status_code == 200
    assert _login(client, name + "x", pw) == 200
    me = client.post(
        f"{API}/login/access-token", data={"username": name + "x", "password": pw}
    ).json()["access_token"]
    assert (
        client.get(f"{API}/users/me", headers={"Authorization": f"Bearer {me}"}).json()[
            "is_superuser"
        ]
        is False
    )
    # 独占本租户：可重置密码
    uid = m["user_id"]
    new_pw = random_lower_string()
    r = client.patch(
        f"{API}/tenants/{t}/members/{uid}/user", headers=ho, json={"password": new_pw}
    )
    assert r.status_code == 200, r.text
    assert _login(client, name, new_pw) == 200
    # 加入第二个租户后：拒绝重置
    other, ho2, t2 = _user(client, db)
    assert (
        client.post(
            f"{API}/tenants/{t2}/members", headers=ho2, json={"username": name}
        ).status_code
        == 200
    )
    r = client.patch(
        f"{API}/tenants/{t}/members/{uid}/user", headers=ho, json={"password": pw}
    )
    assert r.status_code == 403
    lst = client.get(f"{API}/tenants/{t}/members", headers=ho).json()["data"]
    assert {x["username"]: x["sole_tenant"] for x in lst}[name.lower()] is False
    # 普通成员无 members:write
    plain, hm, _ = _user(client, db)
    client.post(
        f"{API}/tenants/{t}/members", headers=ho, json={"username": plain.username}
    )
    hm = {**hm, "X-Tenant-ID": t}
    assert (
        client.post(
            f"{API}/tenants/{t}/members/new",
            headers=hm,
            json={**body, "username": name + "y"},
        ).status_code
        == 403
    )


def test_platform_assign_user_tenants_and_actor_username(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    sh = superuser_token_headers
    _, _, t1 = _user(client, db)
    _, _, t2 = _user(client, db)
    name = "pu_" + random_lower_string()[:8]
    u = client.post(
        f"{API}/platform/users/",
        headers=sh,
        json={"username": name, "password": random_lower_string()},
    ).json()
    assert u["email"] is None and u["updated_by"] in (
        None,
        settings.FIRST_SUPERUSER_USERNAME,
    )
    # 平台创建的用户自带个人工作区（owner）；整体设置时须保留
    personal = [
        {"tenant_id": x["tenant_id"], "roles": x["roles"]}
        for x in client.get(
            f"{API}/platform/users/{u['id']}/tenants", headers=sh
        ).json()
    ]
    items = [
        *personal,
        {"tenant_id": t1, "roles": ["member"]},
        {"tenant_id": t2, "roles": []},
    ]
    r = client.put(
        f"{API}/platform/users/{u['id']}/tenants", headers=sh, json={"items": items}
    )
    assert r.status_code == 200, r.text
    got = {x["tenant_id"]: x["roles"] for x in r.json()}
    assert t1 in got and t2 in got and got[t1] == ["member"]
    r = client.put(
        f"{API}/platform/users/{u['id']}/tenants",
        headers=sh,
        json={"items": [*personal, {"tenant_id": t1, "roles": ["member", "owner"]}]},
    )
    assert t2 not in {x["tenant_id"] for x in r.json()}
    g = client.get(f"{API}/platform/users/{u['id']}/tenants", headers=sh).json()
    assert {x["tenant_id"]: x["roles"] for x in g}[t1] == ["member", "owner"]
    # 平台操作日志的操作人是用户名
    ops = client.get(
        f"{API}/platform/ops-log", headers=sh, params={"page_size": 5}
    ).json()["data"]
    assert ops and all("@" not in (o.get("actor_username") or "") for o in ops)
    # 修改记录更新人为用户名
    upd = client.patch(
        f"{API}/platform/users/{u['id']}", headers=sh, json={"full_name": "X"}
    ).json()
    assert upd["updated_by"] == settings.FIRST_SUPERUSER_USERNAME
    # 邮箱重复 → 409
    e = "dup_" + random_lower_string()[:6] + "@example.com"
    ok = client.post(
        f"{API}/platform/users/",
        headers=sh,
        json={"username": name + "e", "email": e, "password": random_lower_string()},
    )
    assert ok.status_code == 200
    d = client.post(
        f"{API}/platform/users/",
        headers=sh,
        json={"username": name + "f", "email": e.upper(), "password": "x" * 10},
    )
    assert d.status_code == 409
    assert d.json()["detail"] == "User with this email already exists"
