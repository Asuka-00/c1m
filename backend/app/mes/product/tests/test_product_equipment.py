"""MES phase 2: product/material + equipment."""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.testing.mes import API, Mes


def _bind_active_route(m: Mes, product_id: str) -> None:
    op = m.post("operation", {"code": f"OP-{product_id[:6]}", "name": "op"})
    r = m.post("route", {"code": f"R-{product_id[:6]}", "name": "r"})
    m.post("route_step", {"route_id": r["id"], "seq": 10, "operation_id": op["id"]})
    m.action("route", r["id"], "status", {"status": "active"})
    m.post(
        "product_route",
        {"product_id": product_id, "route_id": r["id"], "is_default": True},
    )


def test_product_activation_needs_default_route(
    client: TestClient, db: Session
) -> None:
    m = Mes(client, db)
    p = m.post("product", {"code": "P", "name": "P"})
    err = m.action("product", p["id"], "status", {"status": "active"}, 422)
    assert "default" in err["detail"][0]["msg"]
    op = m.post("operation", {"code": "OP", "name": "op"})
    draft = m.post("route", {"code": "RD", "name": "draft route"})
    m.post("route_step", {"route_id": draft["id"], "seq": 10, "operation_id": op["id"]})
    link = m.post(
        "product_route",
        {"product_id": p["id"], "route_id": draft["id"], "is_default": True},
    )
    m.action(
        "product", p["id"], "status", {"status": "active"}, 422
    )  # route not active
    m.action("route", draft["id"], "status", {"status": "active"})
    m.patch("product_route", link["id"], {"is_default": False})
    m.action("product", p["id"], "status", {"status": "active"}, 422)  # not default
    m.patch("product_route", link["id"], {"is_default": True})
    assert (
        m.action("product", p["id"], "status", {"status": "active"})["status"]
        == "active"
    )


