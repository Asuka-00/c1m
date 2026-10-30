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


def _keys(nodes: list[dict]) -> set[str]:  # type: ignore[type-arg]
    out: set[str] = set()
    for n in nodes:
        out.add(n["key"])
        out |= {t["key"] for t in n.get("tabs", [])}  # 合并菜单的页签
        out |= _keys(n["children"])
    return out


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


def test_superuser_sees_all_menus(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    r = client.get(f"{API}/menus/me", headers=superuser_token_headers)
    assert r.status_code == 200
    keys = _keys(r.json()["menus"])
    assert {"dashboard", "members", "user-roles", "settings"} <= keys
    # 平台页面不在工作区菜单中
    assert not keys & {"users", "roles", "permissions", "tenants", "menus"}
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
    assert {"dashboard", "members", "user-roles", "settings"} <= keys
    assert not keys & {
        "users",
        "roles",
        "permissions",
        "tenants",
        "menus",
    }
    # tenant owners manage their tenant's config (System group)
    assert {"g-system", "config"} <= keys
    assert {"/platform", "/platform/users"} <= set(owner_body["forbidden_paths"])
    # 用户与权限：租户所有者只看到成员 / 租户角色页签
    up = next(
        c
        for g in owner_body["menus"]
        for c in g["children"]
        if c["key"] == "user-permissions"
    )
    assert [t["key"] for t in up["tabs"]] == [
        "members",
        "user-roles",
    ]
    # 平台控制台菜单仅超级用户
    assert (
        client.get(
            f"{API}/menus/me", headers=ho, params={"space": "platform"}
        ).status_code
        == 403
    )
    assert "/platform/tenants" in owner_body["forbidden_paths"]
    tid = owner_body["tenant_id"]

    member_email, hm = _user(client, db)
    client.post(
        f"{API}/tenants/{tid}/members",
        headers=ho,
        json={"username": username_for(member_email), "roles": []},
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
    assert by["g-planning"] == ["mes-lot-start", "mes-wo-board", "mes-work_order"]
    assert "mes-audit_log" in by["g-system"] and "mes-uom" in by["g-master"]
    # 业务流顺序：工作台 → 执行 → 在制报表 … 主数据 → 系统；组内日常作业在前
    assert top[:4] == ["g-workspace", "g-execution", "g-exception", "g-wip"]
    assert top[-1] == "g-system"
    assert by["g-workspace"][:2] == ["dashboard", "notifications"]
    # 批次作业组只放作业项，进出站在首位；Hold 管理与 Q-Time 监控归异常处理
    assert by["g-execution"][:2] == ["mes-lot-console", "mes-batch-ops"]
    assert not {"mes-lot", "mes-wafer", "mes-operator_qual"} & set(by["g-execution"])
    assert by["g-exception"] == [
        "mes-lot_hold",
        "mes-qtime-monitor",
        "mes-ncr",
        "mes-future_hold",
        "mes-check_log",
    ]
    assert {"mes-lot", "mes-wafer"} <= set(by["g-wip"])
    assert "mes-operator_qual" in by["g-factory"]
    assert by["g-equipment"][0] == "mes-eqp-board"
    assert any("mes-equipment-master" in v for v in by.values())
    assert not {"general", "admin", "other", "tenant"} & set(top)


def test_sync_restores_declared_layout(db: Session) -> None:
    from sqlmodel import select

    from app.platform.menus.models import Menu
    from app.platform.menus.service import seed_menus

    other = db.exec(select(Menu).where(Menu.key == "g-wip")).one()
    dash = db.exec(select(Menu).where(Menu.key == "dashboard")).one()
    dash.parent_id, dash.title = other.id, "changed"
    # 被改动的位置 / 排序在重新同步后恢复为注册表定义
    wip = db.exec(select(Menu).where(Menu.key == "mes-wip-dashboard")).one()
    sysg = db.exec(select(Menu).where(Menu.key == "g-system")).one()
    wip.parent_id, wip.sort_order, sysg.sort_order = sysg.id, 999, -5
    db.add_all([dash, wip, sysg])
    db.commit()
    seed_menus(db)
    keys = {m.key: m for m in db.exec(select(Menu)).all()}
    assert keys["dashboard"].parent_id == keys["g-workspace"].id
    assert keys["dashboard"].title == "Dashboard"
    assert keys["mes-wip-dashboard"].parent_id == keys["g-wip"].id
    assert keys["mes-wip-dashboard"].sort_order == 0
    assert keys["g-system"].sort_order == 110


def test_sync_deletes_retired_menus(db: Session) -> None:
    from sqlmodel import select

    from app.platform.menus.layout import RETIRED
    from app.platform.menus.models import Menu
    from app.platform.menus.service import seed_menus

    db.add(Menu(key=RETIRED[0], title="old", path="/old"))
    db.commit()
    seed_menus(db)
    assert not db.exec(select(Menu).where(Menu.key == RETIRED[0])).all()


def test_merged_menu_tabs(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """合并菜单返回页签（key / 组件 / 权限）。"""
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
            assert t["component"]
            assert t["key"] not in nodes  # 不再是独立菜单


def test_merged_menu_permission_any_tab(db: Session) -> None:
    """合并菜单：拥有任一页签权限即可见，页签按各自权限过滤。"""
    from sqlmodel import select

    from app.platform.menus.models import Menu
    from app.platform.menus.service import allowed_perm, build_tree

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


def test_menu_titles_plan_a() -> None:
    """方案 A 菜单英文标题（各语言措辞由前端语言包测试覆盖）：标题非空，合并菜单与首个页签不重名。"""
    from app.platform.menus import layout

    en = {k: lbl for k, lbl, _, _ in layout.GROUPS}
    for items in layout.ITEMS.values():
        en.update(dict(items))
    en.update(layout.TAB_TITLES)
    assert all(v.strip() and "|" not in v for v in en.values())
    assert en["mes-check_log"] == "Interlock Log" and en["mes-change_order"] == "ECN"
    for key, (*_, tabs) in layout.MERGED.items():
        assert en[key] != en[tabs[0]], key


def test_admin_notify_config_and_member_user_permissions(
    client: TestClient, db: Session
) -> None:
    """admin 有 notify:config 能看到通知订阅；member 看不到用户与权限但接口仍可调。"""
    from app.platform.rbac.permissions import TENANT_ROLES

    # admin 经 MES_PERMISSIONS（含模块注册的 EXTRA 权限）已有 notify:config
    assert "notify:config" in TENANT_ROLES["admin"][1]
    assert "notify:config" not in TENANT_ROLES["member"][1]
    _, ho = _user(client, db)
    tid = client.get(f"{API}/menus/me", headers=ho).json()["tenant_id"]
    out = {}
    for role in ("admin", "member"):
        email, h = _user(client, db)
        r = client.post(
            f"{API}/tenants/{tid}/members",
            headers=ho,
            json={"username": username_for(email), "roles": [role]},
        )
        assert r.status_code in (200, 201), r.text
        hh = {**h, "X-Tenant-ID": tid}
        body = client.get(f"{API}/menus/me", headers=hh).json()
        out[role] = (_keys(body["menus"]), body["forbidden_paths"], hh)
    akeys = out["admin"][0]
    assert {"notify-subscriptions", "user-permissions", "members"} <= akeys
    mkeys, mforbidden, mh = out["member"]
    assert not {"user-permissions", "members", "user-roles"} & mkeys
    assert "notify-subscriptions" not in mkeys and "dashboard" in mkeys
    assert "/user-permissions" in mforbidden
    # 已知缺口（MENU-B4 关闭）：members:read 接口本期不收紧
    assert client.get(f"{API}/tenants/{tid}/members", headers=mh).status_code == 200
