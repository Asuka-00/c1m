"""产品与物料实体规格（单位、产品、物料、载具、光罩、治具、线边批次）。"""

from app.core.spec.engine import ENTITIES, ENUMS, Entity, F, register

ENUMS.update(
    {
        "uom_dimension": [
            ("count", "Count"),
            ("length", "Length"),
            ("area", "Area"),
            ("volume", "Volume"),
            ("mass", "Mass"),
            ("time", "Time"),
            ("pressure", "Pressure"),
            ("temperature", "Temperature"),
            ("energy_density", "Energy density"),
        ],
        "wafer_size": [
            ("100", '100 mm (4")'),
            ("150", '150 mm (6")'),
            ("200", '200 mm (8")'),
            ("300", '300 mm (12")'),
        ],
        "product_type": [
            ("production", "Production"),
            ("engineering", "Engineering"),
            ("monitor", "Monitor"),
            ("dummy", "Dummy"),
        ],
        "material_category": [
            ("wafer", "Raw wafer"),
            ("chemical", "Chemical"),
            ("gas", "Gas"),
            ("target", "Sputter target"),
            ("slurry", "Slurry"),
            ("photoresist", "Photoresist"),
            ("consumable", "Consumable"),
        ],
        "carrier_category": [
            ("foup", "FOUP"),
            ("fosb", "FOSB"),
            ("cassette", "Cassette"),
            ("pod", "Reticle pod"),
            ("smif", "SMIF pod"),
        ],
        "carrier_event_type": [
            ("load", "Load"),
            ("unload", "Unload"),
            ("clean", "Clean"),
            ("sort", "Wafer sort"),
            ("split", "Split"),
            ("merge", "Merge"),
        ],
        "asset_status": [
            ("available", "Available"),
            ("in_use", "In use"),
            ("dirty", "Needs cleaning"),
            ("hold", "On hold"),
            ("retired", "Retired"),
        ],
        "reticle_grade": [
            ("binary", "Binary"),
            ("psm", "Phase shift (PSM)"),
            ("euv", "EUV"),
        ],
        "fixture_kind": [
            ("probe_card", "Probe card"),
            ("fixture", "Fixture"),
            ("jig", "Jig"),
            ("tool", "Tool"),
        ],
        "eqp_category": [
            ("process", "Process"),
            ("metrology", "Metrology"),
            ("inspection", "Inspection"),
            ("test", "Test"),
            ("transport", "Transport (AMHS)"),
        ],
        "unit_kind": [
            ("main", "Main equipment"),
            ("chamber", "Chamber"),
            ("load_port", "Load port"),
            ("port", "Port"),
            ("sub_unit", "Sub-unit"),
        ],
        "tracking_level": [
            ("wafer", "Wafer (slots)"),
            ("unit", "Serialized unit"),
            ("quantity", "Quantity"),
        ],
        "serial_kind": [
            ("strip", "Strip"),
            ("die", "Die"),
            ("package", "Package"),
            ("unit", "Unit"),
        ],
        "e10_category": [
            ("PRD", "PRD · Productive"),
            ("SBY", "SBY · Standby"),
            ("ENG", "ENG · Engineering"),
            ("SDT", "SDT · Scheduled down"),
            ("UDT", "UDT · Unscheduled down"),
            ("NST", "NST · Non-scheduled"),
        ],
    }
)

register(
    # ---------------- product & material ----------------
    Entity(
        "uom",
        "product",
        "Unit of measure",
        [
            F("symbol", "str", "Symbol", max_length=20, search=True),
            F(
                "dimension",
                "enum",
                "Dimension",
                required=True,
                enum="uom_dimension",
            ),
        ],
        phase=2,
        icon="Ruler",
        children=["uom_conversion"],
    ),
)


register(
    Entity(
        "uom_conversion",
        "product",
        "UOM conversion",
        [
            F(
                "from_uom",
                "ref",
                "From",
                required=True,
                ref="uom",
                cascade=True,
            ),
            F("to_uom", "ref", "To", required=True, ref="uom"),
            F(
                "factor",
                "float",
                "Factor",
                required=True,
                help="to = from × factor",
            ),
            F("offset", "float", "Offset", default=0, list=False),
        ],
        phase=2,
        has_code=False,
        parent="uom",
        unique=[("from_uom", "to_uom")],
        icon="ArrowLeftRight",
        order=1,
        sort_default="factor",
        label_field="factor",
    ),
)


register(
    Entity(
        "tech_node",
        "product",
        "Technology node",
        [
            F("feature_nm", "float", "Feature size (nm)"),
            F("wafer_size", "enum", enum="wafer_size", default="300"),
            F(
                "tracking_level",
                "enum",
                "Tracking level",
                required=True,
                enum="tracking_level",
                default="wafer",
            ),
        ],
        phase=2,
        icon="Atom",
        order=2,
    ),
)


register(
    Entity(
        "product_family",
        "product",
        "Product family",
        [
            F(
                "tech_node",
                "ref",
                "Technology node",
                ref="tech_node",
                required=True,
            )
        ],
        phase=2,
        icon="Boxes",
        order=3,
    ),
)


