"""D76 item 2：服务端定点运算不经 float；bom_line.scrap_rate 按 4 位校验。"""

import uuid
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.tenant import set_tenant
from app.mes.common.uom import convert, to_qty
from app.mes.product.tests.test_bom import B
from app.testing.mes import Mes


def _uoms(m: Mes) -> dict[str, Any]:
    u = {
        c: m.post("uom", {"code": c, "name": c, "dimension": "volume"})["id"]
        for c in ("L", "ML", "GAL")
    }
    m.post(
        "uom_conversion", {"from_uom_id": u["L"], "to_uom_id": u["ML"], "factor": 1000}
    )
    m.post(
        "uom_conversion",
        {"from_uom_id": u["GAL"], "to_uom_id": u["L"], "factor": 3.785411784},
    )
    return u


def test_to_qty_no_float_math() -> None:
    assert to_qty(0.1) == Decimal("0.100000")
    assert to_qty(0.1 + 0.2) == Decimal("0.300000")
    assert to_qty("0.123456") == Decimal("0.123456")
    assert to_qty("123456789012.123456") == Decimal("123456789012.123456")


def test_uom_round_trip_exact(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    u = _uoms(m)
    tid = uuid.UUID(m.tid)
    u = {k: uuid.UUID(x) for k, x in u.items()}
    set_tenant(db, tid)
    try:
        _round_trips(db, tid, u)
    finally:
        set_tenant(db, None)


def _round_trips(db: Session, tid: uuid.UUID, u: dict[str, Any]) -> None:
    for a, b in (("L", "ML"), ("GAL", "L"), ("GAL", "ML"), ("ML", "GAL")):
        for v in (0.1, 0.123456, "0.1", "0.123456", Decimal("0.123456")):
            fwd = convert(db, tid, u[a], u[b], v)
            back = convert(db, tid, u[b], u[a], fwd["qty"])
            if a == "ML" and b == "GAL":
                continue  # 缩小方向先定点化到 6 位，往返不可逆，仅验证正向
            assert back["qty"] == Decimal(str(v)).quantize(Decimal("0.000001")), (
                a,
                b,
                v,
                fwd,
                back,
            )
    assert convert(db, tid, u["L"], u["ML"], 0.123456)["qty"] == Decimal("123.456")
    assert convert(db, tid, u["GAL"], u["L"], "0.1")["qty"] == Decimal("0.378541")


def _bad(err: Any, loc: list[Any]) -> None:
    d = err["detail"][0]
    assert d["loc"] == loc and d["type"] == "value_error", err
    assert d["ctx"] == {"max_places": 4}, err


def test_bom_line_scrap_rate_scale4_crud(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    b = B(m)
    v = b.bom(b.product("FG"))
    assert b.line(v, 10, scrap_rate="0.1234")["scrap_rate"] == "0.1234"
    _bad(b.line(v, 20, 422, scrap_rate="0.12345"), ["body", "scrap_rate"])
    _bad(b.line(v, 30, 422, scrap_rate=0.12345), ["body", "scrap_rate"])
    ln = b.line(v, 40)
    r = m.c.patch(
        m.url("bom_line", ln["id"]), headers=m.h, json={"scrap_rate": "0.00001"}
    )
    assert r.status_code == 422, r.text
    _bad(r.json(), ["body", "scrap_rate"])


def test_bom_line_scrap_rate_scale4_import(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    b = B(m)
    v = b.bom(b.product("FG"))
    b.line(v, 10)
    rows = m.export("bom_line")
    header = rows[0]
    i = header.index("scrap_rate")
    row = list(rows[1])
    row[i] = "0.12345"
    err = m.import_rows("bom_line", [header, row], 422)
    e0 = err["detail"]["errors"][0]
    assert e0["row"] == 2 and e0["type"] == "value_error", err
    assert e0["ctx"] == {"max_places": 4}, err
    # D77 补充一：loc 定位到行 / 列（不再是 body）
    assert e0["loc"] == ["file", 2, "scrap_rate"], err
    assert e0["column"] == "scrap_rate" and e0["cell"] == f"{chr(65 + i)}2", err
    row[i] = "0.1234"
    m.import_rows("bom_line", [header, row])
    assert m.list("bom_line")["data"][0]["scrap_rate"] == "0.1234"
