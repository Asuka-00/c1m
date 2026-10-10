from fastapi.testclient import TestClient
from sqlmodel import Session

from app import crud
from app.core.config import settings
from app.models import UserCreate
from tests.utils.utils import random_email, random_lower_string

API = settings.API_V1_STR


def _keys(nodes: list[dict]) -> set[str]:  # type: ignore[type-arg]
    out: set[str] = set()
    for n in nodes:
        out.add(n["key"])
        out |= _keys(n["children"])
    return out


def _user(client: TestClient, db: Session) -> tuple[str, dict[str, str]]:
    email, pw = random_email(), random_lower_string()
    crud.create_user(session=db, user_create=UserCreate(email=email, password=pw))
    tok = client.post(
        f"{API}/login/access-token", data={"username": email, "password": pw}
    ).json()["access_token"]
    return email, {"Authorization": f"Bearer {tok}"}


def test_superuser_sees_all_menus(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    r = client.get(f"{API}/menus/me", headers=superuser_token_headers)
    assert r.status_code == 200
    keys = _keys(r.json()["menus"])
    assert {
        "dashboard",
        "members",
        "users",
        "roles",
        "permissions",
        "tenants",
        "menus",
        "settings",
    } <= keys


def test_owner_vs_member_menus(client: TestClient, db: Session) -> None:
    _, ho = _user(client, db)
    owner_body = client.get(f"{API}/menus/me", headers=ho).json()
    keys = _keys(owner_body["menus"])
    assert {"dashboard", "members", "tenant-roles", "settings"} <= keys
    assert not keys & {
        "users",
        "roles",
        "permissions",
        "tenants",
        "menus",
    }
    # tenant owners manage their tenant's config: Administration holds only that
    assert {"admin", "config"} <= keys
    assert {"/users", "/roles", "/tenants"} <= set(owner_body["forbidden_paths"])
    assert "/members" not in owner_body["forbidden_paths"]
    tid = owner_body["tenant_id"]

    member_email, hm = _user(client, db)
    client.post(
        f"{API}/tenants/{tid}/members",
        headers=ho,
        json={"email": member_email, "roles": []},
    )
    # no roles in that tenant -> no members menus there
    keys = _keys(
        client.get(f"{API}/menus/me", headers={**hm, "X-Tenant-ID": tid}).json()[
            "menus"
        ]
    )
    assert "members" not in keys and "dashboard" in keys
    # 2 tenants and no header -> platform-only menus, no error
    body = client.get(f"{API}/menus/me", headers=hm).json()
    assert body["tenant_id"] is None and "members" not in _keys(body["menus"])


def test_menu_crud(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    h = superuser_token_headers
    key = f"reports-{random_lower_string()[:6]}"
    r = client.post(
        f"{API}/menus/",
        headers=h,
        json={
            "key": key,
            "title": "Reports",
            "path": f"/{key}",
            "component": "dashboard",
            "permission": "users:read",
        },
    )
    assert r.status_code == 200
    mid = r.json()["id"]
    assert (
        client.post(
            f"{API}/menus/", headers=h, json={"key": key, "title": "x"}
        ).status_code
        == 409
    )
    assert key in _keys(client.get(f"{API}/menus/me", headers=h).json()["menus"])
    _, hu = _user(client, db)
    assert key not in _keys(client.get(f"{API}/menus/me", headers=hu).json()["menus"])
    assert (
        client.post(
            f"{API}/menus/", headers=hu, json={"key": "x", "title": "x"}
        ).status_code
        == 403
    )
    assert (
        client.patch(f"{API}/menus/{mid}", headers=h, json={"hidden": True}).json()[
            "hidden"
        ]
        is True
    )
    assert key not in _keys(client.get(f"{API}/menus/me", headers=h).json()["menus"])
    assert client.delete(f"{API}/menus/{mid}", headers=h).status_code == 200


def test_role_permission_bulk_and_tenant_roles(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    h = superuser_token_headers
    role = client.post(
        f"{API}/roles/", headers=h, json={"name": f"r-{random_lower_string()[:6]}"}
    ).json()
    r = client.put(
        f"{API}/roles/{role['id']}/permissions",
        headers=h,
        json={"codes": ["users:read", "roles:read"]},
    )
    assert {p["code"] for p in r.json()["permissions"]} == {"users:read", "roles:read"}
    assert (
        client.put(
            f"{API}/roles/{role['id']}/permissions", headers=h, json={"codes": ["nope"]}
        ).status_code
        == 404
    )

    _, ho = _user(client, db)
    tid = client.get(f"{API}/tenants/me", headers=ho).json()["data"][0]["tenant"]["id"]
    tr = client.post(
        f"{API}/tenants/{tid}/roles",
        headers=ho,
        json={"name": "viewer", "permission_codes": ["members:read"]},
    )
    assert tr.status_code == 200
    rid = tr.json()["id"]
    assert (
        client.post(
            f"{API}/tenants/{tid}/roles",
            headers=ho,
            json={"name": "bad", "permission_codes": ["users:read"]},
        ).status_code
        == 400
    )
    r = client.put(
        f"{API}/tenants/{tid}/roles/{rid}/permissions",
        headers=ho,
        json={"codes": ["members:read", "members:write"]},
    )
    assert {p["code"] for p in r.json()["permissions"]} == {
        "members:read",
        "members:write",
    }
    roles = {
        x["name"]: x["id"]
        for x in client.get(f"{API}/tenants/{tid}/roles", headers=ho).json()["data"]
    }
    assert (
        client.put(
            f"{API}/tenants/{tid}/roles/{roles['owner']}/permissions",
            headers=ho,
            json={"codes": []},
        ).status_code
        == 400
    )
    assert (
        client.delete(
            f"{API}/tenants/{tid}/roles/{roles['owner']}", headers=ho
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"{API}/tenants/{tid}/roles/{rid}", headers=ho, json={"description": "d"}
        ).json()["description"]
        == "d"
    )
    assert (
        client.delete(f"{API}/tenants/{tid}/roles/{rid}", headers=ho).status_code == 200
    )
    # platform /roles must not expose tenant roles
    assert client.get(f"{API}/roles/{roles['member']}", headers=h).status_code == 404
