from app.core.spec.engine import Entity, F, register

register(
    # ---------------- equipment ----------------
    Entity(
        "equipment_type",
        "equipment",
        "Equipment type|设备类型|設備タイプ",
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
        "Equipment group|设备组|設備グループ",
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
        "E10 state|E10 状态|E10 状態",
        [
            F(
                "e10_category",
                "enum",
                "E10 category|E10 类别|E10 区分",
                required=True,
                enum="e10_category",
            ),
            F("color", "str", max_length=20),
            F("is_initial", "bool", "Initial state|初始状态|初期状態", default=False),
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
        "E10 transition|E10 状态迁移|E10 状態遷移",
        [
            F(
                "from_state",
                "ref",
                "From state|源状态|遷移元",
                required=True,
                ref="e10_state",
                cascade=True,
            ),
            F(
                "to_state",
                "ref",
                "To state|目标状态|遷移先",
                required=True,
                ref="e10_state",
            ),
            F(
                "reason_required",
                "bool",
                "Reason required|需填写原因|理由必須",
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
        "Equipment|设备|設備",
        [
            F(
                "unit_kind",
                "enum",
                "Unit kind|单元类型|ユニット種別",
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
                "Equipment group|设备组|設備グループ",
                ref="equipment_group",
            ),
            F(
                "workcenter",
                "ref",
                "Work center|工作中心|ワークセンター",
                ref="workcenter",
                required_when={"unit_kind": ("main",)},
            ),
            F(
                "serial_no",
                "str",
                "Serial no.|序列号|シリアル番号",
                max_length=64,
                search=True,
                list=False,
            ),
            F(
                "initial_state",
                "ref",
                "Initial E10 state|初始 E10 状态|初期 E10 状態",
                ref="e10_state",
                list=False,
            ),
            F(
                "e10_state",
                "ref",
                "Current E10 state|当前 E10 状态|現在 E10 状態",
                ref="e10_state",
                system=True,
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
        "Equipment capability|设备能力|設備能力",
        [
            F("equipment", "ref", required=True, ref="equipment", cascade=True),
            F("operation", "ref", required=True, ref="operation"),
            F("recipe", "ref", ref="recipe"),
            F("is_qualified", "bool", "Qualified|已认证|認定済", default=True),
            F("qualified_until", "date", "Qualified until|认证有效期|認定期限"),
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
        "Tool|工具|工具",
        [
            F(
                "fixture",
                "ref",
                "Tool type|工具类型|工具タイプ",
                required=True,
                ref="fixture",
            ),
            F(
                "serial_no",
                "str",
                "Serial no.|序列号|シリアル番号",
                max_length=64,
                search=True,
            ),
            F(
                "usage_count",
                "int",
                "Usage count|使用次数|使用回数",
                required=True,
                default=0,
            ),
            F(
                "max_usage",
                "int",
                "Max usage|最大使用次数|最大使用回数",
                help="Blank: the tool type's max uses|留空则使用工具类型的最大使用次数|空欄：工具タイプの最大使用回数",
            ),
            F(
                "warn_pct",
                "int",
                "Warn at (% of life)|预警阈值（寿命%）|警告しきい値（寿命%）",
                default=90,
                list=False,
            ),
            F("expiry_date", "date", "Expiry|有效期|有効期限"),
            F(
                "tool_status",
                "enum",
                "Status|状态|状態",
                enum="tool_status",
                required=True,
                default="available",
            ),
            F(
                "equipment",
                "ref",
                "Mounted on|安装设备|装着設備",
                ref="equipment",
                list=False,
            ),
        ],
        phase=6,
        has_name=False,
        code_label="Tool ID|工具编号|工具 ID",
        icon="Wrench",
        order=1,
    ),
)


register(
    Entity(
        "e10_auto_rule",
        "equipment",
        "E10 auto transition|E10 自动迁移|E10 自動遷移",
        [
            F(
                "trigger",
                "enum",
                "Trigger|触发时机|トリガー",
                required=True,
                enum="e10_trigger",
            ),
            F(
                "equipment_type",
                "ref",
                ref="equipment_type",
                help="Blank: all types|留空表示所有类型|空欄：全タイプ",
            ),
            F(
                "to_state",
                "ref",
                "To state|目标状态|遷移先",
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
