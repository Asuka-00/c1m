"""产品演示数据（单位、技术节点、产品、物料、载具、光罩）。"""

from app.mes.common.demo import _rows, add

# ---------------- P2: product/material + equipment ----------------
for c, n, sym, d in _rows(
    [
        ("EA", "Each", "ea", "count"),
        ("WFR", "Wafer", "wfr", "count"),
        ("L", "Liter", "L", "volume"),
        ("ML", "Milliliter", "mL", "volume"),
        ("GAL", "US gallon", "gal", "volume"),
        ("KG", "Kilogram", "kg", "mass"),
        ("G", "Gram", "g", "mass"),
        ("SCCM", "Std. cubic cm / min", "sccm", "volume"),
        ("MIN", "Minute", "min", "time"),
        ("NM", "Nanometer", "nm", "length"),
        ("A", "Angstrom", "Å", "length"),
        ("MJCM2", "Millijoule / cm²", "mJ/cm²", "energy_density"),
    ]
):
    add("uom", code=c, name=n, symbol=sym, dimension=d)
for a, b, fct in _rows(
    [
        ("L", "ML", 1000),
        ("GAL", "L", 3.785411784),
        ("KG", "G", 1000),
        ("NM", "A", 10),
    ]
):
    add("uom_conversion", from_uom=("uom", a), to_uom=("uom", b), factor=fct)
add("tech_node", code="N28", name="28 nm HKMG (DEMO)", feature_nm=28, wafer_size="300")
add("tech_node", code="N40", name="40 nm LP (DEMO)", feature_nm=40, wafer_size="300")
add(
    "product_family",
    code="MCU",
    name="Microcontrollers",
    tech_node=("tech_node", "N40"),
)
add(
    "product_family",
    code="PMIC",
    name="Power management",
    tech_node=("tech_node", "N28"),
)
for c, n, fam, node, die in _rows(
    [
        ("MCU-A100", "MCU A100 (DEMO)", "MCU", "N40", 1450),
        ("MCU-B200", "MCU B200 (DEMO)", "MCU", "N40", 980),
        ("PM-X10", "PMIC X10 (DEMO)", "PMIC", "N28", 2210),
    ]
):
    add(
        "product",
        code=c,
        name=n,
        family=("product_family", fam),
        tech_node=("tech_node", node),
        gross_die=die,
        uom=("uom", "WFR"),
    )
add(
    "product",
    code="MON-PARTICLE",
    name="Particle monitor wafer (DEMO)",
    product_type="monitor",
    gross_die=0,
    uom=("uom", "WFR"),
)
for c, n, cat in _rows(
    [
        ("RAW-WFR", "Raw silicon wafers", "wafer"),
        ("CHEM", "Wet chemicals", "chemical"),
        ("GAS", "Process gases", "gas"),
        ("PR", "Photoresists", "photoresist"),
        ("SLURRY", "CMP slurries", "slurry"),
    ]
):
    add("material_type", code=c, name=n, category=cat)
for c, n, mt, u, life in _rows(
    [
        ("SI300-P", "300mm prime Si wafer", "RAW-WFR", "WFR", None),
        ("H2SO4-96", "Sulfuric acid 96%", "CHEM", "L", 365),
        ("NF3", "Nitrogen trifluoride", "GAS", "KG", None),
        ("PR-ARF-01", "ArF photoresist", "PR", "L", 180),
        ("SL-CU-01", "Cu CMP slurry", "SLURRY", "L", 120),
    ]
):
    add(
        "material",
        code=c,
        name=n,
        material_type=("material_type", mt),
        uom=("uom", u),
        shelf_life_days=life,
    )
add(
    "carrier_type",
    code="FOUP25",
    name="FOUP 25-slot 300mm",
    category="foup",
    capacity=25,
    wafer_size="300",
    clean_interval_days=30,
)
add(
    "carrier_type",
    code="FOSB25",
    name="FOSB shipping box",
    category="fosb",
    capacity=25,
    wafer_size="300",
)
add(
    "carrier_type",
    code="RPOD",
    name="Reticle SMIF pod",
    category="pod",
    capacity=1,
    wafer_size="300",
)
for i in range(1, 7):
    add(
        "carrier",
        code=f"FP{i:04d}",
        name=f"FOUP {i} (DEMO)",
        carrier_type=("carrier_type", "FOUP25"),
        max_uses=500,
        status_code="dirty" if i == 5 else "available",
    )
for c, layer, g in _rows(
    [
        ("RT-A100-AA", "AA", "binary"),
        ("RT-A100-PO", "PO", "psm"),
        ("RT-A100-M1", "M1", "psm"),
    ]
):
    add(
        "reticle",
        code=c,
        name=f"MCU-A100 {layer} mask (DEMO)",
        product=("product", "MCU-A100"),
        layer=layer,
        grade=g,
        max_shots=250000,
    )
add(
    "fixture",
    code="PC-A100-01",
    name="Probe card A100 #1",
    kind="probe_card",
    max_uses=1_000_000,
)
for c, n, cat, v, mdl in _rows(
    [
        ("SCANNER", "ArF immersion scanner", "process", "ASML", "NXT:1980Di"),
        ("TRACK", "Coater/developer", "process", "TEL", "Lithius Pro"),
        ("DRYETCH", "Conductor etcher", "process", "LAM", "Kiyo"),
        ("FURNACE", "Vertical furnace", "process", "KOKUSAI", "AdvancedAce"),
        ("CVD", "PECVD", "process", "AMAT", "Producer"),
        ("CMP", "CMP polisher", "process", "AMAT", "Reflexion LK"),
        ("CDSEM", "CD-SEM", "metrology", "Hitachi", "CG6300"),
        ("OVL", "Overlay metrology", "metrology", "KLA", "Archer 750"),
    ]
):
    add("equipment_type", code=c, name=n, category=cat, vendor=v, model=mdl)
