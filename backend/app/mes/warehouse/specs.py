"""仓储实体规格：仓库、库位、完工入库单及其明细。"""

from app.core.spec.engine import ENUMS, Entity, F, register

ENUMS.update(
    {
        "warehouse_type": [
            ("finished_goods", "Finished goods"),
            ("semi_finished", "Semi-finished"),
            ("raw_material", "Raw material"),
            ("quarantine", "Quarantine"),
            ("scrap", "Scrap"),
        ],
        "location_type": [
            ("rack", "Rack"),
            ("shelf", "Shelf"),
            ("bin", "Bin"),
            (
                "dry_cabinet",
                "Dry cabinet / N2 cabinet",
            ),
            ("floor", "Floor area"),
        ],
        "receipt_status": [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("confirmed", "Confirmed"),
            ("cancelled", "Cancelled"),
        ],
    }
)


register(
    Entity(
        "warehouse",
        "wh",
        "Warehouse",
        [
            F("site", "ref", required=True, ref="site"),
            F(
                "warehouse_type",
                "enum",
                "Warehouse type",
                enum="warehouse_type",
                default="finished_goods",
                required=True,
            ),
            F("address", "str", "Address", max_length=300, list=False),
            F("keeper", "str", "Keeper", search=True),
            F("is_active", "bool", default=True),
        ],
        phase=7,
        icon="Warehouse",
        order=1,
    ),
)


register(
    Entity(
        "storage_location",
        "wh",
        "Storage location",
        [
            F(
                "warehouse",
                "ref",
                "Warehouse",
                required=True,
                ref="warehouse",
            ),
            F(
                "location_type",
                "enum",
                "Location type",
                enum="location_type",
                default="rack",
                required=True,
            ),
            F(
                "capacity",
                "int",
                "Capacity (lots)",
                help="Blank: unlimited",
            ),
            F("is_active", "bool", default=True),
        ],
        phase=7,
        icon="MapPin",
        order=2,
    ),
)


register(
    Entity(
        "receipt",
        "wh",
        "Finished-goods receipt",
        [
            F(
                "warehouse",
                "ref",
                "Warehouse",
                required=True,
                ref="warehouse",
            ),
            F(
                "location",
                "ref",
                "Storage location",
                ref="storage_location",
                depends="warehouse",
            ),
            F(
                "receipt_status",
                "enum",
                "Status",
                enum="receipt_status",
                system=True,
                default="draft",
            ),
            F("lot_count", "int", "Lots", system=True, default=0),
            F("total_good", "int", "Good qty", system=True, default=0),
            F("total_scrap", "int", "Scrap qty", system=True, default=0),
            F("remarks", "text", "Remarks", list=False),
            F(
                "submitted_at",
                "datetime",
                "Submitted at",
                system=True,
                list=False,
            ),
            F(
                "submitted_by",
                "str",
                "Submitted by",
                system=True,
                list=False,
            ),
            F(
                "confirmed_at",
                "datetime",
                "Confirmed at",
                system=True,
            ),
            F(
                "confirmed_by",
                "str",
                "Confirmed by",
                system=True,
                list=False,
            ),
        ],
        phase=7,
        icon="PackageCheck",
        order=0,
        has_name=False,
        code_label="Receipt no.",
        code_auto=True,
        sort_default="created_at",
        children=["receipt_line"],
    ),
)


register(
    Entity(
        "receipt_line",
        "wh",
        "Receipt line",
        [
            F(
                "receipt",
                "ref",
                "Receipt",
                required=True,
                ref="receipt",
                cascade=True,
            ),
            F(
                "lot",
                "ref",
                "Lot",
                required=True,
                ref="lot",
                ref_filter={"lot_status": "completed"},
                help="Only finished lots awaiting receipt",
            ),
            F(
                "work_order",
                "ref",
                "Work order",
                ref="work_order",
                system=True,
            ),
            F("product", "ref", ref="product", system=True),
            F("good_qty", "int", "Good qty", required=True),
            F("scrap_qty", "int", "Scrap qty", default=0),
            F("remarks", "str", "Remarks", max_length=300, list=False),
        ],
        phase=7,
        has_code=False,
        parent="receipt",
        unique=[("receipt", "lot")],
        icon="List",
        order=3,
        sort_default="created_at",
        label_field="good_qty",
    ),
)
