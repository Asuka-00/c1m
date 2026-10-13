"""Multi-tenancy tests: tenant resolution, membership/roles API, isolation (RLS: test_rls.py)."""

import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.platform.tenants.models import Tenant
from app.platform.users import service as crud
from app.platform.users.schemas import UserCreate
from app.testing.user import create_owned_tenant, user_authentication_headers
from app.testing.utils import (
    login_name,
    random_email,
    random_lower_string,
    username_for,
)

API = settings.API_V1_STR


def _user(client: TestClient, db: Session):  # type: ignore[no-untyped-def]
    email, pw = random_email(), random_lower_string()
    user = crud.create_user(
        session=db,
        user_create=UserCreate(email=email, username=username_for(email), password=pw),
    )
    create_owned_tenant(db, user)
    r = client.post(
        f"{API}/login/access-token",
        data={"username": login_name(email), "password": pw},
    )
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    tenant_id = client.get(f"{API}/tenants/me", headers=h).json()["data"][0]["tenant"][
        "id"
    ]
    return user, h, tenant_id


def test_new_users_get_no_personal_tenant(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    """任何途径创建的用户都不会自动获得个人工作区。"""
    email, pw = random_email(), random_lower_string()
    user = crud.create_user(
        session=db,
        user_create=UserCreate(email=email, username=username_for(email), password=pw),
    )
    h = user_authentication_headers(client=client, email=email, password=pw)
    assert client.get(f"{API}/tenants/me", headers=h).json()["count"] == 0
    name = "np_" + random_lower_string()[:8]
    u = client.post(
        f"{API}/platform/users/",
        headers=superuser_token_headers,
        json={"username": name, "password": pw},
    ).json()
    assert (
        client.get(
            f"{API}/platform/users/{u['id']}/tenants", headers=superuser_token_headers
        ).json()
        == []
    )
    assert user.id


def test_superuser_owns_default_tenant(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    mine = client.get(f"{API}/tenants/me", headers=superuser_token_headers).json()[
        "data"
    ]
    assert [(m["tenant"]["slug"], m["roles"]) for m in mine] == [("default", ["owner"])]


def test_cross_tenant_isolation(client: TestClient, db: Session) -> None:
    _, ha, ta = _user(client, db)
    _, hb, tb = _user(client, db)
    # B cannot see A's tenant / members / roles, nor select it via header
    assert client.get(f"{API}/tenants/{ta}", headers=hb).status_code == 404
    assert client.get(f"{API}/tenants/{ta}/members", headers=hb).status_code == 404
    assert client.get(f"{API}/tenants/{ta}/roles", headers=hb).status_code == 404
    assert (
        client.get(f"{API}/menus/me", headers={**hb, "X-Tenant-ID": ta}).status_code
        == 404
    )
    assert all(
        m["tenant"]["id"] != ta
        for m in client.get(f"{API}/tenants/me", headers=hb).json()["data"]
    )


def test_superuser_can_access_any_tenant(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    _, ha, ta = _user(client, db)
    hs = {**superuser_token_headers, "X-Tenant-ID": ta}
    assert client.get(f"{API}/tenants/{ta}/members", headers=hs).json()["count"] == 1
    assert client.get(f"{API}/menus/me", headers=hs).json()["tenant_id"] == ta


def test_members_roles_and_header_selection(client: TestClient, db: Session) -> None:
    owner, ho, t = _user(client, db)
    member, hm, personal = _user(client, db)
    r = client.post(
        f"{API}/tenants/{t}/members",
        headers=ho,
        json={"username": member.username, "roles": ["member"]},
    )
    assert r.status_code == 200 and r.json()["roles"] == ["member"]
    assert (
        client.post(
            f"{API}/tenants/{t}/members", headers=ho, json={"username": member.username}
        ).status_code
        == 409
    )

    # member now has 2 tenants -> no tenant resolved without header (or tid claim)
    assert client.get(f"{API}/menus/me", headers=hm).json()["tenant_id"] is None
    hmt = {**hm, "X-Tenant-ID": t}
    assert client.get(f"{API}/menus/me", headers=hmt).json()["tenant_id"] == t

    # member can read but not manage members or the tenant
    assert (
        client.post(
            f"{API}/tenants/{t}/members", headers=hm, json={"username": owner.username}
        ).status_code
        == 403
    )
    assert (
        client.patch(f"{API}/tenants/{t}", headers=hm, json={"name": "x"}).status_code
        == 403
    )
    assert client.get(f"{API}/tenants/{t}/members", headers=hm).json()["count"] == 2

    # promote to admin -> members:write; admin cannot grant owner
    r = client.put(
        f"{API}/tenants/{t}/members/{member.id}/roles",
        headers=ho,
        json={"roles": ["admin"]},
    )
    assert r.json()["roles"] == ["admin"]
    assert (
        "members:write"
        in client.get(f"{API}/menus/me", headers=hmt).json()["permissions"]
    )
    assert (
        client.put(
            f"{API}/tenants/{t}/members/{member.id}/roles",
            headers=hmt,
            json={"roles": ["owner"]},
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"{API}/tenants/{t}/members/{member.id}/roles",
            headers=ho,
            json={"roles": ["nope"]},
        ).status_code
        == 400
    )

    # last owner cannot be demoted/removed
    assert (
        client.put(
            f"{API}/tenants/{t}/members/{owner.id}/roles",
            headers=ho,
            json={"roles": ["member"]},
        ).status_code
        == 400
    )
    assert (
        client.delete(f"{API}/tenants/{t}/members/{owner.id}", headers=ho).status_code
        == 400
    )

    # remove member -> access gone
    assert (
        client.delete(f"{API}/tenants/{t}/members/{member.id}", headers=ho).status_code
        == 200
    )
    assert client.get(f"{API}/menus/me", headers=hmt).status_code == 404
    assert (
        client.get(f"{API}/menus/me", headers=hm).json()["tenant_id"] == personal
    )  # back to one tenant


def test_switch_tenant_token_claim(client: TestClient, db: Session) -> None:
    owner, ho, t = _user(client, db)
    member, hm, personal = _user(client, db)
    client.post(
        f"{API}/tenants/{t}/members", headers=ho, json={"username": member.username}
    )
    tok = client.post(f"{API}/tenants/{t}/switch", headers=hm).json()["access_token"]
    hs = {"Authorization": f"Bearer {tok}"}
    assert client.get(f"{API}/menus/me", headers=hs).json()["tenant_id"] == t
    # explicit header wins over the claim
    assert (
        client.get(f"{API}/menus/me", headers={**hs, "X-Tenant-ID": personal}).json()[
            "tenant_id"
        ]
        == personal
    )
    # cannot switch into a foreign tenant
    _, _, other = _user(client, db)
    assert client.post(f"{API}/tenants/{other}/switch", headers=hm).status_code == 404


def test_tenant_crud(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    email, h, _ = _user(client, db)
    sh = superuser_token_headers
    slug = f"acme-{random_lower_string()[:6]}"
    # 租户由平台创建（自助创建接口已移除），普通用户无权调用平台接口
    body = {"name": "Acme", "slug": slug}
    assert (
        client.post(f"{API}/platform/tenants", headers=h, json=body).status_code == 403
    )
    r = client.post(
        f"{API}/platform/tenants", headers=sh, json={**body, "owner": email.username}
    )
    assert r.status_code == 200
    tid = r.json()["id"]
    assert (
        client.post(
            f"{API}/platform/tenants", headers=sh, json={"name": "Acme", "slug": slug}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{API}/platform/tenants",
            headers=sh,
            json={"name": "Bad", "slug": "Bad Slug"},
        ).status_code
        == 422
    )
    assert (
        client.patch(f"{API}/tenants/{tid}", headers=h, json={"name": "Acme 2"}).json()[
            "name"
        ]
        == "Acme 2"
    )
    assert (
        client.patch(
            f"{API}/tenants/{tid}", headers=h, json={"status": "suspended"}
        ).status_code
        == 403
    )
    assert {
        x["tenant"]["slug"]
        for x in client.get(f"{API}/tenants/me", headers=h).json()["data"]
    } >= {slug}
    roles = {
        r["name"]
        for r in client.get(f"{API}/tenants/{tid}/roles", headers=h).json()["data"]
    }
    assert roles == {"owner", "admin", "member"}
    # platform admin may suspend; members are then locked out
    assert (
        client.patch(
            f"{API}/tenants/{tid}",
            headers=superuser_token_headers,
            json={"status": "suspended"},
        ).json()["status"]
        == "suspended"
    )
    assert (
        client.get(f"{API}/menus/me", headers={**h, "X-Tenant-ID": tid}).status_code
        == 403
    )
    assert (
        client.get(f"{API}/platform/tenants", headers=superuser_token_headers).json()[
            "count"
        ]
        >= 3
    )
    assert (
        client.delete(f"{API}/tenants/{tid}", headers=h).status_code == 403
    )  # suspended
    assert (
        client.delete(
            f"{API}/tenants/{tid}", headers=superuser_token_headers
        ).status_code
        == 200
    )
    assert db.get(Tenant, uuid.UUID(tid)) is None
