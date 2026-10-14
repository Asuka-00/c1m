"""P2-D9 / P2-D10 regression: list-format 422 with registered codes."""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution.tests.test_exec import EXEC
from app.testing.mes import Mes


def test_trace_bad_kind_is_enum_422(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    r = client.get(f"{EXEC}/trace", headers=m.h, params={"kind": "bogus", "code": "X"})
    assert r.status_code == 422, r.text
    (item,) = r.json()["detail"]
    assert item["loc"] == ["query", "kind"]
    assert item["code"] == item["type"] == "enum"
    assert item["ctx"]["expected"] == [
        "lot",
        "wafer",
        "equipment",
        "material_lot",
        "customer_lot",
    ]


def test_versioned_create_non_int_version_is_422(
    client: TestClient, db: Session
) -> None:
    m = Mes(client, db)
    for bad in ("Q1", "1.5", True, 1.5):
        r = client.post(
            m.url("product"),
            headers=m.h,
            json=m._fill("product", {"code": f"PV-{bad}", "name": "p", "version": bad}),
        )
        assert r.status_code == 422, (bad, r.text)
        (item,) = r.json()["detail"]
        assert item["loc"] == ["body", "version"]
        assert item["code"] == item["type"] == "int_parsing"
        assert item["input"] == bad  # D71 O-2
    ok = m.post("product", {"code": "PV-OK", "name": "p", "version": "3"})
    assert ok["version"] == 3
    assert (
        m.post("product", {"code": "PV-INT", "name": "p", "version": 7})["version"] == 7
    )
    assert m.post("product", {"code": "PV-NONE", "name": "p"})["version"] == 1
