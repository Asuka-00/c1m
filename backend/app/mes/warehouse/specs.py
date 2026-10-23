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
        "iqc_result": [
            ("pending", "Pending"),
            ("pass", "Passed"),
            ("fail", "Failed"),
        ],
        # 领料单 / 出货单 / 来料接收单共用：草稿 → 已确认 / 已取消
        "issue_status": [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("cancelled", "Cancelled"),
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


register(
    Entity(
        "material_issue",
        "wh",
        "Material issue",
        [
            F(
                "work_order",
                "ref",
                "Work order",
                required=True,
                ref="work_order",
            ),
            F(
                "issue_status",
                "enum",
                "Status",
                enum="issue_status",
                system=True,
                default="draft",
            ),
            F("remarks", "text", "Remarks", list=False),
            F("confirmed_at", "datetime", "Confirmed at", system=True),
            F("confirmed_by", "str", "Confirmed by", system=True, list=False),
        ],
        phase=7,
        icon="PackageMinus",
        order=4,
        has_name=False,
        code_label="Issue no.",
        sort_default="created_at",
        children=["material_issue_line"],
    ),
)


register(
    Entity(
        "material_issue_line",
        "wh",
        "Material issue line",
        [
            F(
                "material_issue",
                "ref",
                "Material issue",
                required=True,
                ref="material_issue",
                cascade=True,
            ),
            F(
                "material_lot",
                "ref",
                "Source material lot",
                required=True,
                ref="material_lot",
                ref_filter={"ml_status": "available"},
                help="Only available lots not yet issued to a work order",
            ),
            F("qty", "float", "Quantity", required=True),
        ],
        phase=7,
        has_code=False,
        parent="material_issue",
        unique=[("material_issue", "material_lot")],
        icon="List",
        order=5,
        sort_default="created_at",
        label_field="qty",
    ),
)


register(
    Entity(
        "shipment",
        "wh",
        "Shipment",
        [
            F(
                "customer",
                "str",
                "Customer",
                required=True,
                max_length=200,
                search=True,
            ),
            F(
                "warehouse",
                "ref",
                "Warehouse",
                ref="warehouse",
            ),
            F("waybill", "str", "Waybill no.", max_length=100, search=True),
            F(
                "issue_status",
                "enum",
                "Status",
                enum="issue_status",
                system=True,
                default="draft",
            ),
            F("remarks", "text", "Remarks", list=False),
            F("confirmed_at", "datetime", "Shipped at", system=True),
            F("confirmed_by", "str", "Confirmed by", system=True, list=False),
        ],
        phase=7,
        icon="Truck",
        order=6,
        has_name=False,
        code_label="Shipment no.",
        sort_default="created_at",
        children=["shipment_line"],
    ),
)


register(
    Entity(
        "shipment_line",
        "wh",
        "Shipment line",
        [
            F(
                "shipment",
                "ref",
                "Shipment",
                required=True,
                ref="shipment",
                cascade=True,
            ),
            F(
                "lot",
                "ref",
                "Lot",
                required=True,
                ref="lot",
                ref_filter={"lot_status": "stored"},
                help="Only stored lots can be shipped",
            ),
            F("product", "ref", ref="product", system=True),
            F("qty", "int", "Quantity", required=True),
        ],
        phase=7,
        has_code=False,
        parent="shipment",
        unique=[("shipment", "lot")],
        icon="List",
        order=7,
        sort_default="created_at",
        label_field="qty",
    ),
)


register(
    Entity(
        "material_receipt",
        "wh",
        "Material receipt",
        [
            F(
                "supplier",
                "str",
                "Supplier",
                required=True,
                max_length=200,
                search=True,
            ),
            F(
                "issue_status",
                "enum",
                "Status",
                enum="issue_status",
                system=True,
                default="draft",
            ),
            F("remarks", "text", "Remarks", list=False),
            F("confirmed_at", "datetime", "Received at", system=True),
            F("confirmed_by", "str", "Confirmed by", system=True, list=False),
        ],
        phase=7,
        icon="PackageSearch",
        order=8,
        has_name=False,
        code_label="Receipt no.",
        sort_default="created_at",
        children=["material_receipt_line"],
    ),
)


register(
    Entity(
        "material_receipt_line",
        "wh",
        "Material receipt line",
        [
            F(
                "material_receipt",
                "ref",
                "Material receipt",
                required=True,
                ref="material_receipt",
                cascade=True,
            ),
            F("material", "ref", "Material", required=True, ref="material"),
            F("qty", "float", "Quantity", required=True),
            F("uom", "ref", ref="uom", required=True),
            F("supplier_lot", "str", "Supplier lot", max_length=100, search=True),
            F(
                "expiry_date",
                "date",
                "Expiry",
                help="Blank: received date plus the material's shelf life",
            ),
            F("location", "str", "Location", max_length=100, list=False),
            F(
                "iqc_result",
                "enum",
                "IQC result",
                enum="iqc_result",
                system=True,
                default="pending",
            ),
            F(
                "material_lot",
                "ref",
                "Material lot",
                ref="material_lot",
                system=True,
            ),
        ],
        phase=7,
        has_code=False,
        parent="material_receipt",
        icon="List",
        order=9,
        sort_default="created_at",
        label_field="qty",
        label_ref="material",
    ),
)
