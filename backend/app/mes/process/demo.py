from typing import Any

from app.mes.common.demo import ACTIVATE, _rows, add

# ---------------- P3: process ----------------
OPS = [
    ("PH-COAT", "Resist coat", "process", "PHOTO", 6),
    ("PH-EXPO", "Exposure", "process", "PHOTO", 3),
    ("PH-DEV", "Develop", "process", "PHOTO", 5),
    ("PH-CD", "After-develop CD measure", "metrology", "METRO", 4),
    ("PH-OVL", "Overlay measure", "metrology", "METRO", 4),
    ("PH-STRIP", "Resist strip (rework)", "clean", "PHOTO", 8),
    ("DF-OX", "Gate oxidation", "process", "DIFF", 180),
    ("TF-DEP", "PECVD oxide deposition", "process", "THIN", 25),
    ("ET-POLY", "Poly gate etch", "process", "ETCH", 12),
    ("ET-CLN", "Post-etch clean", "clean", "ETCH", 15),
    ("CMP-OX", "Oxide CMP", "process", "CMP", 10),
    ("IN-PART", "Particle inspection", "inspection", "METRO", 5),
]
for c, n, tp, area, mins in OPS:
    add(
        "operation",
        code=c,
        name=n,
        operation_type=tp,
        area=("area", area),
        std_minutes=mins,
    )
add("route", code="RW-PHOTO", name="Photo rework (DEMO)", route_type="rework")
add(
    "route_step",
    route=("route", "RW-PHOTO@1"),
    seq=10,
    operation=("operation", "PH-STRIP"),
)
add(
    "route_step",
    route=("route", "RW-PHOTO@1"),
    seq=20,
    operation=("operation", "IN-PART"),
)
add("route", code="SUB-PHOTO", name="Photo module (DEMO)", route_type="sub")
for i, op in enumerate(["PH-COAT", "PH-EXPO", "PH-DEV"]):
    add(
        "route_step",
        route=("route", "SUB-PHOTO@1"),
        seq=(i + 1) * 10,
        operation=("operation", op),
    )
add(
    "route",
    code="MCU40-MAIN",
    name="MCU 40nm front-end flow (DEMO)",
    route_type="main",
    product_family=("product_family", "MCU"),
)
MAIN = [
    (10, "operation", "DF-OX", {}),
    (20, "operation", "TF-DEP", {}),
    (
        30,
        "sub_route",
        None,
        {"sub_route": ("route", "SUB-PHOTO@1"), "note": "Gate photo"},
    ),
    (40, "operation", "PH-CD", {"rework_route": ("route", "RW-PHOTO@1")}),
    (
        50,
        "operation",
        "PH-OVL",
        {"rework_route": ("route", "RW-PHOTO@1"), "is_optional": True},
    ),
    (60, "operation", "ET-POLY", {}),
    (70, "operation", "ET-CLN", {}),
    (
        80,
        "operation",
        "IN-PART",
        {"branch_condition": "lot_type == 'ENG'", "branch_to_seq": 100},
    ),
    (90, "operation", "CMP-OX", {}),
    (100, "operation", "TF-DEP", {"note": "Cap oxide"}),
]
for seq, st, op, extra in _rows(MAIN):
    add(
        "route_step",
        route=("route", "MCU40-MAIN@1"),
        seq=seq,
        step_type=st,
        **({"operation": ("operation", op)} if op else {}),
        **extra,
    )
ACTIVATE.extend(
    [("route", "RW-PHOTO@1"), ("route", "SUB-PHOTO@1"), ("route", "MCU40-MAIN@1")]
)
for p in ("MCU-A100", "MCU-B200"):
    add(
        "product_route",
        product=("product", f"{p}@1"),
        route=("route", "MCU40-MAIN@1"),
        is_default=True,
        priority=1,
        effective_from="2026-01-01",
    )
for c, n, et, tp, body in _rows(
    [
        (
            "EXP-GATE",
            "Gate exposure 28mJ",
            "SCANNER",
            "production",
            {"dose_mj": 28.0, "focus_um": -0.03, "na": 1.35},
        ),
        (
            "COAT-ARF",
            "ArF resist coat 120nm",
            "TRACK",
            "production",
            {"spin_rpm": 1500, "bake_c": 110},
        ),
        (
            "ETCH-POLY",
            "Poly gate main etch",
            "DRYETCH",
            "production",
            {"rf_w": 600, "pressure_mtorr": 8, "cl2_sccm": 80},
        ),
        (
            "OX-GATE",
            "Dry gate oxide 3nm",
            "FURNACE",
            "production",
            {"temp_c": 850, "o2_slm": 10, "minutes": 45},
        ),
        ("SEASON-ET", "Etch chamber seasoning", "DRYETCH", "clean", {"minutes": 10}),
    ]
):
    add(
        "recipe",
        code=c,
        name=f"{n} (DEMO)",
        equipment_type=("equipment_type", et),
        recipe_type=tp,
        body=body,
    )
    ACTIVATE.append(("recipe", f"{c}@1"))
