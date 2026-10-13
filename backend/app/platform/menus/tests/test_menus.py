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
        out |= {t["key"] for t in n.get("tabs", [])}  # 合并菜单的页签
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
    assert {"dashboard", "members", "tenant-roles", "settings"} <= keys
    # 平台页面不在工作区菜单中，旧路径重定向到平台管理控制台
    assert not keys & {"users", "roles", "permissions", "tenants", "menus"}
    assert r.json()["redirects"]["/tenants"] == "/platform/tenants"
    p = client.get(
        f"{API}/menus/me", headers=superuser_token_headers, params={"space": "platform"}
    )
    assert p.status_code == 200 and p.json()["space"] == "platform"
    pkeys = _keys(p.json()["menus"])
    assert {
        "p-g-tenants",
        "p-g-rbac",
        "p-g-settings",
        "p-g-ops",
        "p-tenants",
        "p-users",
        "p-roles",
        "p-permissions",
        "p-config",
        "p-channels",
        "p-audit",
        "p-login-log",
        "p-ops-log",
    } == pkeys


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
    # 用户与权限：租户所有者只看到成员 / 租户角色页签
    up = next(
        c
        for g in owner_body["menus"]
        for c in g["children"]
        if c["key"] == "user-permissions"
    )
    assert [t["key"] for t in up["tabs"]] == [
        "members",
        "tenant-roles",
    ]
    # 平台控制台菜单仅超级用户
    assert (
        client.get(
            f"{API}/menus/me", headers=ho, params={"space": "platform"}
        ).status_code
        == 403
    )
    assert "/platform/tenants" in owner_body["forbidden_paths"]
    assert set(owner_body["redirects"]) == {
        "/members",
        "/tenant-roles",
    } | {k for k in owner_body["redirects"] if k.startswith("/mes/")}
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
        f"{API}/platform/menus/",
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
            f"{API}/platform/menus/", headers=h, json={"key": key, "title": "x"}
        ).status_code
        == 409
    )
    assert key in _keys(client.get(f"{API}/menus/me", headers=h).json()["menus"])
    _, hu = _user(client, db)
    assert key not in _keys(client.get(f"{API}/menus/me", headers=hu).json()["menus"])
    assert (
        client.post(
            f"{API}/platform/menus/", headers=hu, json={"key": "x", "title": "x"}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"{API}/platform/menus/{mid}", headers=h, json={"hidden": True}
        ).json()["hidden"]
        is True
    )
    assert key not in _keys(client.get(f"{API}/menus/me", headers=h).json()["menus"])
    assert client.delete(f"{API}/platform/menus/{mid}", headers=h).status_code == 200


