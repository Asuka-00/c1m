"""Multi-tenancy tests: tenant resolution, membership/roles API, isolation (RLS: test_rls.py)."""

import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.platform.tenants.models import Tenant
from app.platform.users import service as crud
from app.platform.users.schemas import UserCreate
from app.testing.utils import random_email, random_lower_string

API = settings.API_V1_STR


def _user(client: TestClient, db: Session):  # type: ignore[no-untyped-def]
    email, pw = random_email(), random_lower_string()
    user = crud.create_user(
        session=db, user_create=UserCreate(email=email, password=pw)
    )
    r = client.post(
        f"{API}/login/access-token", data={"username": email, "password": pw}
    )
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    tenant_id = client.get(f"{API}/tenants/me", headers=h).json()["data"][0]["tenant"][
        "id"
    ]
    return user, h, tenant_id


def test_signup_creates_personal_tenant_as_owner(client: TestClient) -> None:
    email, pw = random_email(), random_lower_string()
    assert (
        client.post(
            f"{API}/users/signup", json={"email": email, "password": pw}
        ).status_code
        == 200
    )
    tok = client.post(
        f"{API}/login/access-token", data={"username": email, "password": pw}
    ).json()["access_token"]
    mine = client.get(
        f"{API}/tenants/me", headers={"Authorization": f"Bearer {tok}"}
    ).json()
    assert mine["count"] == 1
    assert mine["data"][0]["roles"] == ["owner"]
    assert "tenant:manage" in mine["data"][0]["permissions"]


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
        json={"email": member.email, "roles": ["member"]},
    )
    assert r.status_code == 200 and r.json()["roles"] == ["member"]
    assert (
        client.post(
            f"{API}/tenants/{t}/members", headers=ho, json={"email": member.email}
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
            f"{API}/tenants/{t}/members", headers=hm, json={"email": owner.email}
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
    client.post(f"{API}/tenants/{t}/members", headers=ho, json={"email": member.email})
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
    _, h, _ = _user(client, db)
    slug = f"acme-{random_lower_string()[:6]}"
    r = client.post(f"{API}/tenants/", headers=h, json={"name": "Acme", "slug": slug})
    assert r.status_code == 200
    tid = r.json()["id"]
    assert (
        client.post(
            f"{API}/tenants/", headers=h, json={"name": "Acme", "slug": slug}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{API}/tenants/", headers=h, json={"name": "Bad", "slug": "Bad Slug"}
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
        t["slug"] for t in client.get(f"{API}/tenants/", headers=h).json()["data"]
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
        client.get(f"{API}/tenants/", headers=superuser_token_headers).json()["count"]
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
