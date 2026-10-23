"""设备实体规格：类型、组、E10 状态/迁移/自动规则、能力、工具。"""

from app.core.spec.engine import ENUMS, Entity, F, register

register(
    # ---------------- equipment ----------------
    Entity(
        "equipment_type",
        "equipment",
        "Equipment type",
        [
            F("category", "enum", required=True, enum="eqp_category"),
            F("vendor", "str", search=True),
            F("model", "str", search=True),
        ],
        phase=2,
        icon="ServerCog",
    ),
)


register(
    Entity(
        "equipment_group",
        "equipment",
        "Equipment group",
        [
            F("equipment_type", "ref", ref="equipment_type", required=True),
            F("area", "ref", ref="area"),
        ],
        phase=2,
        icon="Boxes",
        order=1,
    ),
)


register(
    Entity(
        "e10_state",
        "equipment",
        "E10 state",
        [
            F(
                "e10_category",
                "enum",
                "E10 category",
                required=True,
                enum="e10_category",
            ),
            F("color", "str", max_length=20),
            F("is_initial", "bool", "Initial state", default=False),
            F("sort_order", "int", default=0),
        ],
        phase=2,
        icon="Activity",
        order=2,
        children=["e10_transition"],
        sort_default="sort_order",
    ),
)


register(
    Entity(
        "e10_transition",
        "equipment",
        "E10 transition",
        [
            F(
                "from_state",
                "ref",
                "From state",
                required=True,
                ref="e10_state",
                cascade=True,
            ),
            F(
                "to_state",
                "ref",
                "To state",
                required=True,
                ref="e10_state",
            ),
            F(
                "reason_required",
                "bool",
                "Reason required",
                default=False,
            ),
        ],
        phase=2,
        has_code=False,
        parent="e10_state",
        unique=[("from_state", "to_state")],
        icon="GitBranch",
        order=3,
        sort_default="reason_required",
        label_field="id",
    ),
)


register(
    Entity(
        "equipment",
        "equipment",
        "Equipment",
        [
            F(
                "unit_kind",
                "enum",
                "Unit kind",
                required=True,
                enum="unit_kind",
                default="main",
            ),
            F(
                "equipment_type",
                "ref",
                ref="equipment_type",
                required_when={"unit_kind": ("main",)},
            ),
            F(
                "equipment_group",
                "ref",
                "Equipment group",
                ref="equipment_group",
            ),
            F(
                "workcenter",
                "ref",
                "Work center",
                ref="workcenter",
                required_when={"unit_kind": ("main",)},
            ),
            F(
                "serial_no",
                "str",
                "Serial no.",
                max_length=64,
                search=True,
                list=False,
            ),
            F(
                "initial_state",
                "ref",
                "Initial E10 state",
                ref="e10_state",
                list=False,
            ),
            F(
                "e10_state",
                "ref",
                "Current E10 state",
                ref="e10_state",
                system=True,
            ),
            F(
                "ideal_uph",
                "float",
                "Ideal throughput (UPH)",
                help="Optional; reserved for OEE performance rate",
                list=False,
            ),
            F("is_active", "bool", default=True),
        ],
        phase=2,
        parent_required_when={
            "unit_kind": ("chamber", "load_port", "port", "sub_unit")
        },
        tree=True,
        icon="Cpu",
        order=4,
    ),
)


register(
    Entity(
        "equipment_capability",
        "equipment",
        "Equipment capability",
        [
            F("equipment", "ref", required=True, ref="equipment", cascade=True),
            F("operation", "ref", required=True, ref="operation"),
            F("recipe", "ref", ref="recipe"),
            F("is_qualified", "bool", "Qualified", default=True),
            F("qualified_until", "date", "Qualified until"),
        ],
        phase=3,
        has_code=False,
        unique=[("equipment", "operation", "recipe")],
        icon="BadgeCheck",
        order=5,
        sort_default="is_qualified",
        label_field="id",
    ),
)


register(
    Entity(
        "tool",
        "inventory",
        "Tool",
        [
            F(
                "fixture",
                "ref",
                "Tool type",
                required=True,
                ref="fixture",
            ),
            F(
                "serial_no",
                "str",
                "Serial no.",
                max_length=64,
                search=True,
            ),
            F(
                "usage_count",
                "int",
                "Usage count",
                required=True,
                default=0,
            ),
            F(
                "max_usage",
                "int",
                "Max usage",
                help="Blank: the tool type's max uses",
            ),
            F(
                "warn_pct",
                "int",
                "Warn at (% of life)",
                default=90,
                list=False,
            ),
            F("expiry_date", "date", "Expiry"),
            F(
                "tool_status",
                "enum",
                "Status",
                enum="tool_status",
                required=True,
                default="available",
            ),
            F(
                "equipment",
                "ref",
                "Mounted on",
                ref="equipment",
                list=False,
            ),
        ],
        phase=6,
        has_name=False,
        code_label="Tool ID",
        icon="Wrench",
        order=1,
    ),
)