register(
    Entity(
        "product",
        "product",
        "Product",
        [
            F(
                "family",
                "ref",
                "Family",
                ref="product_family",
                required_when={"product_type": ("production", "engineering")},
            ),
            F(
                "tech_node",
                "ref",
                "Technology node",
                ref="tech_node",
                required_when={"product_type": ("production", "engineering")},
            ),
            F(
                "product_type",
                "enum",
                "Type",
                enum="product_type",
                default="production",
            ),
            F("wafer_size", "enum", enum="wafer_size", default="300"),
            F(
                "gross_die",
                "int",
                "Gross die / wafer",
            ),
            F("uom", "ref", ref="uom", list=False, required=True),
            F(
                "tracking_level",
                "enum",
                "Tracking level",
                enum="tracking_level",
                list=False,
                help="Blank: inherit from the technology node",
            ),
            F(
                "serial_kind",
                "enum",
                "Serialized unit kind",
                enum="serial_kind",
                list=False,
                required_when={"tracking_level": ("unit",)},
            ),
            F(
                "unit_code_rule",
                "ref",
                "Unit serial rule",
                ref="code_rule",
                list=False,
                required_when={"tracking_level": ("unit",)},
            ),
        ],
        phase=2,
        versioned=True,
        icon="Package",
        order=4,
    ),
)


register(
    Entity(
        "material_type",
        "product",
        "Material type",
        [F("category", "enum", required=True, enum="material_category")],
        phase=2,
        icon="FlaskConical",
        order=5,
    ),
)


register(
    Entity(
        "material",
        "product",
        "Material",
        [
            F(
                "material_type",
                "ref",
                "Material type",
                required=True,
                ref="material_type",
            ),
            F("uom", "ref", required=True, ref="uom"),
            F("vendor", "str", max_length=100, search=True),
            F(
                "shelf_life_days",
                "int",
                "Shelf life (days)",
            ),
            F(
                "storage",
                "str",
                "Storage condition",
                max_length=200,
                list=False,
            ),
            F("is_active", "bool", default=True),
        ],
        phase=2,
        icon="Beaker",
        order=6,
    ),
)


register(
    Entity(
        "carrier_type",
        "product",
        "Carrier type",
        [
            F("category", "enum", required=True, enum="carrier_category"),
            F(
                "capacity",
                "int",
                "Capacity (slots)",
                required=True,
            ),
            F("wafer_size", "enum", enum="wafer_size", default="300"),
            F(
                "clean_interval_days",
                "int",
                "Clean interval (days)",
                list=False,
            ),
        ],
        phase=2,
        icon="Container",
        order=7,
    ),
)


register(
    Entity(
        "carrier",
        "product",
        "Carrier",
        [
            F(
                "carrier_type",
                "ref",
                "Carrier type",
                required=True,
                ref="carrier_type",
            ),
            F("status_code", "enum", enum="asset_status", default="available"),
            F("max_uses", "int", "Max uses"),
            F(
                "use_count",
                "int",
                "Uses since clean",
                system=True,
            ),
            F(
                "last_cleaned_at",
                "datetime",
                "Last cleaned",
                system=True,
            ),
            F(
                "rfid",
                "str",
                "RFID tag",
                max_length=64,
                search=True,
                list=False,
            ),
        ],
        phase=2,
        icon="Archive",
        order=8,
    ),
)


register(
    Entity(
        "carrier_event",
        "product",
        "Carrier event",
        [
            F(
                "carrier",
                "ref",
                "Carrier",
                required=True,
                ref="carrier",
                cascade=True,
            ),
            F("event", "enum", "Event", enum="carrier_event_type"),
            F("lot", "ref", "Lot", ref="lot"),
            F(
                "other_carrier",
                "ref",
                "From / to carrier",
                ref="carrier",
            ),
            F("qty", "int", "Qty"),
            F("comment", "str", "Comment", max_length=300, search=True),
            F("username", "str", "User", max_length=255, search=True),
            F("at", "datetime", "Time"),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        icon="History",
        order=10,
        menu=False,
        sort_default="at",
        label_field="event",
    ),
)


register(
    Entity(
        "reticle",
        "product",
        "Reticle",
        [
            F("product", "ref", ref="product", required=True),
            F(
                "layer",
                "str",
                "Layer",
                max_length=40,
                search=True,
                required=True,
            ),
            F(
                "grade",
                "enum",
                "Grade",
                enum="reticle_grade",
                default="binary",
            ),
            F("max_shots", "int", "Max shots"),
            F("status_code", "enum", enum="asset_status", default="available"),
        ],
        phase=2,
        icon="Aperture",
        order=9,
    ),
)


register(
    Entity(
        "fixture",
        "product",
        "Fixture / tool",
        [
            F("kind", "enum", "Kind", required=True, enum="fixture_kind"),
            F("max_uses", "int", "Max uses"),
            F("status_code", "enum", enum="asset_status", default="available"),
        ],
        phase=2,
        icon="Hammer",
        order=10,
    ),
)


register(
    # ---------------- line-side material & tools ----------------
    Entity(
        "material_lot",
        "inventory",
        "Material lot",
        [
            F("material", "ref", "Material", required=True, ref="material"),
            F("qty_remaining", "float", "Qty remaining", required=True),
            F("initial_qty", "float", "Received qty", list=False),
            F("uom", "ref", ref="uom", required=True),
            F("supplier_lot", "str", "Supplier lot", max_length=100, list=False),
            F(
                "work_order",
                "ref",
                "Issued to work order",
                ref="work_order",
                system=True,
                help="Set by a material issue; only that work order consumes this lot",
            ),
            F("expiry_date", "date", "Expiry"),
            F(
                "location",
                "str",
                "Location",
                max_length=100,
                search=True,
            ),
            F(
                "ml_status",
                "enum",
                "Status",
                enum="ml_status",
                required=True,
                default="available",
            ),
        ],
        phase=6,
        has_name=False,
        code_label="Material lot no.",
        icon="PackageOpen",
        order=0,
    ),
)

ENTITIES["carrier"].children.append("carrier_event")
