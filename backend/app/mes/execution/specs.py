"""执行实体规格：检查规则 / 方案 / 绑定 / 日志、单元谱系、晶圆图、NCR。"""

from app.core.spec.engine import ENUMS, FIELD_LABELS, Entity, F, register

TRIGGERS = [
    ("move_in", "Move in"),
    ("track_in", "Track in"),
    ("track_out", "Track out"),
    ("move_out", "Move out"),
    ("split", "Split"),
    ("merge", "Merge"),
    ("jump", "Jump step"),
    ("adjust", "Scrap / bonus"),
    ("sort", "Wafer sort"),
    ("priority", "Priority change"),
    ("convert", "Unit conversion"),
]
# built-in check types (app.mes.checks implements them; plugins may add more)
CHECK_TYPES = [
    (
        "e10_available",
        "Equipment E10 state available",
    ),
    (
        "eqp_capability",
        "Equipment capability / recipe match",
    ),
    ("recipe_active", "Recipe active"),
    ("reticle_available", "Reticle available"),
    ("material_sufficient", "Material sufficient"),
    ("bom_over", "BOM consumption within limit"),
    ("tool_life", "Tool available + life"),
    ("carrier_available", "Carrier available"),
    ("batch_same_step", "Batch: same step"),
    ("sort_order", "Sort keeps wafer order"),
    ("hot_lot_limit", "Hot lot WIP limit"),
    (
        "handover_ack_other",
        "Handover confirmed by another user",
    ),
    ("operator_qualified", "Operator qualified"),
    (
        "qual_expiry_notice",
        "Qualification expiry notice",
    ),
    ("future_hold", "Future hold at step"),
    ("wo_due", "Work order due notice"),
    ("carrier_clean", "Carrier cleaning due"),
    ("carrier_usage", "Carrier usage limit"),
    ("chamber_required", "Chamber selected"),
    (
        "chamber_available",
        "Chamber E10 state available",
    ),
    ("qtime", "Q-Time"),
    ("lot_hold", "Lot not on hold"),
    ("wo_status", "Work order status"),
    ("dc_complete", "DC completeness"),
    ("oos", "Out of spec"),
    ("ooc", "Out of control (SPC)"),
    ("sampling", "Sampling decision"),
    ("split_merge_rule", "Split / merge rule"),
    ("recipe_match", "Recipe ↔ equipment mapping"),
    ("pm_due", "Equipment PM not overdue"),
    ("rework_limit", "Rework count limit"),
    (
        "qty_adjust_limit",
        "Scrap / bonus qty limit",
    ),
]
ENUMS.update(
    {
        "exec_trigger": TRIGGERS,
        "check_type": list(CHECK_TYPES),
        "check_severity": [
            ("block", "Block"),
            ("warn", "Warn"),
            ("off", "Off (control disabled)"),
        ],
        "check_result": [
            ("pass", "Pass"),
            ("warn", "Warn"),
            ("block", "Block"),
            ("overridden", "Overridden"),
        ],
        "check_scope": [
            ("route_step", "Route step"),
            ("equipment", "Equipment"),
            ("operation", "Operation"),
            ("equipment_type", "Equipment type"),
            ("product", "Product"),
        ],
        "ml_status": [
            ("available", "Available"),
            ("hold", "On hold"),
            ("empty", "Used up"),
            ("expired", "Expired"),
            ("rejected", "Rejected (IQC)"),
        ],
        "tool_status": [
            ("available", "Available"),
            ("in_use", "In use"),
            ("pending_maintenance", "Pending maintenance"),
            ("expired", "Expired"),
            ("retired", "Retired"),
        ],
        "e10_trigger": [
            ("track_in", "Track in"),
            (
                "track_out",
                "Track out (no other running lots)",
            ),
        ],
        "hold_type": [
            ("manual", "Manual"),
            ("auto", "Automatic"),
            ("future", "Future hold"),
        ],
        "shift_log_status": [
            ("open", "Awaiting handover"),
            ("acknowledged", "Acknowledged"),
        ],
        "fh_status": [
            ("active", "Waiting"),
            ("triggered", "Triggered"),
            ("cancelled", "Cancelled"),
        ],
        "history_action": [
            ("start", "Lot start"),
            ("move_in", "Move in"),
            ("track_in", "Track in"),
            ("track_out", "Track out"),
            ("move_out", "Move out"),
            ("hold", "Hold"),
            ("release", "Release"),
            ("scrap", "Scrap"),
            ("rework", "Rework"),
            ("branch", "Branch"),
            ("sub_route", "Enter sub-route"),
            (
                "return",
                "Return from sub/rework route",
            ),
            ("complete", "Finished (to receive)"),
            ("receive", "Received"),
            ("ship", "Shipped"),
            ("override", "Check override"),
            ("qtime", "Q-Time violation"),
            ("oos", "Out of spec"),
            ("split", "Split"),
            ("merge", "Merge"),
            ("jump", "Jump step"),
            ("bonus", "Bonus"),
            ("carrier_change", "Carrier change"),
            ("sort", "Wafer sort"),
            ("priority", "Priority change"),
            ("convert", "Unit conversion"),
            ("die_map", "Die map import"),
            ("bank_in", "Bank in"),
            ("bank_out", "Bank issue"),
            ("ooc", "Out of control"),
            ("ncr", "NCR disposition"),
        ],
        "genealogy_relation": [
            ("split", "Split"),
            ("merge", "Merge"),
            ("bank_issue", "Bank issue"),
        ],
        "unit_relation": [
            ("convert", "Convert (1 → N)"),
            ("assemble", "Assemble (N → 1)"),
        ],
        "die_map_kind": [
            ("cp", "Chip probing (CP)"),
            ("aoi", "Inspection (AOI)"),
            ("ink", "Ink / merged map"),
        ],
        "ncr_status": [
            ("open", "Open"),
            ("reviewing", "Under review"),
            ("closed", "Closed"),
            ("cancelled", "Cancelled"),
        ],
        "ncr_disposition": [
            ("release", "Release"),
            ("use_as_is", "Use as is (concession)"),
            ("rework", "Rework"),
            ("scrap", "Scrap"),
            ("downgrade", "Downgrade"),
            ("rtv", "Return to vendor"),
        ],
        "ncr_decision": [
            ("approve", "Approve"),
            ("reject", "Reject"),
        ],
    }
)


