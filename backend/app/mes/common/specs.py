"""MES 公共实体规格：数据字典、编码规则、自定义属性。"""

from app.core.spec.engine import ENUMS, FIELD_LABELS, Entity, F, register

FIELD_LABELS.update(
    {
        "code": "Code",
        "name": "Name",
        "description": "Description",
        "parent": "Parent",
        "sort_order": "Sort order",
        "is_active": "Active",
        "color": "Color",
        "vendor": "Vendor",
        "model": "Model",
        "site": "Site",
        "area": "Area",
        "uom": "Unit",
        "product": "Product",
        "operation": "Operation",
        "equipment": "Equipment",
        "equipment_type": "Equipment type",
        "route": "Route",
        "recipe": "Recipe",
        "wafer_size": "Wafer size",
        "status_code": "State",
        "category": "Category",
        "target": "Target",
        "lsl": "LSL",
        "usl": "USL",
    }
)

ENUMS.update(
    {
        # versioned master data
        "status": [
            ("draft", "Draft"),
            ("active", "Active"),
            ("inactive", "Inactive"),
        ],
        "audit_action": [
            ("create", "Create"),
            ("update", "Update"),
            ("delete", "Delete"),
            ("status", "Status change"),
            ("import", "Import"),
            ("new_version", "New version"),
            ("release", "Release"),
            ("hold", "Hold"),
            ("resume", "Resume"),
            ("complete", "Complete"),
            ("submit", "Submit"),
            ("confirm", "Confirm"),
            ("reject", "Reject"),
            ("receive", "Receive"),
            ("ship", "Ship"),
            ("close", "Close"),
            ("cancel", "Cancel"),
            ("start", "Lot start"),
            ("undo_start", "Undo start"),
            ("move_in", "Move in"),
            ("track_in", "Track in"),
            ("track_out", "Track out"),
            ("move_out", "Move out"),
            ("override", "Check override"),
            ("split", "Split"),
            ("qtime_rework", "Q-Time rework"),
            ("merge", "Merge"),
            ("e10", "E10 state change"),
            ("convert", "Unit conversion"),
            ("bank_in", "Bank in"),
            ("bank_out", "Bank issue"),
            ("disposition", "NCR disposition"),
        ],
        "seq_reset": [
            ("never", "Never"),
            ("daily", "Daily"),
            ("monthly", "Monthly"),
            ("yearly", "Yearly"),
        ],
        "code_target": [
            ("lot", "Lot ID"),
            ("wafer", "Wafer ID"),
            ("carrier", "Carrier ID"),
            ("material", "Material lot"),
            ("equipment", "Equipment ID"),
            ("work_order", "Work order no."),
            ("receipt", "Receipt no."),
            ("unit", "Unit serial no."),
            ("other", "Other"),
        ],
        "attr_type": [
            ("string", "Text"),
            ("number", "Number"),
            ("boolean", "Yes/No"),
            ("date", "Date"),
            ("select", "Select"),
        ],
        "area_type": [
            ("fab", "Fab (front-end)"),
            ("cleanroom", "Clean room"),
            ("test", "Test / probe"),
            ("assembly", "Assembly"),
            ("warehouse", "Warehouse"),
            ("facility", "Facility"),
        ],
        "wc_kind": [
            ("bay", "Bay"),
            ("workcenter", "Work center"),
            ("cell", "Cell"),
        ],
        "day_type": [
            ("workday", "Workday"),
            ("holiday", "Holiday"),
            ("maintenance", "Maintenance"),
        ],
    }
)

ENTITY_TYPES: list[tuple[str, str]] = []  # filled by specs/__init__ (attr_def)
ENUMS["entity_type"] = ENTITY_TYPES

register(
    # ---------------- common ----------------
    Entity(
        "dict_type",
        "common",
        "Dictionary",
        [F("is_active", "bool", default=True)],
        phase=1,
        children=["dict_item"],
        icon="BookOpen",
    ),
)


register(
    Entity(
        "dict_item",
        "common",
        "Dictionary item",
        [
            F(
                "dict_type",
                "ref",
                "Dictionary",
                required=True,
                ref="dict_type",
                cascade=True,
            ),
            F(
                "value",
                "str",
                "Value",
                search=True,
                max_length=200,
                required=True,
                default_from="code",
            ),
            F("color", "str", max_length=20, list=False),
            F("sort_order", "int", default=0),
            F("is_active", "bool", default=True),
        ],
        phase=1,
        parent="dict_type",
        unique=[("dict_type", "code")],
        icon="List",
        order=1,
        sort_default="sort_order",
    ),
)


register(
    Entity(
        "code_rule",
        "common",
        "Code rule",
        [
            F(
                "target",
                "enum",
                "Applies to",
                required=True,
                enum="code_target",
            ),
            F(
                "pattern",
                "str",
                "Pattern",
                required=True,
                max_length=120,
                search=True,
                help="Tokens: {YYYY} {YY} {MM} {DD} {JJJ} {SEQ} {SEQ36} {LOT} {SLOT}",
            ),
            F("seq_width", "int", "Sequence width", default=4),
            F(
                "seq_start",
                "int",
                "Sequence start",
                default=1,
                list=False,
            ),
            F(
                "seq_reset",
                "enum",
                "Reset",
                enum="seq_reset",
                default="never",
            ),
        ],
        phase=1,
        icon="Hash",
        order=2,
    ),
)


register(
    Entity(
        "code_rule_counter",
        "common",
        "Code rule counter",
        [
            F(
                "code_rule",
                "ref",
                "Code rule",
                required=True,
                ref="code_rule",
                cascade=True,
            ),
            F("period", "str", "Period", max_length=20),
            F("value", "int", "Value", default=0),
        ],
        phase=1,
        has_code=False,
        unique=[("code_rule", "period")],
        internal=True,
        sort_default="period",
    ),
)


register(
    Entity(
        "attr_def",
        "common",
        "Custom attribute",
        [
            F(
                "entity_type",
                "enum",
                "Entity",
                required=True,
                enum="entity_type",
            ),
            F(
                "data_type",
                "enum",
                "Data type",
                required=True,
                enum="attr_type",
            ),
            F("required", "bool", "Required", default=False),
            F(
                "options",
                "str",
                "Options (comma separated)",
                max_length=500,
                list=False,
            ),
            F(
                "dict_type",
                "ref",
                "Options from dictionary",
                ref="dict_type",
                list=False,
            ),
            F("sort_order", "int", default=0),
        ],
        phase=1,
        unique=[("entity_type", "code")],
        icon="ListPlus",
        order=3,
    ),
)
