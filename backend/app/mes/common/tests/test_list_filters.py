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


def test_export_datetime_fields_utc_z(client: TestClient, db: Session) -> None:
    """D46 P2：xlsx 里 datetime 是按租户时区换算的 Excel 日期单元格，列名带时区；
    接口 JSON 仍是 UTC Z。导出文件可原样导回（列名时区后缀被去掉）。"""
    import io
    from datetime import datetime

    from openpyxl import load_workbook

    m = Mes(client, db)
    eq = m.post("equipment", {"code": "EQ-XD", "name": "eq"})
    rc = m.post("reason_code", {"code": "DT-X", "name": "d", "reason_type": "downtime"})
    m.post(
        "downtime",
        {
            "equipment_id": eq["id"],
            "start_at": "2026-04-01T08:00:00+08:00",
            "reason_id": rc["id"],
        },
    )
    r = client.get(m.url("downtime", "export"), headers=m.h)
    assert r.status_code == 200, r.text
    ws = load_workbook(io.BytesIO(r.content)).active
    assert ws is not None
    rows = list(ws.iter_rows(values_only=True))
    # 没有厂区：默认 Asia/Taipei
    i = rows[0].index("start_at (Asia/Taipei)")
    assert datetime(2026, 4, 1, 8, 0) in [x[i] for x in rows[1:]]
    assert ws.cell(row=2, column=i + 1).number_format == "yyyy-mm-dd hh:mm:ss"
    assert "equipment" in rows[0]  # 非时间列名不变
    js = m.list("downtime")["data"]
    assert js[0]["start_at"] == "2026-04-01T00:00:00Z"
    # 租户时区取第一个启用厂区
    m.post("site", {"code": "A-UTC", "name": "s", "timezone": "UTC"})
    r = client.get(m.url("downtime", "export"), headers=m.h)
    rows = list(load_workbook(io.BytesIO(r.content)).active.iter_rows(values_only=True))  # type: ignore[union-attr]
    i = rows[0].index("start_at (UTC)")
    assert datetime(2026, 4, 1, 0, 0) in [x[i] for x in rows[1:]]


def test_export_import_datetime_roundtrip(client: TestClient, db: Session) -> None:
    """D46 P2：导出的 xlsx（列名带时区、日期单元格）可原样导回，时间不偏移。"""
    m = Mes(client, db)
    eq = m.post("equipment", {"code": "EQ-RT", "name": "eq"})
    rc = m.post(
        "reason_code", {"code": "DT-RT", "name": "d", "reason_type": "downtime"}
    )
    m.post(
        "downtime",
        {
            "equipment_id": eq["id"],
            "start_at": "2026-04-01T08:30:00+08:00",
            "reason_id": rc["id"],
        },
    )
    rows = m.export("downtime")
    assert "start_at (Asia/Taipei)" in rows[0]
    m.import_rows("downtime", rows)
    got = [x["start_at"] for x in m.list("downtime")["data"]]
    assert got == ["2026-04-01T00:30:00Z", "2026-04-01T00:30:00Z"], got


def test_range_boundaries_d77(client: TestClient, db: Session) -> None:
    """D77：datetime 的 _to 半开（恰在边界的记录不含）；date 的 _to 闭区间（含当天）。"""
    m = Mes(client, db)
    eq = m.post("equipment", {"code": "EQ-B", "name": "eq"})
    rc = m.post("reason_code", {"code": "DT", "name": "d", "reason_type": "downtime"})
    m.post(
        "downtime",
        {
            "equipment_id": eq["id"],
            "start_at": "2026-03-10T00:00:00+08:00",
            "reason_id": rc["id"],
        },
    )

    def dt(**kw: str) -> int:
        return int(m.list("downtime", **kw)["count"])

    assert dt(start_at_to="2026-03-10T00:00:00+08:00") == 0  # 边界不含
    assert dt(start_at_to="2026-03-09T16:00:00Z") == 0  # 同一时刻（UTC 写法）
    assert dt(start_at_to="2026-03-10T00:00:00.000001+08:00") == 1
    assert dt(start_at_from="2026-03-10T00:00:00+08:00") == 1  # 下限含
    assert (
        dt(
            start_at_from="2026-03-09T16:00:00Z",
            start_at_to="2026-03-10T00:00:01+08:00",
        )
        == 1
    )
    # date 字段：qualified_until = 3/10，_to=3/10 含当天，_to=3/9 不含
    op = m.post("operation", {"code": "OP-B", "name": "op"})
    m.post(
        "equipment_capability",
        {
            "equipment_id": eq["id"],
            "operation_id": op["id"],
            "qualified_until": "2026-03-10",
        },
    )

    def cap(**kw: str) -> int:
        return int(m.list("equipment_capability", **kw)["count"])

    assert cap(qualified_until_to="2026-03-10") == 1
    assert cap(qualified_until_to="2026-03-09") == 0
    assert cap(qualified_until_from="2026-03-10", qualified_until_to="2026-03-10") == 1
    assert cap(qualified_until_from="2026-03-11") == 0
