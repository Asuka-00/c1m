"""MES phase 1: generic CRUD contract, org tree, dictionary, code rules,
custom attributes, audit log, xlsx import/export, RLS + permissions."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from app.core.db import engine
from app.core.tenant import set_tenant
from app.platform.users import service as crud
from app.platform.users.schemas import UserCreate
from app.testing.mes import API, Mes
from app.testing.utils import random_email, random_lower_string, username_for


def _org(m: Mes) -> tuple[dict, dict]:  # type: ignore[type-arg]
    site = m.post("site", {"code": "F1", "name": "Fab 1", "timezone": "Asia/Taipei"})
    area = m.post(
        "area",
        {"code": "PHOTO", "name": "Photo", "site_id": site["id"], "area_type": "fab"},
    )
    return site, area


def test_meta_and_menus(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    meta = client.get(f"{API}/_meta", headers=m.h).json()
    codes = {e["code"] for e in meta["entities"]}
    assert {
        "site",
        "area",
        "workcenter",
        "shift",
        "work_calendar",
        "code_rule",
        "audit_log",
    } <= codes
    assert "code_rule_counter" not in codes  # internal
    site = next(e for e in meta["entities"] if e["code"] == "site")
    assert site["can_write"] and site["read"] == "mes.org:read"
    menus = client.get("/api/v1/menus/me", headers=m.h).json()
    # 独立菜单与合并菜单的页签
    keys = {c["key"] for g in menus["menus"] for c in g["children"]} | {
        t["key"] for g in menus["menus"] for c in g["children"] for t in c["tabs"]
    }
    assert {
        "mes-site",
        "mes-workcenter",
        "mes-code_rule",
        "mes-product",
        "mes-equipment",
    } <= keys


def test_crud_search_filter_sort_page(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    site, area = _org(m)
    assert area["site_label"] == "F1 · Fab 1"
    for i in range(25):
        m.post(
            "area",
            {
                "code": f"A{i:02d}",
                "name": f"Area {i}",
                "site_id": site["id"],
                "area_type": "test" if i % 2 else "fab",
            },
        )
    page = m.list("area")
    assert page["count"] == 26 and len(page["data"]) == 20
    assert m.list("area", page=2)["data"][-1]["code"] == "PHOTO"
    assert (
        m.list("area", sort_by="code", sort_order="desc")["data"][0]["code"] == "PHOTO"
    )
    assert m.list("area", q="area 1")["count"] == 11  # Area 1, 10..19
    assert m.list("area", area_type="test")["count"] == 12
    assert m.list("area", site_id=site["id"], q="photo")["count"] == 1
    assert (
        client.get(m.url("area"), headers=m.h, params={"sort_by": "nope"}).status_code
        == 422
    )
    # validation
    m.post(
        "area",
        {"code": "X", "name": "x", "site_id": site["id"], "area_type": "moon"},
        422,
    )
    m.post("area", {"name": "x", "site_id": site["id"]}, 422)
    m.post("area", {"code": "X", "name": "x", "site_id": str(uuid.uuid4())}, 422)
    m.post("area", {"code": "PHOTO", "name": "dup", "site_id": site["id"]}, 409)
    # update + delete restrict (site still referenced)
    assert (
        m.patch("area", area["id"], {"name": "Photolithography"})["name"]
        == "Photolithography"
    )
    m.delete("site", site["id"], 409)
    got = client.get(m.url("area", area["id"]), headers=m.h).json()
    assert got["code"] == "PHOTO"


def test_workcenter_tree_and_cycles(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    _, area = _org(m)
    bay = m.post(
        "workcenter",
        {"code": "BAY1", "name": "Bay 1", "area_id": area["id"], "kind": "bay"},
    )
    wc = m.post(
        "workcenter",
        {
            "code": "WC1",
            "name": "Litho WC",
            "area_id": area["id"],
            "kind": "workcenter",
            "parent_id": bay["id"],
        },
    )
    cell = m.post(
        "workcenter",
        {
            "code": "C1",
            "name": "Cell",
            "area_id": area["id"],
            "kind": "cell",
            "parent_id": wc["id"],
        },
    )
    tree = client.get(m.url("workcenter", "tree"), headers=m.h).json()
    assert (
        tree[0]["code"] == "BAY1"
        and tree[0]["children"][0]["children"][0]["code"] == "C1"
    )
    m.patch("workcenter", bay["id"], {"parent_id": cell["id"]}, 422)  # cycle
    m.delete("workcenter", bay["id"])  # cascades to children
    assert m.list("workcenter")["count"] == 0


def test_shift_calendar_dictionary(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    site, _ = _org(m)
    m.post(
        "shift",
        {
            "code": "D",
            "name": "Day",
            "site_id": site["id"],
            "start_time": "08:00",
            "end_time": "20:00",
        },
    )
    m.post(
        "shift",
        {
            "code": "N",
            "name": "Night",
            "site_id": site["id"],
            "start_time": "20:00",
            "end_time": "08:00",
        },
        422,
    )
    m.post(
        "shift",
        {
            "code": "N",
            "name": "Night",
            "site_id": site["id"],
            "start_time": "20:00",
            "end_time": "08:00",
            "crosses_midnight": True,
        },
    )
    cal = m.post(
        "work_calendar",
        {"code": "CAL26", "name": "2026", "site_id": site["id"], "year": 2026},
    )
    m.post(
        "calendar_day",
        {"work_calendar_id": cal["id"], "day": "2026-10-10", "day_type": "holiday"},
    )
    m.post("calendar_day", {"work_calendar_id": cal["id"], "day": "2026-10-10"}, 409)
    assert (
        m.list("calendar_day", work_calendar_id=cal["id"])["data"][0]["day"]
        == "2026-10-10"
    )
    dt = m.post("dict_type", {"code": "GRADE", "name": "Grade"})
    m.post(
        "dict_item",
        {"dict_type_id": dt["id"], "code": "A", "name": "Grade A", "sort_order": 1},
    )
    assert m.list("dict_item", dict_type_id=dt["id"])["count"] == 1


def test_custom_attributes(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    m.post(
        "attr_def",
        {
            "entity_type": "site",
            "code": "fab_class",
            "name": "Fab class",
            "data_type": "select",
        },
        422,
    )
    m.post(
        "attr_def",
        {
            "entity_type": "site",
            "code": "fab_class",
            "name": "Fab class",
            "data_type": "select",
            "options": "ISO3, ISO4",
            "required": True,
        },
    )
    m.post(
        "attr_def",
        {
            "entity_type": "site",
            "code": "wafers_per_month",
            "name": "WPM",
            "data_type": "number",
        },
    )
    defs = client.get(f"{API}/_attrs/site", headers=m.h).json()
    assert defs[0]["options"] == ["ISO3", "ISO4"]
    m.post("site", {"code": "S", "name": "S"}, 422)  # required attr missing
    m.post("site", {"code": "S", "name": "S", "attrs": {"fab_class": "ISO9"}}, 422)
    m.post(
        "site",
        {"code": "S", "name": "S", "attrs": {"fab_class": "ISO3", "nope": 1}},
        422,
    )
    m.post(
        "site",
        {
            "code": "S",
            "name": "S",
            "attrs": {"fab_class": "ISO3", "wafers_per_month": "x"},
        },
        422,
    )
    s = m.post(
        "site",
        {
            "code": "S",
            "name": "S",
            "attrs": {"fab_class": "ISO3", "wafers_per_month": 40000},
        },
    )
    assert s["attrs"] == {"fab_class": "ISO3", "wafers_per_month": 40000}


def test_code_rules(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    m.post(
        "code_rule",
        {"code": "BAD", "name": "x", "target": "lot", "pattern": "LT{YY}"},
        422,
    )
    m.post(
        "code_rule",
        {"code": "BAD", "name": "x", "target": "lot", "pattern": "LT{FOO}{SEQ}"},
        422,
    )
    r = m.post(
        "code_rule",
        {
            "code": "LOT",
            "name": "Lot",
            "target": "lot",
            "pattern": "LT{SEQ}",
            "seq_width": 5,
        },
    )
    assert m.action("code-rule", r["id"], "preview", {"count": 2})["codes"] == [
        "LT00001",
        "LT00002",
    ]
    assert m.action("code-rule", r["id"], "generate", {"count": 2})["codes"] == [
        "LT00001",
        "LT00002",
    ]
    assert m.action("code-rule", r["id"], "generate", {})["codes"] == ["LT00003"]
    w = m.post(
        "code_rule",
        {
            "code": "WAF",
            "name": "Wafer",
            "target": "wafer",
            "pattern": "{LOT}.{SLOT:2}",
        },
    )
    assert m.action(
        "code-rule", w["id"], "preview", {"count": 2, "context": {"LOT": "LT00003"}}
    )["codes"] == ["LT00003.01", "LT00003.02"]
    b = m.post(
        "code_rule",
        {
            "code": "B36",
            "name": "b36",
            "target": "carrier",
            "pattern": "C{SEQ36}",
            "seq_width": 3,
            "seq_start": 35,
        },
    )
    assert m.action("code-rule", b["id"], "generate", {"count": 2})["codes"] == [
        "C00Z",
        "C010",
    ]


def test_audit_log(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    site, _ = _org(m)
    m.patch("site", site["id"], {"name": "Fab One"})
    logs = m.list("audit_log", entity_type="site")["data"]
    assert [x["action"] for x in logs] == ["update", "create"]  # newest first
    assert logs[0]["changes"]["name"] == ["Fab 1", "Fab One"] and logs[0]["user_email"]
    assert client.post(m.url("audit_log"), headers=m.h, json={}).status_code == 405


def test_xlsx_roundtrip(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    site, _ = _org(m)
    rows = m.export("area")
    assert rows[0][:4] == ["code", "name", "site", "area_type"] and rows[1][2] == "F1"
    header = rows[0]
    rows[1][header.index("name")] = "Photo (renamed)"
    new = dict.fromkeys(header)
    new.update(code="ETCH", name="Etch", site="F1", area_type="fab")
    res = m.import_rows("area", [header, rows[1], [new[h] for h in header]])
    assert res == {"created": 1, "updated": 1}
    assert {a["name"] for a in m.list("area")["data"]} == {"Photo (renamed)", "Etch"}
    bad = m.import_rows(
        "area", [header, [new[h] if h != "site" else "NOPE" for h in header]], 422
    )
    assert bad["detail"]["errors"][0]["row"] == 2
    m.import_rows("area", [["code", "bogus"]], 422)
    assert m.list("area")["count"] == 2  # nothing partial
    assert m.list("audit_log", action="import")["count"] == 1
    _ = site


def test_isolation_and_permissions(client: TestClient, db: Session) -> None:
    a, b = Mes(client, db), Mes(client, db)
    site, _ = _org(a)
    assert b.list("site")["count"] == 0
    assert client.get(a.url("site", site["id"]), headers=b.h).status_code == 404
    with Session(engine) as s:  # RLS backstop: no tenant -> nothing visible
        assert s.execute(text("SELECT count(*) FROM mes_site")).scalar_one() == 0
        set_tenant(s, uuid.UUID(a.tid))
        assert s.execute(text("SELECT count(*) FROM mes_site")).scalar_one() == 1
    # plain member: read yes, write no
    email, pw = random_email(), random_lower_string()
    crud.create_user(
        session=db,
        user_create=UserCreate(email=email, username=username_for(email), password=pw),
    )
    client.post(
        f"/api/v1/tenants/{a.tid}/members",
        headers=a.h,
        json={"username": email, "roles": ["member"]},
    )
    tok = client.post(
        "/api/v1/login/access-token", data={"username": email, "password": pw}
    ).json()["access_token"]
    hm = {"Authorization": f"Bearer {tok}", "X-Tenant-ID": a.tid}
    assert client.get(a.url("site"), headers=hm).json()["count"] == 1
    assert (
        client.post(
            a.url("site"), headers=hm, json={"code": "X", "name": "X"}
        ).status_code
        == 403
    )
    assert client.get(f"{API}/nope", headers=a.h).status_code == 404
    assert client.get(f"{API}/code-rule-counter", headers=a.h).status_code == 404
