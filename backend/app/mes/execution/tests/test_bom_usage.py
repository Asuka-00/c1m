"""B2 验收（D28，bom.md v1.1 §3 / §10 / §11）：单位换算精度与计件整数；用料记录
（source / usage_type）；出站按工序累计比对 BOM 计划用量（返工不计、换算后比较），
超量只提示、写批次履历 bom_over_consumption。"""

from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution.tests.test_exec import EXEC, Line
from app.testing.mes import API


def _res(f: Line, seq: int, uom: str, qty: float) -> None:
    f.sql(
        "INSERT INTO mes_step_resource (id, tenant_id, route_step_id, resource_kind,"
        " material_id, qty, uom_id, qty_basis) VALUES (gen_random_uuid(), :t, :s,"
        " 'material', :m, :qty, :u, 'per_unit')",
        t=f.m.tid,
        s=f.steps[seq]["id"],
        m=f.mat["id"],
        qty=qty,
        u=uom,
    )


def _get(f: Line, url: str, status: int = 200, **params: Any) -> Any:
    r = f.c.get(url, headers=f.m.h, params=params)
    assert r.status_code == status, r.text
    return r.json()


def test_uom_precision_and_count_units(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    m = f.m
    ea = m.fx("uom")  # count
    box = m.post("uom", {"code": "BOX", "name": "box", "dimension": "count"})["id"]
    g = m.post("uom", {"code": "G", "name": "g", "dimension": "mass"})["id"]
    kg = m.post("uom", {"code": "KG", "name": "kg", "dimension": "mass"})["id"]
    m.post("uom_conversion", {"from_uom_id": box, "to_uom_id": ea, "factor": 3})
    m.post("uom_conversion", {"from_uom_id": kg, "to_uom_id": g, "factor": 1000})
    conv = f"{API}/_convert"
    # 6 位小数四舍五入
    assert _get(f, conv, from_uom=g, to_uom=kg, value=1.2345678)["value"] == 0.001235
    assert _get(f, conv, from_uom=box, to_uom=ea, value=2)["value"] == 6
    # 换算到计件单位不是整数 → 422
    r = _get(f, conv, 422, from_uom=ea, to_uom=box, value=4)
    assert "whole number" in str(r)
    # 计件单位录入非整数 → 422；质量单位可带小数（保留 6 位）
    base = {"material_id": f.mat["id"], "expiry_date": "2030-01-01"}
    r = m.post(
        "material_lot", {**base, "code": "X1", "qty_remaining": 1.5, "uom_id": ea}, 422
    )
    assert "qty_remaining" in str(r)
    ok = m.post(
        "material_lot",
        {**base, "code": "X2", "qty_remaining": 1.23456789, "uom_id": g},
    )
    assert ok["qty_remaining"] == 1.234568 and ok["initial_qty"] == 1.234568
    m.post("material_lot", {**base, "code": "X3", "qty_remaining": 2, "uom_id": ea})


def test_track_out_bom_comparison(client: TestClient, db: Session) -> None:
    f = Line(client, db, {20: {"rework_return": "same_step"}})
    m = f.m
    g = m.post("uom", {"code": "G", "name": "g", "dimension": "mass"})["id"]
    kg = m.post("uom", {"code": "KG", "name": "kg", "dimension": "mass"})["id"]
    m.post("uom_conversion", {"from_uom_id": kg, "to_uom_id": g, "factor": 1000})
    _res(f, 10, g, 1.5)  # OP0：每片 1.5 g
    _res(f, 20, g, 2)  # OP1：每片 2 g
    m.post(
        "material_lot",
        {
            "code": "MLG",
            "material_id": f.mat["id"],
            "qty_remaining": 100,
            "uom_id": g,
            "expiry_date": "2030-01-01",
        },
    )
    bom = m.post("bom", {"product_id": f.product["id"]})
    line = {"bom_id": bom["id"], "component_type": "material", "consume_mode": "issue"}
    # OP0 计划 1 g/片（会超量）；OP1 计划 0.002 kg/片 + 10% 损耗（换算后比较）
    m.post(
        "bom_line",
        {
            **line,
            "line_no": 10,
            "material_id": f.mat["id"],
            "qty": 1,
            "uom_id": g,
            "operation_id": f.ops[0]["id"],
        },
    )
    m.post(
        "bom_line",
        {
            **line,
            "line_no": 20,
            "material_id": f.mat["id"],
            "qty": 0.002,
            "uom_id": kg,
            "scrap_rate": 0.1,
            "operation_id": f.ops[1]["id"],
        },
    )
    r = client.post(f"{API}/bom/{bom['id']}/activate", headers=m.h)
    assert r.status_code == 200, r.text
    (lot,) = f.start(2)
    # OP0：实际 3 g > 计划 2 g → 只提示，出站成功
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    out = f.stage(lot, "track_out")
    assert f.lot(lot)["lot_status"] == "tracked_out"
    (w,) = out["warnings"]
    assert w["code"] == "bom_over_consumption"
    assert [(x["line_no"], x["planned"], x["actual"]) for x in w["lines"]] == [
        (10, 2, 3)
    ]
    h = m.list("lot_history", lot=lot["id"], action="bom_over_consumption")["data"]
    assert len(h) == 1 and h[0]["details"]["lines"][0]["material"] == f.mat["code"]
    f.stage(lot, "move_out")
    # OP1：4 g = 0.004 kg ≤ 2 × 0.002 × 1.1 = 0.0044 kg → 无提示
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    out = f.stage(lot, "track_out")
    assert out["warnings"] == []
    assert [(x["planned"], x["actual"], x["over"]) for x in out["bom_usage"]] == [
        (0.0044, 0.004, False)
    ]
    # 返工后回到同一工步重做：用量记为 rework，不参与比对
    f.stage(lot, "move_out", rework=True)
    f.run_step(lot)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    out = f.stage(lot, "track_out")
    assert out["warnings"] == [] and out["bom_usage"][0]["actual"] == 0.004
    recs = m.list("material_consumption", lot=lot["id"])["data"]
    assert sorted((float(x["qty"]), x["usage_type"], x["source"]) for x in recs) == [
        (3.0, "normal", "step_resource"),
        (4.0, "normal", "step_resource"),
        (4.0, "rework", "step_resource"),
    ]
    # 用量总览：全部 issue 明细的累计正常用量
    u = _get(f, f"{EXEC}/lots/{lot['id']}/bom-usage")
    assert u["bom_version"] == 1 and u["basis"] == 2
    assert [(x["line_no"], x["actual"], x["over"]) for x in u["lines"]] == [
        (10, 3, True),
        (20, 0.004, False),
    ]
    assert _get(f, f"{EXEC}/lots/{f.wo['id']}/bom-usage", 404)


def test_migration_0016_consumption_event_index() -> None:
    """0016 可重复执行；external_event_id 列与部分唯一索引与表定义（partial_unique）一致；"""
    import os
    import subprocess
    from pathlib import Path

    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.engine import make_url
    from sqlmodel import SQLModel

    from app.core.config import settings

    base = make_url(settings.migration_database_url)
    name = f"{base.database}_mig_b2e"
    server = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with server.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = base.set(database=name).render_as_string(hide_password=False)
    backend = Path(__file__).resolve().parents[4]

    def alembic(*args: str) -> None:
        env = {**os.environ, "MIGRATION_DATABASE_URL": url}
        r = subprocess.run(
            ["alembic", *args], cwd=backend, env=env, capture_output=True, text=True
        )
        assert r.returncode == 0, r.stderr[-2000:]

    T, IDX = "mes_material_consumption", "uq_mes_mat_consumption_event"
    eng = create_engine(url)

    def state() -> tuple[bool, bool]:
        with eng.connect() as c:
            i = inspect(c)
            col = any(x["name"] == "external_event_id" for x in i.get_columns(T))
            return col, any(x["name"] == IDX for x in i.get_indexes(T))

    try:
        alembic("upgrade", "head")
        assert state() == (True, True)
        with eng.connect() as c:
            diffs = compare_metadata(MigrationContext.configure(c), SQLModel.metadata)
        flat = [d for x in diffs for d in (x if isinstance(x, list) else [x])]
        bad = [d for d in flat if T in str(d)]
        assert not bad, bad
        alembic("stamp", "0015_material_consumption")
        alembic("upgrade", "head")  # 已存在：不报错
        alembic("downgrade", "0015_material_consumption")
        assert state() == (False, False)
        alembic("stamp", "head")
        alembic("downgrade", "0015_material_consumption")  # 已不在：不报错
        alembic("upgrade", "head")
        assert state() == (True, True)
    finally:
        eng.dispose()
        with server.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        server.dispose()


def test_consumption_event_unique(client: TestClient, db: Session) -> None:
    """同一来源同一外部事件号只能一条；不同来源或事件号为空不受限。"""
    import pytest
    from sqlalchemy.exc import IntegrityError

    f = Line(client, db)
    m = f.m
    g = m.post("uom", {"code": "G", "name": "g", "dimension": "mass"})["id"]
    _res(f, 10, g, 1)
    m.post(
        "material_lot",
        {
            "code": "MLG",
            "material_id": f.mat["id"],
            "qty_remaining": 100,
            "uom_id": g,
            "expiry_date": "2030-01-01",
        },
    )
    (lot,) = f.start(1)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_out")
    (rec,) = m.list("material_consumption", lot=lot["id"])["data"]
    assert rec["external_event_id"] is None
    copy = (
        "INSERT INTO mes_material_consumption (id, tenant_id, lot_id, qty, source,"
        " usage_type, external_event_id) SELECT gen_random_uuid(), tenant_id, lot_id,"
        " qty, :src, usage_type, :ev FROM mes_material_consumption WHERE id = :id"
    )
    f.sql(copy, src="eap", ev=None, id=rec["id"])  # 空事件号：不受限
    f.sql(copy, src="eap", ev="EV-1", id=rec["id"])
    f.sql(copy, src="manual", ev="EV-1", id=rec["id"])  # 不同来源：可以
    with pytest.raises(IntegrityError):
        f.sql(copy, src="eap", ev="EV-1", id=rec["id"])


def test_qty_decimal_half_up() -> None:
    """D31：数量先转 Decimal 再 ROUND_HALF_UP 到 6 位，浮点误差不进入结果。"""
    from decimal import Decimal

    from app.mes.common.uom import round_qty, to_qty

    assert 0.1 + 0.2 != 0.3 and to_qty(0.1 + 0.2) == Decimal("0.300000")
    assert to_qty(0.1 * 3) == Decimal("0.300000")
    assert to_qty(1.0000005) == Decimal("1.000001")  # 半数进位（round() 会得 1.0）
    assert to_qty(Decimal("2.0000025")) == Decimal("2.000003")
    assert to_qty(5e-7) == Decimal("0.000001") and round_qty(0.1 + 0.2) == 0.3


def test_consumption_float_error_and_bom_usage_scope(
    client: TestClient, db: Session
) -> None:
    """用料记录与比对不带浮点误差（每片 0.1 × 3 片 = 0.3）；bom-usage 说明只算本批，
    拆出的子批带 parent_lot_id。"""
    from app.mes.execution.tests.test_split_merge import _line, split, uid

    f = _line(client, db)
    m = f.m
    g = m.post("uom", {"code": "G", "name": "g", "dimension": "mass"})["id"]
    _res(f, 10, g, 0.1)
    m.post(
        "material_lot",
        {
            "code": "MLG",
            "material_id": f.mat["id"],
            "qty_remaining": 1,
            "uom_id": g,
            "expiry_date": "2030-01-01",
        },
    )
    bom = m.post("bom", {"product_id": f.product["id"]})
    m.post(
        "bom_line",
        {
            "bom_id": bom["id"],
            "line_no": 10,
            "component_type": "material",
            "consume_mode": "issue",
            "material_id": f.mat["id"],
            "qty": 0.1,
            "uom_id": g,
            "operation_id": f.ops[0]["id"],
        },
    )
    assert (
        client.post(f"{API}/bom/{bom['id']}/activate", headers=m.h).status_code == 200
    )
    (lot,) = f.start(5)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    r = split(f, lot, [{"unit_ids": uid(f, lot, 0, 1)}])
    (ch,) = r["children"]
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    out = f.stage(lot, "track_out")  # 3 片 × 0.1 g
    assert out["consumed"] == [{"material_lot": "MLG", "qty": 0.3, "left": 0.7}]
    assert out["warnings"] == [] and out["bom_usage"][0]["actual"] == 0.3
    raw = f.sql(
        "SELECT qty::text FROM mes_material_consumption WHERE lot_id = :l", l=lot["id"]
    )
    assert [x[0] for x in raw] == ["0.300000"]
    left = f.sql("SELECT qty_remaining::text FROM mes_material_lot WHERE code = 'MLG'")
    assert left[0][0] == "0.700000"
    u = _get(f, f"{EXEC}/lots/{lot['id']}/bom-usage")
    assert u["scope"] == "lot_only" and u["scope_note"] and u["parent_lot_id"] is None
    assert u["lines"][0]["actual"] == 0.3 and u["lines"][0]["planned"] == 0.3
    c = _get(f, f"{EXEC}/lots/{ch['id']}/bom-usage")
    assert c["parent_lot_id"] == lot["id"] and c["lines"][0]["actual"] == 0


def _bom_lines(f: Line, *lines: dict[str, Any]) -> None:
    m = f.m
    bom = m.post("bom", {"product_id": f.product["id"]})
    for i, ln in enumerate(lines):
        m.post(
            "bom_line",
            {
                "bom_id": bom["id"],
                "line_no": (i + 1) * 10,
                "component_type": "material",
                "consume_mode": "issue",
                "material_id": f.mat["id"],
                **ln,
            },
        )
    r = f.c.post(f"{API}/bom/{bom['id']}/activate", headers=m.h)
    assert r.status_code == 200, r.text


def _g_lot(f: Line) -> str:
    g = f.m.post("uom", {"code": "G", "name": "g", "dimension": "mass"})["id"]
    f.m.post(
        "material_lot",
        {
            "code": "MLG",
            "material_id": f.mat["id"],
            "qty_remaining": 100,
            "uom_id": g,
            "expiry_date": "2030-01-01",
        },
    )
    return str(g)


def test_over_alert_only_when_excess_grows(client: TestClient, db: Session) -> None:
    """D32-1：累计超出量比上次报警时更大才再报；warnings 与履历同一判断；返工重做不报。"""
    f = Line(
        client,
        db,
        {20: {"rework_return": "same_step"}},
    )
    f.sql(
        "UPDATE mes_route_step SET operation_id = :o WHERE id = :s",
        o=f.ops[0]["id"],
        s=f.steps[20]["id"],
    )  # 10、20 两个工步同属 OP0
    g = _g_lot(f)
    _res(f, 10, g, 1.5)
    _res(f, 20, g, 1)
    _bom_lines(f, {"qty": 1, "uom_id": g, "operation_id": f.ops[0]["id"]})
    (lot,) = f.start(2)

    def out() -> Any:
        f.stage(lot, "move_in", equipment_id=f.eq["id"])
        f.stage(lot, "track_in", equipment_id=f.eq["id"])
        return f.stage(lot, "track_out")

    def alerts() -> int:
        return int(
            f.m.list("lot_history", lot=lot["id"], action="bom_over_consumption")[
                "count"
            ]
        )

    r = out()  # 3 g / 计划 2 g：超 1 → 报
    assert r["warnings"][0]["lines"][0]["excess"] == 1 and alerts() == 1
    f.stage(lot, "move_out")
    r = out()  # 累计 5 g：超 3 > 1 → 再报
    assert r["warnings"][0]["lines"][0]["excess"] == 3 and alerts() == 2
    f.stage(lot, "move_out", rework=True)
    f.run_step(lot)
    r = out()  # 返工重做：用量记 rework，正常累计不变 → 两边都不报
    assert r["warnings"] == [] and r["bom_usage"][0]["excess"] == 3
    assert alerts() == 2


def test_same_material_two_lines_allocation(client: TestClient, db: Session) -> None:
    """D32-2：绑定工序上的用量记到绑定明细，其他工序的记到未绑工序明细；超出不挤占。"""
    f = Line(client, db)
    g = _g_lot(f)
    _res(f, 10, g, 1.5)  # OP0：3 g
    _res(f, 40, g, 0.5)  # OP2（最后一步）：1 g
    _bom_lines(
        f,
        {"qty": 1, "uom_id": g, "operation_id": f.ops[0]["id"]},  # 绑 OP0
        {"qty": 1, "uom_id": g},  # 未绑工序
    )
    (lot,) = f.start(2)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    r = f.stage(lot, "track_out")
    assert [(x["line_no"], x["actual"]) for x in r["bom_usage"]] == [(10, 3)]
    assert r["warnings"][0]["lines"][0]["line_no"] == 10
    f.stage(lot, "move_out")
    for _ in range(2):  # 20、SUB#10
        f.run_step(lot)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    r = f.stage(lot, "track_out")  # 最后一步只比未绑工序明细：1 g ≤ 2 g，不报
    assert [(x["line_no"], x["actual"], x["over"]) for x in r["bom_usage"]] == [
        (20, 1, False)
    ]
    assert r["warnings"] == []
    u = _get(f, f"{EXEC}/lots/{lot['id']}/bom-usage")
    assert "operation" in u["allocation_rule"]
    assert [(x["line_no"], x["actual"], x["excess"]) for x in u["lines"]] == [
        (10, 3, 1),
        (20, 1, 0),
    ]
