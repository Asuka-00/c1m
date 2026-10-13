"""R2: required fields and conditional requirements."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.testing.mes import API, Mes


def _errs(m: Mes, e: str, body: dict[str, Any]) -> dict[str, str]:
    r = m.c.post(m.url(e), headers=m.h, json=body)
    assert r.status_code == 422, r.text
    return {d["loc"][1]: d["msg"] for d in r.json()["detail"]}


def _no_err(m: Mes, e: str, body: dict[str, Any], field: str) -> None:
    r = m.c.post(m.url(e), headers=m.h, json=body)
    if r.status_code == 422:
        assert field not in {d["loc"][1] for d in r.json()["detail"]}, r.text


@pytest.mark.parametrize(
    "entity,field",
    [
        ("equipment_group", "equipment_type"),
        ("product_family", "tech_node"),
        ("product", "uom"),
        ("reticle", "product"),
        ("reticle", "layer"),
        ("operation", "area"),
        ("recipe", "equipment_type"),
        ("dc_plan", "operation"),
        ("sampling_rule", "operation"),
        ("lot_type", "default_priority"),
        ("lot_type", "lot_id_rule"),
        ("lot_type", "wafer_id_rule"),
        ("split_merge_rule", "lot_type"),
        ("param_spec", "uom"),
    ],
)
def test_required_fields(
    client: TestClient, db: Session, entity: str, field: str
) -> None:
    m = Mes(client, db)
    errs = _errs(
        m, entity, {"code": "X", "name": "x", f"{field}_id": None, field: None}
    )
    assert errs[field] == f"{field}: required"


def test_dict_item_value_defaults_to_code(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    dt = m.post("dict_type", {"code": "DT", "name": "dt"})
    a = m.post("dict_item", {"dict_type_id": dt["id"], "code": "A1", "name": "a"})
    b = m.post(
        "dict_item",
        {"dict_type_id": dt["id"], "code": "B1", "name": "b", "value": "bee"},
    )
    assert (a["value"], b["value"]) == ("A1", "bee")


def test_equipment_main_and_sub_units(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    errs = _errs(
        m,
        "equipment",
        {"code": "E", "name": "e", "equipment_type_id": None, "workcenter_id": None},
    )
    assert errs["equipment_type"] == "equipment_type: required when unit_kind = main"
    assert errs["workcenter"] == "workcenter: required when unit_kind = main"
    main = m.post("equipment", {"code": "E1", "name": "e1"})
    errs = _errs(
        m, "equipment", {"code": "E1-PM1", "name": "pm", "unit_kind": "chamber"}
    )
    assert errs["parent"] == "parent: required when unit_kind = chamber"
    # chamber inherits the parent's type, without needing a work center
    ch = m.post(
        "equipment",
        {
            "code": "E1-PM1",
            "name": "pm",
            "unit_kind": "chamber",
            "parent_id": main["id"],
        },
    )
    assert ch["equipment_type_id"] == main["equipment_type_id"]
    same = {
        "code": "E1-PM2",
        "name": "pm",
        "unit_kind": "chamber",
        "parent_id": main["id"],
    }
    m.post("equipment", {**same, "equipment_type_id": main["equipment_type_id"]})
    other = m.post(
        "equipment_type", {"code": "OT", "name": "o", "category": "metrology"}
    )
    errs = _errs(
        m, "equipment", {**same, "code": "E1-PM3", "equipment_type_id": other["id"]}
    )
    assert "must match the parent" in errs["equipment_type"]
    errs = _errs(
        m,
        "equipment",
        {**same, "code": "E1-PM3", "equipment_type_id": None, "parent_id": None},
    )
    assert "parent" in errs


def test_product_family_node_by_type(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    for pt in ("production", "engineering"):
        errs = _errs(
            m,
            "product",
            {
                "code": "P",
                "name": "p",
                "product_type": pt,
                "family_id": None,
                "tech_node_id": None,
            },
        )
        assert errs["family"] == f"family: required when product_type = {pt}"
        assert "tech_node" in errs
    m.post("product", {"code": "MON", "name": "m", "product_type": "monitor"})


def test_measurement_uom_when_numeric(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    errs = _errs(
        m, "measurement_item", {"code": "M", "name": "m", "meas_type": "numeric"}
    )
    assert errs["uom"] == "uom: required when meas_type = numeric"
    m.post("measurement_item", {"code": "M2", "name": "m", "meas_type": "count"})


def test_qtime_reason_and_resource_uom(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    # D25 / D26：原因码对任何处置都选填（hold 留空用 qtime_expired）；scrap 已去掉
    for act in ("warn", "hold", "rework"):
        _no_err(
            m,
            "qtime_rule",
            {"code": "Q", "name": "q", "action": act, "reason_id": None},
            "reason",
        )
    errs = _errs(m, "step_resource", {"resource_kind": "material", "qty": 2})
    assert errs["uom"] == "uom: required when qty = set"
    _no_err(m, "step_resource", {"resource_kind": "material"}, "uom")


def test_one_default_route_per_product(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    p = m.post("product", {"code": "P", "name": "p"})
    r1 = m.post("route", {"code": "R1", "name": "r"})
    r2 = m.post("route", {"code": "R2", "name": "r"})
    a = m.post("product_route", {"product_id": p["id"], "route_id": r1["id"]})
    errs = _errs(
        m,
        "product_route",
        {"product_id": p["id"], "route_id": r2["id"], "is_default": True},
    )
    assert "already has a default" in errs["is_default"]
    m.post(
        "product_route",
        {"product_id": p["id"], "route_id": r2["id"], "is_default": False},
    )
    m.patch("product_route", a["id"], {"priority": 2})  # editing itself is fine


def test_meta_exposes_conditions(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    r = client.get(f"{API}/_meta", headers=m.h)
    eq = next(e for e in r.json()["entities"] if e["code"] == "equipment")
    f = {x["name"]: x for x in eq["fields"]}
    assert f["equipment_type"]["required_when"] == {"unit_kind": ["main"]}
    assert "chamber" in f["parent"]["required_when"]["unit_kind"]