register(
    Entity(
        "e10_auto_rule",
        "equipment",
        "E10 auto transition",
        [
            F(
                "trigger",
                "enum",
                "Trigger",
                required=True,
                enum="e10_trigger",
            ),
            F(
                "equipment_type",
                "ref",
                ref="equipment_type",
                help="Blank: all types",
            ),
            F(
                "to_state",
                "ref",
                "To state",
                required=True,
                ref="e10_state",
            ),
            F("is_active", "bool", default=True),
        ],
        phase=6,
        has_code=False,
        unique=[("trigger", "equipment_type")],
        icon="Repeat",
        order=6,
        sort_default="trigger",
        label_field="trigger",
    ),
)


ENUMS.update(
    {
        "e10_source": [
            ("manual", "Manual"),
            ("auto", "Automatic"),
        ],
        "pm_result": [
            ("ok", "OK"),
            ("ng", "NG"),
        ],
    }
)


# ---------------- E10 履历 / PM / 停机（二期阶段 5） ----------------
register(
    Entity(
        "e10_history",
        "equipment",
        "E10 history",
        [
            F("equipment", "ref", required=True, ref="equipment", cascade=True),
            F("from_state", "ref", "From state", ref="e10_state"),
            F("to_state", "ref", "To state", ref="e10_state"),
            F("source", "enum", "Source", enum="e10_source"),
            F("reason", "ref", "Reason code", ref="reason_code"),
            F("comment", "str", "Comment", max_length=300, search=True),
            # 系统生成的说明 {key, params}（前端按 mes.sysNote.<key> 翻译）
            F("note", "json", "System note", list=False, system=True),
            F("username", "str", "User", max_length=255, search=True),
            F("at", "datetime", "Time"),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        icon="History",
        order=7,
        sort_default="at",
        label_field="at",
    ),
)


register(
    Entity(
        "pm_plan",
        "equipment",
        "PM plan",
        [
            F(
                "equipment",
                "ref",
                ref="equipment",
                help="Blank: all equipment of the type",
            ),
            F("equipment_type", "ref", ref="equipment_type"),
            F("interval_days", "int", "Interval (days)"),
            F(
                "interval_lots",
                "int",
                "Interval (lots)",
            ),
            F(
                "warn_days",
                "int",
                "Warn before (days)",
                default=3,
            ),
            F("is_active", "bool", default=True),
        ],
        phase=6,
        icon="CalendarClock",
        order=8,
        children=["pm_record"],
    ),
)


register(
    Entity(
        "pm_record",
        "equipment",
        "PM record",
        [
            F(
                "pm_plan",
                "ref",
                "PM plan",
                required=True,
                ref="pm_plan",
                cascade=True,
            ),
            F("equipment", "ref", required=True, ref="equipment"),
            F("result", "enum", "Result", enum="pm_result", default="ok"),
            F("comment", "str", "Comment", max_length=300),
            F("username", "str", "User", max_length=255),
            F("done_at", "datetime", "Done at"),
        ],
        phase=6,
        has_code=False,
        parent="pm_plan",
        readonly=True,
        icon="ClipboardCheck",
        order=9,
        sort_default="done_at",
        label_field="done_at",
    ),
)


register(
    Entity(
        "downtime",
        "equipment",
        "Downtime",
        [
            F("equipment", "ref", required=True, ref="equipment"),
            F("start_at", "datetime", "Start", required=True),
            F("end_at", "datetime", "End"),
            F(
                "reason",
                "ref",
                "Reason code",
                ref="reason_code",
                required=True,
            ),
            F("e10_state", "ref", "E10 state", ref="e10_state"),
            F("comment", "str", "Comment", max_length=300, search=True),
        ],
        phase=6,
        has_code=False,
        icon="PowerOff",
        order=10,
        sort_default="start_at",
        label_field="start_at",
    ),
)


register(
    Entity(
        "equipment_material_mount",
        "equipment",
        "Material mount",
        [
            F("equipment", "ref", required=True, ref="equipment"),
            F("position", "str", "Position", required=True, max_length=50, search=True),
            F("material_lot", "ref", "Material lot", required=True, ref="material_lot"),
            F("mounted_at", "datetime", "Mounted at", required=True),
            F(
                "unmounted_at",
                "datetime",
                "Unmounted at",
                help="Blank while the lot is still mounted",
            ),
        ],
        phase=6,
        has_code=False,
        icon="PackagePlus",
        order=11,
        sort_default="mounted_at",
        label_field="position",
    ),
)
