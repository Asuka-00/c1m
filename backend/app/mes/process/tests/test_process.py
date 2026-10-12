"""MES phase 3: process modeling."""

from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.testing.mes import API, Mes


def _ops(m: Mes) -> dict[str, Any]:
    return {
        c: m.post("operation", {"code": c, "name": c, "operation_type": t})["id"]
        for c, t in [
            ("COAT", "process"),
            ("EXPO", "process"),
            ("DEV", "process"),
            ("CD", "metrology"),
            ("STRIP", "clean"),
        ]
    }


def test_route_steps_versions_and_activation(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    op = _ops(m)
    rw = m.post(
        "route", {"code": "RW-PH", "name": "Photo rework", "route_type": "rework"}
    )
    m.post("route_step", {"route_id": rw["id"], "seq": 10, "operation_id": op["STRIP"]})
    sub = m.post(
        "route", {"code": "SUB-PH", "name": "Photo module", "route_type": "sub"}
    )
    for i, c in enumerate(["COAT", "EXPO", "DEV"]):
        m.post(
            "route_step",
            {"route_id": sub["id"], "seq": (i + 1) * 10, "operation_id": op[c]},
        )
    main = m.post("route", {"code": "MAIN", "name": "Main flow", "route_type": "main"})
    s1 = m.post(
        "route_step",
        {
            "route_id": main["id"],
            "seq": 10,
            "step_type": "sub_route",
            "sub_route_id": sub["id"],
        },
    )
    m.post(
        "route_step",
        {
            "route_id": main["id"],
            "seq": 20,
            "operation_id": op["CD"],
            "rework_route_id": rw["id"],
            "branch_condition": "cd_out_of_spec",
            "branch_to_seq": 10,
        },
    )
    # validation
    m.post("route_step", {"route_id": main["id"], "seq": 30}, 422)  # operation missing
    m.post(
        "route_step",
        {
            "route_id": main["id"],
            "seq": 30,
            "step_type": "sub_route",
            "sub_route_id": rw["id"],
        },
        422,
    )
    m.post(
        "route_step",
        {
            "route_id": main["id"],
            "seq": 30,
            "operation_id": op["CD"],
            "rework_route_id": sub["id"],
        },
        422,
    )
    m.post(
        "route_step", {"route_id": main["id"], "seq": 20, "operation_id": op["CD"]}, 409
    )
    m.post(
        "route_step",
        {
            "route_id": main["id"],
            "seq": 30,
            "operation_id": op["CD"],
            "branch_to_seq": 10,
        },
        422,
    )
    # activation requires active sub / rework routes
    m.action("route", main["id"], "status", {"status": "active"}, 422)
    m.action("route", sub["id"], "status", {"status": "active"})
    m.action("route", rw["id"], "status", {"status": "active"})
    empty = m.post("route", {"code": "EMPTY", "name": "x"})
    m.action("route", empty["id"], "status", {"status": "active"}, 422)
    m.action("route", main["id"], "status", {"status": "active"})
    # active route: steps locked
    m.patch("route_step", s1["id"], {"seq": 15}, 409)
    m.post(
        "route_step", {"route_id": main["id"], "seq": 30, "operation_id": op["CD"]}, 409
    )
    # new version copies steps (+ resources) as a draft
    v2 = m.action("route", main["id"], "new-version")
    steps = m.list("route_step", route_id=v2["id"])["data"]
    assert [(s["seq"], s["step_type"]) for s in steps] == [
        (10, "sub_route"),
        (20, "operation"),
    ]
    assert steps[1]["rework_route_label"] == "RW-PH v1 · Photo rework"
    # reorder (draft only)
    r = client.post(
        f"{API}/route/{v2['id']}/reorder",
        headers=m.h,
        json={"step_ids": [steps[1]["id"], steps[0]["id"]]},
    )
    assert r.status_code == 200, r.text
    assert [(s["seq"], s["step_type"]) for s in r.json()["data"]] == [
        (10, "operation"),
        (20, "sub_route"),
    ]
    assert (
        client.post(
            f"{API}/route/{v2['id']}/reorder",
            headers=m.h,
            json={"step_ids": [steps[0]["id"]]},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{API}/route/{main['id']}/reorder", headers=m.h, json={"step_ids": []}
        ).status_code
        == 409
    )


def test_step_resources_and_product_binding(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    op = _ops(m)
    et = m.post(
        "equipment_type", {"code": "SCN", "name": "Scanner", "category": "process"}
    )
    eq = m.post(
        "equipment",
        {
            "code": "SCN01",
            "name": "Scanner 1",
            "unit_kind": "main",
            "equipment_type_id": et["id"],
        },
    )
    g = m.post(
        "equipment_group", {"code": "G1", "name": "G1", "equipment_type_id": et["id"]}
    )
    rt = m.post("reticle", {"code": "RT1", "name": "RT1", "layer": "M1"})
    route = m.post("route", {"code": "R", "name": "R"})
    st = m.post(
        "route_step", {"route_id": route["id"], "seq": 10, "operation_id": op["EXPO"]}
    )
    m.post(
        "step_resource",
        {
            "route_step_id": st["id"],
            "resource_kind": "equipment_group",
            "equipment_group_id": g["id"],
        },
    )
    m.post(
        "step_resource",
        {"route_step_id": st["id"], "resource_kind": "reticle", "reticle_id": rt["id"]},
    )
    m.post(
        "step_resource", {"route_step_id": st["id"], "resource_kind": "reticle"}, 422
    )
    m.post(
        "step_resource",
        {
            "route_step_id": st["id"],
            "resource_kind": "reticle",
            "reticle_id": rt["id"],
            "equipment_id": eq["id"],
        },
        422,
    )
    assert m.list("step_resource", route_step_id=st["id"])["count"] == 2
    v2 = m.action("route", route["id"], "new-version")
    st2 = m.list("route_step", route_id=v2["id"])["data"][0]
    assert m.list("step_resource", route_step_id=st2["id"])["count"] == 2  # deep copy
    prod = m.post("product", {"code": "P1", "name": "P1"})
    m.post(
        "product_route",
        {
            "product_id": prod["id"],
            "route_id": route["id"],
            "effective_from": "2026-01-01",
            "effective_to": "2026-12-31",
        },
    )
    m.post(
        "product_route",
        {
            "product_id": prod["id"],
            "route_id": v2["id"],
            "effective_from": "2026-12-31",
            "effective_to": "2026-01-01",
        },
        422,
    )
    sub = m.post("route", {"code": "S", "name": "S", "route_type": "sub"})
    m.post("product_route", {"product_id": prod["id"], "route_id": sub["id"]}, 422)


def test_recipes_specs_capability(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    op = _ops(m)
    scn = m.post(
        "equipment_type", {"code": "SCN", "name": "Scanner", "category": "process"}
    )
    etc = m.post(
        "equipment_type", {"code": "ETC", "name": "Etcher", "category": "process"}
    )
    e1 = m.post(
        "equipment",
        {
            "code": "SCN01",
            "name": "S1",
            "unit_kind": "main",
            "equipment_type_id": scn["id"],
        },
    )
    e2 = m.post(
        "equipment",
        {
            "code": "ETC01",
            "name": "E1",
            "unit_kind": "main",
            "equipment_type_id": etc["id"],
        },
    )
    rec = m.post(
        "recipe",
        {
            "code": "EXPO-M1",
            "name": "M1 exposure",
            "equipment_type_id": scn["id"],
            "body": {"dose": 32.5, "focus": -0.02},
        },
    )
    assert rec["body"] == {"dose": 32.5, "focus": -0.02}
    m.post(
        "recipe_equipment",
        {"recipe_id": rec["id"], "equipment_id": e1["id"], "eqp_recipe": "M1_EXP_V3"},
    )
    m.post(
        "recipe_equipment", {"recipe_id": rec["id"], "equipment_id": e2["id"]}, 422
    )  # wrong type
    m.post(
        "param_spec",
        {
            "code": "DOSE",
            "name": "Dose",
            "recipe_id": rec["id"],
            "lsl": 30,
            "target": 32.5,
            "usl": 35,
        },
    )
    m.post(
        "param_spec",
        {"code": "DOSE", "name": "Dose", "recipe_id": rec["id"], "lsl": 30, "usl": 35},
        409,
    )
    m.post(
        "param_spec",
        {"code": "X", "name": "x", "operation_id": op["CD"], "lsl": 5, "usl": 1},
        422,
    )
    m.post(
        "param_spec",
        {
            "code": "X",
            "name": "x",
            "operation_id": op["CD"],
            "lsl": 1,
            "target": 9,
            "usl": 5,
        },
        422,
    )
    m.post("param_spec", {"code": "X", "name": "x", "lsl": 1}, 422)
    m.post(
        "param_spec",
        {"code": "CD", "name": "CD", "operation_id": op["CD"], "target": 45, "usl": 48},
    )
    m.post(
        "equipment_capability",
        {
            "equipment_id": e1["id"],
            "operation_id": op["EXPO"],
            "recipe_id": rec["id"],
            "qualified_until": "2027-01-01",
        },
    )
    m.post(
        "equipment_capability",
        {"equipment_id": e2["id"], "operation_id": op["EXPO"], "recipe_id": rec["id"]},
        422,
    )
    assert m.list("equipment_capability", equipment_id=e1["id"])["count"] == 1
    m.action("recipe", rec["id"], "status", {"status": "active"})
    v2 = m.action("recipe", rec["id"], "new-version")
    assert (
        m.list("recipe_equipment", recipe_id=v2["id"])["data"][0]["eqp_recipe"]
        == "M1_EXP_V3"
    )