for rc, eqs in _rows(
    [
        ("EXP-GATE", ["SCN01"]),
        ("COAT-ARF", ["TRK01"]),
        ("ETCH-POLY", ["ETC01", "ETC02"]),
        ("OX-GATE", ["FRN01"]),
        ("SEASON-ET", ["ETC01", "ETC02"]),
    ]
):
    for eq in eqs:
        add(
            "recipe_equipment",
            recipe=("recipe", f"{rc}@1"),
            equipment=("equipment", eq),
            eqp_recipe=f"{rc.replace('-', '_')}_V1",
        )
for c, n, op, rc, tgt, lsl, usl, u in _rows(
    [
        ("DOSE", "Exposure dose", None, "EXP-GATE", 28.0, 27.0, 29.0, "MJCM2"),
        ("GATE-CD", "Gate CD after develop", "PH-CD", None, 45.0, 42.0, 48.0, "NM"),
        ("OVL-X", "Overlay X", "PH-OVL", None, 0.0, -8.0, 8.0, "NM"),
        ("OX-THK", "Gate oxide thickness", "DF-OX", "OX-GATE", 30.0, 28.5, 31.5, "A"),
        (
            "ETCH-RATE",
            "Poly etch rate",
            "ET-POLY",
            "ETCH-POLY",
            2500.0,
            2300.0,
            2700.0,
            "A",
        ),
    ]
):
    add(
        "param_spec",
        code=c,
        name=n,
        target=tgt,
        lsl=lsl,
        usl=usl,
        **({"operation": ("operation", op)} if op else {}),
        **({"recipe": ("recipe", f"{rc}@1")} if rc else {}),
        **({"uom": ("uom", u)} if u else {}),
    )
for eq, op, rc in _rows(
    [
        ("SCN01", "PH-EXPO", "EXP-GATE"),
        ("TRK01", "PH-COAT", "COAT-ARF"),
        ("TRK01", "PH-DEV", None),
        ("ETC01", "ET-POLY", "ETCH-POLY"),
        ("ETC02", "ET-POLY", "ETCH-POLY"),
        ("FRN01", "DF-OX", "OX-GATE"),
        ("CVD01", "TF-DEP", None),
        ("CMP01", "CMP-OX", None),
        ("CDS01", "PH-CD", None),
    ]
):
    add(
        "equipment_capability",
        equipment=("equipment", eq),
        operation=("operation", op),
        qualified_until="2027-06-30",
        **({"recipe": ("recipe", f"{rc}@1")} if rc else {}),
    )
# line-side consumption per step (qty, uom, basis)
MAT_QTY: dict[str, dict[str, Any]] = {
    "NF3": {"qty": 0.2, "uom": ("uom", "KG"), "qty_basis": "per_lot"},
    "SL-CU-01": {"qty": 0.05, "uom": ("uom", "L"), "qty_basis": "per_unit"},
}
for seq, kind, ref, rc in _rows(
    [
        (10, "equipment_group", ("equipment_group", "G-FURN"), "OX-GATE"),
        (20, "equipment_group", ("equipment_group", "G-CVD"), None),
        (40, "equipment", ("equipment", "CDS01"), None),
        (60, "equipment_group", ("equipment_group", "G-ETCH"), "ETCH-POLY"),
        (60, "material", ("material", "NF3"), None),
        (90, "equipment", ("equipment", "CMP01"), None),
        (90, "material", ("material", "SL-CU-01"), None),
    ]
):
    add(
        "step_resource",
        route_step=("route_step", f"MCU40-MAIN@1#{seq}"),
        resource_kind=kind,
        **{kind: ref},
        **({"recipe": ("recipe", f"{rc}@1")} if rc else {}),
        **MAT_QTY.get(ref[1] if kind == "material" else "", {}),
    )
for seq, kind, ref, rc in _rows(
    [
        (10, "equipment_group", ("equipment_group", "G-TRACK"), "COAT-ARF"),
        (20, "equipment", ("equipment", "SCN01"), "EXP-GATE"),
        (20, "reticle", ("reticle", "RT-A100-PO"), None),
        (30, "equipment_group", ("equipment_group", "G-TRACK"), None),
    ]
):
    add(
        "step_resource",
        route_step=("route_step", f"SUB-PHOTO@1#{seq}"),
        resource_kind=kind,
        **{kind: ref},
        **({"recipe": ("recipe", f"{rc}@1")} if rc else {}),
    )