def test_role_permission_bulk_and_tenant_roles(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    h = superuser_token_headers
    role = client.post(
        f"{API}/platform/roles/",
        headers=h,
        json={"name": f"r-{random_lower_string()[:6]}"},
    ).json()
    r = client.put(
        f"{API}/platform/roles/{role['id']}/permissions",
        headers=h,
        json={"codes": ["users:read", "roles:read"]},
    )
    assert {p["code"] for p in r.json()["permissions"]} == {"users:read", "roles:read"}
    assert (
        client.put(
            f"{API}/platform/roles/{role['id']}/permissions",
            headers=h,
            json={"codes": ["nope"]},
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
    assert (
        client.get(f"{API}/platform/roles/{roles['member']}", headers=h).status_code
        == 404
    )


def test_menu_layout_complete_and_synced(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    from app.core.registry import menu_items
    from app.platform.menus.layout import GROUPS, ITEMS, MERGED, tab_keys
    from app.platform.menus.service import SYSTEM_ITEMS

    placed = [k for items in ITEMS.values() for k, _ in items]
    tabs = [k for *_, ts in MERGED.values() for k in ts]
    assert len(placed) == len(set(placed)) and len(tabs) == len(set(tabs))
    assert set(MERGED) <= set(placed) and not tab_keys() & set(placed)
    # 每个页面恰好出现一次：独立菜单或合并菜单的页签
    assert (set(placed) - set(MERGED)) | tab_keys() == set(SYSTEM_ITEMS) | set(
        menu_items()
    )
    assert [g for g, *_ in GROUPS] == list(ITEMS)
    tree = client.get(f"{API}/menus/me", headers=superuser_token_headers).json()
    top = [n["key"] for n in tree["menus"]]
    assert top == [g for g, *_ in GROUPS]  # ordered domain groups only
    by = {n["key"]: [c["key"] for c in n["children"]] for n in tree["menus"]}
    assert by["g-planning"] == ["mes-work_order", "mes-lot-start"]
    assert "mes-audit_log" in by["g-system"] and "mes-uom" in by["g-master"]
    # 业务流顺序：工作台 → 执行 → 在制报表 … 主数据 → 系统；组内日常作业在前
    assert top[:3] == ["g-workspace", "g-execution", "g-wip"] and top[-1] == "g-system"
    assert by["g-workspace"][:2] == ["dashboard", "notifications"]
    assert by["g-execution"][0] == "mes-lot-console"
    assert by["g-equipment"][0] == "mes-eqp-board"
    assert any("mes-equipment-master" in v for v in by.values())
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
    # 旧库中的错位 / 旧排序在重新同步后被纠正
    wip = db.exec(select(Menu).where(Menu.key == "mes-wip-dashboard")).one()
    sysg = db.exec(select(Menu).where(Menu.key == "g-system")).one()
    wip.parent_id, wip.sort_order, sysg.sort_order = sysg.id, 999, -5
    db.add_all([custom, dash, wip, sysg])
    db.commit()
    seed_menus(db)
    keys = {m.key: m for m in db.exec(select(Menu)).all()}
    assert "mes-g-legacy" not in keys
    assert keys["custom-under-legacy"].parent_id is None
    assert keys["dashboard"].parent_id == keys["g-workspace"].id
    assert keys["dashboard"].title == "Dashboard"
    assert keys["mes-wip-dashboard"].parent_id == keys["g-wip"].id
    assert keys["mes-wip-dashboard"].sort_order == 0
    assert keys["g-system"].sort_order == 110
    db.delete(keys["custom-under-legacy"])
    db.commit()


def test_sync_removes_merged_hold_release_menu(db: Session) -> None:
    """旧库中的「批量释放 Hold」菜单在同步后删除，Hold 管理指向合并后的页面。"""
    from sqlmodel import select

    from app.platform.menus.models import Menu
    from app.platform.menus.service import seed_menus

    db.add(
        Menu(
            key="mes-hold-release",
            title="Batch Hold Release",
            path="/mes/hold-release",
            component="mes-page:hold-release",
        )
    )
    db.commit()
    seed_menus(db)
    keys = {m.key: m for m in db.exec(select(Menu)).all()}
    assert "mes-hold-release" not in keys
    hold = keys["mes-lot_hold"]
    assert (hold.path, hold.component) == ("/mes/lot-hold", "mes-page:hold")


def test_merged_menu_tabs_and_redirects(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """合并菜单返回页签（原菜单 key / 组件 / 权限），旧路径重定向到 合并页?tab=。"""
    from app.platform.menus.layout import MERGED

    body = client.get(f"{API}/menus/me", headers=superuser_token_headers).json()
    nodes = {}

    def walk(ns: list[dict]) -> None:  # type: ignore[type-arg]
        for n in ns:
            nodes[n["key"]] = n
            walk(n["children"])

    walk(body["menus"])
    for key, (path, _, view, tabs) in MERGED.items():
        n = nodes[key]
        assert n["path"] == path and n["component"] == view
        assert [t["key"] for t in n["tabs"]] == tabs
        for t in n["tabs"]:
            assert t["component"] and t["path"] != path
            assert body["redirects"][t["path"]] == f"{path}?tab={t['key']}"
            assert t["key"] not in nodes  # 不再是独立菜单


def test_merged_menu_permission_any_tab(db: Session) -> None:
    """合并菜单：拥有任一页签权限即可见，页签按各自权限过滤。"""
    from sqlmodel import select

    from app.platform.menus.models import Menu
    from app.platform.menus.service import allowed_perm, build_tree, redirects

    assert allowed_perm("a:read,b:read", {"b:read"}, False)
    assert not allowed_perm("a:read,b:read", {"c:read"}, False)
    assert allowed_perm(None, set(), False) and allowed_perm("x", set(), True)
    menus = list(db.exec(select(Menu)).all())
    tree = build_tree(menus, {"mes.check:read"}, False)
    flat = {c["key"]: c for g in tree for c in g.model_dump()["children"]}
    node = flat["mes-check-config"]
    assert [t["key"] for t in node["tabs"]] == [
        "mes-check_rule",
        "mes-check_plan",
        "mes-check_binding",
    ]
    assert "mes-product-master" not in flat  # 无产品权限
    assert all(v.startswith("/mes/check-config?tab=") for v in redirects(tree).values())


def test_sync_removes_menus_merged_into_tabs(db: Session) -> None:
    """已有库中被合并为页签的旧独立菜单在同步时删除。"""
    from sqlmodel import select

    from app.platform.menus.layout import tab_keys
    from app.platform.menus.models import Menu
    from app.platform.menus.service import seed_menus

    old = sorted(tab_keys())
    db.add_all(Menu(key=k, title=k, path=f"/old/{k}") for k in old)
    db.commit()
    seed_menus(db)
    keys = {m.key for m in db.exec(select(Menu)).all()}
    assert not keys & set(old)