def test_versioned_product_lifecycle(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    node = m.post("tech_node", {"code": "N28", "name": "28nm", "feature_nm": 28})
    fam = m.post(
        "product_family", {"code": "MCU", "name": "MCU", "tech_node_id": node["id"]}
    )
    p1 = m.post(
        "product",
        {"code": "MCU-A", "name": "MCU A", "family_id": fam["id"], "gross_die": 600},
    )
    assert (p1["version"], p1["status"], p1["family_label"]) == (
        1,
        "draft",
        "MCU · MCU",
    )
    m.patch("product", p1["id"], {"gross_die": 610})  # drafts are editable
    _bind_active_route(m, p1["id"])
    m.action("product", p1["id"], "status", {"status": "active"})
    m.patch("product", p1["id"], {"gross_die": 1}, 409)  # active is locked
    m.delete("product", p1["id"], 409)
    m.action("product", p1["id"], "status", {"status": "draft"}, 409)  # no way back
    p2 = m.action("product", p1["id"], "new-version")
    assert (p2["version"], p2["status"], p2["gross_die"]) == (2, "draft", 610)
    m.patch("product", p2["id"], {"gross_die": 620})
    _bind_active_route(m, p2["id"])
    m.action("product", p2["id"], "status", {"status": "active"})
    rows = {r["version"]: r["status"] for r in m.list("product", code="MCU-A")["data"]}
    assert rows == {1: "inactive", 2: "active"}  # single active version per code
    assert m.list("product", status="active")["count"] == 1
    m.action("product", p1["id"], "status", {"status": "bogus"}, 422)
    m.action(
        "tech_node", node["id"], "status", {"status": "active"}, 404
    )  # not versioned


def test_uom_conversion(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    u = {
        c: m.post("uom", {"code": c, "name": c, "dimension": d})["id"]
        for c, d in [
            ("L", "volume"),
            ("ML", "volume"),
            ("GAL", "volume"),
            ("KG", "mass"),
            ("C", "temperature"),
            ("F", "temperature"),
        ]
    }
    m.post(
        "uom_conversion", {"from_uom_id": u["L"], "to_uom_id": u["ML"], "factor": 1000}
    )
    m.post(
        "uom_conversion",
        {"from_uom_id": u["GAL"], "to_uom_id": u["L"], "factor": 3.785411784},
    )
    m.post(
        "uom_conversion",
        {"from_uom_id": u["C"], "to_uom_id": u["F"], "factor": 1.8, "offset": 32},
    )
    m.post(
        "uom_conversion",
        {"from_uom_id": u["L"], "to_uom_id": u["KG"], "factor": 1},
        422,
    )  # dimension
    m.post(
        "uom_conversion", {"from_uom_id": u["L"], "to_uom_id": u["L"], "factor": 1}, 422
    )
    m.post(
        "uom_conversion",
        {"from_uom_id": u["L"], "to_uom_id": u["ML"], "factor": 2},
        409,
    )
    m.post(
        "uom_conversion",
        {"from_uom_id": u["ML"], "to_uom_id": u["GAL"], "factor": 0},
        422,
    )

    def conv(a: str, b: str, v: float) -> float:
        r = client.get(
            f"{API}/_convert",
            headers=m.h,
            params={"from_uom": u[a], "to_uom": u[b], "value": v},
        )
        assert r.status_code == 200, r.text
        return float(r.json()["value"])

    assert conv("GAL", "ML", 1) == 3785.411784  # two hops
    assert round(conv("ML", "GAL", 3785.411784), 9) == 1  # inverse
    assert conv("C", "F", 100) == 212 and round(conv("F", "C", 32), 9) == 0
    assert (
        client.get(
            f"{API}/_convert",
            headers=m.h,
            params={"from_uom": u["L"], "to_uom": u["KG"]},
        ).status_code
        == 422
    )


def test_material_carrier_reticle(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    liter = m.post("uom", {"code": "L", "name": "Liter", "dimension": "volume"})
    mt = m.post(
        "material_type", {"code": "CHEM", "name": "Chemicals", "category": "chemical"}
    )
    m.post(
        "material",
        {
            "code": "H2SO4",
            "name": "Sulfuric acid",
            "material_type_id": mt["id"],
            "uom_id": liter["id"],
            "shelf_life_days": 365,
        },
    )
    m.post(
        "material", {"code": "X", "name": "x", "material_type_id": mt["id"]}, 422
    )  # uom required
    ct = m.post(
        "carrier_type",
        {"code": "FOUP25", "name": "FOUP 25", "category": "foup", "capacity": 25},
    )
    m.post(
        "carrier_type",
        {"code": "BAD", "name": "x", "category": "foup", "capacity": 0},
        422,
    )
    c = m.post(
        "carrier", {"code": "FP0001", "name": "FOUP 1", "carrier_type_id": ct["id"]}
    )
    assert c["status_code"] == "available"
    m.post(
        "reticle",
        {
            "code": "RT-M1",
            "name": "M1 mask",
            "layer": "M1",
            "grade": "psm",
            "max_shots": 100000,
        },
    )
    assert m.list("reticle", grade="psm")["count"] == 1
    m.delete("carrier_type", ct["id"], 409)  # in use


def test_equipment_tree_and_e10(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    et = m.post(
        "equipment_type",
        {
            "code": "ETCHER",
            "name": "Dry etcher",
            "category": "process",
            "vendor": "LAM",
        },
    )
    idle = m.post(
        "e10_state",
        {"code": "SBY-IDLE", "name": "Idle", "e10_category": "SBY", "is_initial": True},
    )
    m.post(
        "e10_state",
        {"code": "SBY-X", "name": "x", "e10_category": "SBY", "is_initial": True},
        422,
    )
    run = m.post(
        "e10_state", {"code": "PRD-RUN", "name": "Running", "e10_category": "PRD"}
    )
    m.post("e10_transition", {"from_state_id": idle["id"], "to_state_id": run["id"]})
    m.post(
        "e10_transition", {"from_state_id": idle["id"], "to_state_id": idle["id"]}, 422
    )
    m.post(
        "e10_transition", {"from_state_id": idle["id"], "to_state_id": run["id"]}, 409
    )
    assert (
        m.list("e10_transition", from_state_id=idle["id"])["data"][0]["to_state_label"]
        == "PRD-RUN · Running"
    )
    main = m.post(
        "equipment",
        {
            "code": "ET01",
            "name": "Etcher 01",
            "unit_kind": "main",
            "equipment_type_id": et["id"],
            "initial_state_id": idle["id"],
        },
    )
    ch = m.post(
        "equipment",
        {
            "code": "ET01-PM1",
            "name": "Chamber 1",
            "unit_kind": "chamber",
            "parent_id": main["id"],
        },
    )
    m.post(
        "equipment",
        {
            "code": "ET01-LP1",
            "name": "Load port 1",
            "unit_kind": "load_port",
            "parent_id": main["id"],
        },
    )
    m.post("equipment", {"code": "LOOSE", "name": "x", "unit_kind": "chamber"}, 422)
    m.post(
        "equipment",
        {"code": "SUB", "name": "x", "unit_kind": "chamber", "parent_id": ch["id"]},
        422,
    )
    m.post(
        "equipment",
        {"code": "M2", "name": "x", "unit_kind": "main", "parent_id": main["id"]},
        422,
    )
    tree = client.get(m.url("equipment", "tree"), headers=m.h).json()
    assert [c["code"] for c in tree[0]["children"]] == ["ET01-LP1", "ET01-PM1"]
    assert m.list("equipment", unit_kind="chamber")["count"] == 1


def test_module_permissions(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    meta = client.get(f"{API}/_meta", headers=m.h).json()
    mods = {e["module"] for e in meta["entities"]}
    assert {"product", "equipment"} <= mods
    assert (
        next(e for e in meta["entities"] if e["code"] == "equipment")["write"]
        == "mes.equipment:write"
    )