def _scope_ref(name: str, ref: str) -> F:
    return F(
        name,
        "ref",
        ref=ref,
        required_when={"scope": (name,)},
        only_when_required=True,
    )


FIELD_LABELS.setdefault("route_step", "Route step")

register(
    # ---------------- checks ----------------
    Entity(
        "check_rule",
        "check",
        "Check rule",
        [
            F(
                "check_type",
                "enum",
                "Check type",
                required=True,
                enum="check_type",
            ),
            F(
                "severity",
                "enum",
                "Severity",
                required=True,
                enum="check_severity",
                default="block",
            ),
            F(
                "params",
                "json",
                "Parameters (JSON)",
                list=False,
                help='e.g. {"allowed": ["SBY", "PRD"]} for E10; {"days": 7} for warn ahead',
            ),
            F("is_active", "bool", default=True),
        ],
        phase=6,
        icon="ShieldAlert",
        order=0,
    ),
)


register(
    Entity(
        "check_plan",
        "check",
        "Check plan",
        [F("is_active", "bool", default=True)],
        phase=6,
        icon="ListChecks",
        order=1,
        children=["check_plan_item"],
    ),
)


register(
    Entity(
        "check_plan_item",
        "check",
        "Plan rule",
        [
            F(
                "check_plan",
                "ref",
                "Check plan",
                required=True,
                ref="check_plan",
                cascade=True,
            ),
            F(
                "check_rule",
                "ref",
                "Check rule",
                required=True,
                ref="check_rule",
            ),
            F("seq", "int", "Seq.", default=10),
        ],
        phase=6,
        has_code=False,
        parent="check_plan",
        unique=[("check_plan", "check_rule")],
        icon="List",
        order=2,
        sort_default="seq",
        label_field="seq",
    ),
)


register(
    Entity(
        "check_binding",
        "check",
        "Check binding",
        [
            F(
                "check_plan",
                "ref",
                "Check plan",
                required=True,
                ref="check_plan",
            ),
            F(
                "trigger",
                "enum",
                "Trigger",
                required=True,
                enum="exec_trigger",
            ),
            F(
                "scope",
                "enum",
                "Scope",
                required=True,
                enum="check_scope",
            ),
            _scope_ref("route_step", "route_step"),
            _scope_ref("equipment", "equipment"),
            _scope_ref("operation", "operation"),
            _scope_ref("equipment_type", "equipment_type"),
            _scope_ref("product", "product"),
            F("is_active", "bool", default=True),
        ],
        phase=6,
        has_code=False,
        unique=[
            (
                "check_plan",
                "trigger",
                "scope",
                "route_step",
                "equipment",
                "operation",
                "equipment_type",
                "product",
            )
        ],
        icon="Link",
        order=3,
        sort_default="trigger",
        label_field="trigger",
    ),
)


