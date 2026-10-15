from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.platform.users import service as crud
from app.platform.users.schemas import UserCreate
from app.testing.utils import random_email, random_lower_string

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
    # tenant owners manage their tenant's config (System group)
    assert {"g-system", "config"} <= keys
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


def test_menu_layout_complete_and_synced(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    from app.core.registry import menu_items
    from app.platform.menus.layout import GROUPS, ITEMS
    from app.platform.menus.service import SYSTEM_ITEMS

    placed = [k for items in ITEMS.values() for k, _ in items]
    assert len(placed) == len(set(placed))  # each item once
    assert set(placed) == set(SYSTEM_ITEMS) | set(menu_items())  # nothing missing
    assert [g for g, *_ in GROUPS] == list(ITEMS)
    tree = client.get(f"{API}/menus/me", headers=superuser_token_headers).json()
    top = [n["key"] for n in tree["menus"]]
    assert top == [g for g, *_ in GROUPS]  # ordered domain groups only
    by = {n["key"]: [c["key"] for c in n["children"]] for n in tree["menus"]}
    assert by["g-planning"] == ["mes-work_order", "mes-lot-start"]
    assert "mes-audit_log" in by["g-system"] and "mes-uom" in by["g-master"]
    assert not {"general", "admin", "other", "tenant"} & set(top)


def test_sync_moves_and_drops_legacy_groups(db: Session) -> None:
    from sqlmodel import select

    from app.platform.menus.models import Menu
    from app.platform.menus.service import seed_menus

    legacy = Menu(key="mes-g-legacy", title="MES · Legacy", sort_order=1)
    db.add(legacy)
    db.flush()
    custom = Menu(
        key="custom-under-legacy", title="x", parent_id=legacy.id, sort_order=1
    )
    dash = db.exec(select(Menu).where(Menu.key == "dashboard")).one()
    dash.parent_id, dash.title = legacy.id, "old"
    db.add_all([custom, dash])
    db.commit()
    seed_menus(db)
    keys = {m.key: m for m in db.exec(select(Menu)).all()}
    assert "mes-g-legacy" not in keys
    assert keys["custom-under-legacy"].parent_id is None
    assert keys["dashboard"].parent_id == keys["g-workspace"].id
    assert keys["dashboard"].title == "Dashboard"
    db.delete(keys["custom-under-legacy"])
    db.commit()
