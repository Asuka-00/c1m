"""通用列表筛选：?id= 指定记录、日期 / 时间范围（_from / _to）、时间字段默认降序。"""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.testing.mes import API, Mes


def test_id_range_and_default_desc(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    a = m.post("site", {"code": "S-A", "name": "a"})
    b = m.post("site", {"code": "S-B", "name": "b"})
    r = m.list("site", id=a["id"])
    assert [x["code"] for x in r["data"]] == ["S-A"]
    r = m.list("site", id=f"{a['id']},{b['id']}")
    assert r["count"] == 2
    assert client.get(m.url("site"), headers=m.h, params={"id": "x"}).status_code == 422
    # 时间范围：created_at（日志）与 datetime 字段
    assert m.list("audit_log", created_at_from="2000-01-01T00:00:00Z")["count"] >= 2
    assert m.list("audit_log", created_at_to="2000-01-01T00:00:00Z")["count"] == 0
    eq = m.post("equipment", {"code": "EQ-R", "name": "eq"})
    rc = m.post("reason_code", {"code": "DT", "name": "d", "reason_type": "downtime"})
    for d in ("2026-01-01", "2026-03-01", "2026-02-01"):
        m.post(
            "downtime",
            {
                "equipment_id": eq["id"],
                "start_at": f"{d}T08:00:00+08:00",
                "reason_id": rc["id"],
            },
        )
    # 默认按开始时间降序（最新在前）
    rows = m.list("downtime")["data"]
    assert [x["start_at"][:7] for x in rows] == ["2026-03", "2026-02", "2026-01"]
    r = m.list(
        "downtime",
        start_at_from="2026-01-15T00:00:00+08:00",
        start_at_to="2026-02-28T23:59:59+08:00",
    )
    assert [x["start_at"][:7] for x in r["data"]] == ["2026-02"]
    bad = client.get(m.url("downtime"), headers=m.h, params={"start_at_from": "nope"})
    assert bad.status_code == 422


def test_export_honours_filters_and_distinct(client: TestClient, db: Session) -> None:
    import io

    from openpyxl import load_workbook

    m = Mes(client, db)
    for c in ("EX-A", "EX-B", "EY-C"):
        m.post("site", {"code": c, "name": c})
    r = client.get(m.url("site", "export"), headers=m.h, params={"q": "EX-"})
    ws = load_workbook(io.BytesIO(r.content)).active
    assert ws is not None
    codes = sorted(str(x[0].value) for x in ws.iter_rows(min_row=2) if x[0].value)
    assert [c for c in codes if c.startswith("E")] == ["EX-A", "EX-B"]
    # 文本筛选去重取值：仅 filter=True 的 str 字段
    d = client.get(m.url("audit_log", "distinct", "username"), headers=m.h)
    assert d.status_code == 200 and d.json()["data"]
    bad = client.get(m.url("site", "distinct", "name"), headers=m.h)
    assert bad.status_code == 422


def test_meta_conditional_scope_fields(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    meta = client.get(f"{API}/_meta", headers=m.h).json()
    e = next(x for x in meta["entities"] if x["code"] == "check_binding")
    f = {x["name"]: x for x in e["fields"]}
    assert f["equipment"]["only_when_required"] is True
    assert f["trigger"]["only_when_required"] is False
    smr = next(x for x in meta["entities"] if x["code"] == "split_merge_rule")
    assert not any(x["filter"] for x in smr["fields"] if x["type"] == "bool")
