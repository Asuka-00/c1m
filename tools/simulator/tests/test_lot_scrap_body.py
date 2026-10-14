"""lot_scrap：晶圆 / 单元级按 unit_ids，数量级按 qty（后端 adjust.py:82-94）。"""

from __future__ import annotations

from sim.p3 import active_units, scrap_body

UNITS = [
    {"id": "u2", "code": "L.02", "slot": 2, "wafer_status": "processing"},
    {"id": "u1", "code": "L.01", "slot": 1, "wafer_status": "processing"},
    {"id": "u3", "code": "L.03", "slot": 3, "wafer_status": "scrapped"},
    {"id": "u4", "code": "L.04", "slot": 4, "wafer_status": "converted"},
]


def test_wafer_lot_uses_remaining_unit_ids():
    b = scrap_body({"tracking_level": "wafer", "qty": 2}, UNITS, {}, "r1", "c")
    assert b == {"kind": "scrap", "reason_id": "r1", "comment": "c", "unit_ids": ["u1", "u2"]}
    assert "qty" not in b


def test_unit_lot_and_default_level_use_unit_ids():
    assert scrap_body({"tracking_level": "unit"}, UNITS, {"units": 1}, "r", "c")["unit_ids"] == ["u1"]
    assert scrap_body({}, UNITS, {"units": ["L.02", "L.03"]}, "r", "c")["unit_ids"] == ["u2"]


def test_quantity_lot_uses_qty():
    b = scrap_body({"tracking_level": "quantity", "qty": "5.000"}, [], {}, "r", "c")
    assert b["qty"] == 5 and "unit_ids" not in b
    assert scrap_body({"tracking_level": "quantity", "qty": 5}, [], {"qty": 2}, "r", "c")["qty"] == 2


def test_active_units_sorted_by_slot():
    assert [u["id"] for u in active_units(UNITS)] == ["u1", "u2"]


def test_override_passthrough():
    b = scrap_body({"tracking_level": "wafer"}, UNITS, {"override": True, "override_reason": "x"}, "r", "c")
    assert b["override"] is True and b["override_reason"] == "x"
    assert "override" not in scrap_body({"tracking_level": "wafer"}, UNITS, {}, "r", "c")