register(
    Entity(
        "check_log",
        "check",
        "Check log",
        [
            F("lot", "ref", "Lot", ref="lot", cascade=True),
            F("trigger", "enum", "Trigger", enum="exec_trigger"),
            F("route_step", "ref", ref="route_step", list=False, filter=False),
            F("equipment", "ref", ref="equipment"),
            F(
                "check_rule",
                "ref",
                "Check rule",
                ref="check_rule",
            ),
            F(
                "check_plan",
                "ref",
                "Check plan",
                ref="check_plan",
                list=False,
            ),
            F(
                "check_type",
                "enum",
                "Check type",
                enum="check_type",
            ),
            F(
                "severity",
                "enum",
                "Severity",
                enum="check_severity",
                list=False,
            ),
            F("result", "enum", "Result", enum="check_result"),
            F("message", "str", "Message", max_length=500, search=True),
            F("context", "json", "Context", list=False),
            F(
                "override_reason",
                "str",
                "Override reason",
                max_length=300,
                list=False,
            ),
            F("username", "str", "User", max_length=255, search=True),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        icon="ScrollText",
        order=4,
        sort_default="created_at",
        label_field="check_type",
    ),
)


register(
    Entity(
        "future_hold",
        "exec",
        "Future hold",
        [
            F("lot", "ref", "Lot", required=True, ref="lot", cascade=True),
            F(
                "route_step",
                "ref",
                "Hold at step",
                required=True,
                ref="route_step",
            ),
            F(
                "reason",
                "ref",
                "Reason code",
                ref="reason_code",
                help="Blank: default hold reason",
            ),
            F("comment", "str", "Comment", max_length=300, search=True),
            F(
                "fh_status",
                "enum",
                "Status",
                enum="fh_status",
                system=True,
                default="active",
            ),
            F(
                "triggered_at",
                "datetime",
                "Triggered at",
                system=True,
            ),
        ],
        phase=6,
        has_code=False,
        icon="CalendarX",
        order=3,
        sort_default="created_at",
        label_field="comment",
    ),
)


register(
    Entity(
        "shift_log",
        "exec",
        "Shift handover",
        [
            F("shift_date", "date", "Date", required=True),
            F("shift", "ref", "Shift", ref="shift", required=True),
            F("area", "ref", ref="area"),
            F("summary", "text", "Handover notes", search=True),
            F("open_items", "text", "Open items", search=True),
            F("handed_by", "str", "Handed over by"),
            F("handed_at", "datetime", "Handed over at"),
            F(
                "log_status",
                "enum",
                "Status",
                enum="shift_log_status",
                default="open",
            ),
            F("received_by", "str", "Received by"),
            F("received_at", "datetime", "Received at"),
            F(
                "receive_comment",
                "str",
                "Receiver note",
                max_length=300,
            ),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        menu=False,
        icon="NotebookPen",
        sort_default="shift_date",
        label_field="shift_date",
    ),
)


register(
    Entity(
        "operator_qual",
        "exec",
        "Operator qualification",
        [
            F("username", "str", "User", required=True, search=True),
            F("operation", "ref", ref="operation", required=True),
            F(
                "equipment_type",
                "ref",
                "Equipment type",
                ref="equipment_type",
                help="Blank: any equipment type",
            ),
            F("certified_on", "date", "Certified on"),
            F("expires_on", "date", "Expires on"),
            F("is_active", "bool", default=True),
        ],
        phase=6,
        has_code=False,
        icon="Award",
        sort_default="expires_on",
        label_field="username",
        unique=[("username", "operation", "equipment_type")],
    ),
)


register(
    # 单元级谱系：晶圆 → 芯片 → 条带 → 单颗的逐级转换（批次级谱系见 lot_genealogy）
    Entity(
        "unit_genealogy",
        "exec",
        "Unit genealogy",
        [
            F(
                "parent_unit",
                "ref",
                "Source unit",
                required=True,
                ref="wafer",
                cascade=True,
            ),
            F(
                "child_unit",
                "ref",
                "Output unit",
                required=True,
                ref="wafer",
                cascade=True,
            ),
            F("lot", "ref", "Lot", required=True, ref="lot", cascade=True),
            F("relation", "enum", "Relation", enum="unit_relation"),
            F("qty", "int", "Qty"),
            # 取自晶圆图的芯片坐标 [[x, y], ...]
            F("dies", "json", "Die coordinates", list=False),
            F("route_step", "ref", ref="route_step", list=False, filter=False),
            F("username", "str", "User", max_length=255, search=True),
            F("at", "datetime", "Time"),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        icon="GitFork",
        order=5,
        menu=False,
        sort_default="at",
        label_field="relation",
    ),
)


register(
    Entity(
        "die_map",
        "exec",
        "Die map",
        [
            F("unit", "ref", "Wafer", required=True, ref="wafer", cascade=True),
            F("lot", "ref", "Lot", required=True, ref="lot", cascade=True),
            F("route_step", "ref", ref="route_step", list=False, filter=False),
            F(
                "test_kind",
                "enum",
                "Map kind",
                enum="die_map_kind",
                required=True,
                default="cp",
            ),
            F("rows", "int", "Rows", list=False),
            F("cols", "int", "Columns", list=False),
            # [[x, y, bin], ...]
            F("dies", "json", "Dies", list=False),
            F("gross", "int", "Gross die"),
            F("good", "int", "Good die"),
            F("yield_pct", "float", "Yield %"),
            # 同一晶圆同一类型只有最新一张生效（重测覆盖）
            F("is_current", "bool", "Current", default=True),
            F("source", "str", "Source file", max_length=200, search=True),
            F("username", "str", "User", max_length=255, search=True, list=False),
            F("at", "datetime", "Time"),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        icon="Grid3x3",
        order=6,
        sort_default="at",
        label_field="at",
    ),
)


register(
    Entity(
        "ncr",
        "ncr",
        "NCR / MRB",
        [
            F("lot", "ref", "Lot", required=True, ref="lot", cascade=True),
            F("title", "str", "Title", required=True, max_length=200, search=True),
            F(
                "severity",
                "enum",
                "Severity",
                enum="severity",
                required=True,
                default="major",
            ),
            F("defect_code", "ref", "Defect code", ref="defect_code"),
            F("qty", "int", "Affected qty"),
            F("units", "json", "Affected units", list=False),
            F("hold", "ref", "Hold", ref="lot_hold", list=False, filter=False),
            F(
                "ncr_status",
                "enum",
                "Status",
                enum="ncr_status",
                default="open",
            ),
            F("disposition", "enum", "Disposition", enum="ncr_disposition"),
            F(
                "disposition_comment",
                "str",
                "Disposition note",
                max_length=300,
                list=False,
            ),
            F(
                "scrap_reason",
                "ref",
                "Scrap reason",
                ref="reason_code",
                list=False,
                filter=False,
            ),
            # 审批级数按严重度：minor 1 / major 2 / critical 3
            F("required_levels", "int", "Approval levels", list=False),
            F("approved_levels", "int", "Approved levels", default=0),
            F("raised_by", "str", "Raised by", max_length=255),
            F("raised_at", "datetime", "Raised at"),
            F("proposed_by", "str", "Proposed by", max_length=255, list=False),
            F("proposed_at", "datetime", "Proposed at", list=False),
            F("closed_by", "str", "Closed by", max_length=255, list=False),
            F("closed_at", "datetime", "Closed at", list=False),
            F("result", "json", "Execution result", list=False),
        ],
        phase=6,
        has_name=False,
        code_label="NCR no.",
        readonly=True,
        icon="FileWarning",
        children=["ncr_approval"],
        sort_default="raised_at",
    ),
)


register(
    Entity(
        "ncr_approval",
        "ncr",
        "NCR approval",
        [
            F("ncr", "ref", "NCR", required=True, ref="ncr", cascade=True),
            F("level", "int", "Level"),
            F("decision", "enum", "Decision", enum="ncr_decision"),
            F("comment", "str", "Comment", max_length=300),
            F("username", "str", "User", max_length=255),
            F("at", "datetime", "Time"),
        ],
        phase=6,
        has_code=False,
        parent="ncr",
        readonly=True,
        icon="Stamp",
        order=1,
        sort_default="at",
        label_field="decision",
    ),
)
