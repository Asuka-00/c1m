"""通用列表筛选：?id= 指定记录、日期 / 时间范围（_from / _to）、时间字段默认降序。"""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.testing.mes import Mes


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
