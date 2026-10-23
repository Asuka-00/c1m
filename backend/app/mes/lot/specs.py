"""批次实体规格：批次、晶圆、批次规则、Hold、历史、谱系。"""

from app.core.spec.engine import ENUMS, Entity, F, register

register(
    # ---------------- lot / wafer rules ----------------
    Entity(
        "lot_priority",
        "lot",
        "Lot priority",
        [
            F(
                "level",
                "int",
                "Level (1 = highest)",
                required=True,
            ),
            F("color", "str", max_length=20),
            F("is_hot", "bool", "Hot lot", default=False),
        ],
        phase=4,
        icon="Flag",
        sort_default="level",
    ),
)


register(
    Entity(
        "lot_type",
        "lot",
        "Lot type",
        [
            F(
                "category",
                "enum",
                required=True,
                enum="product_type",
                default="production",
            ),
            F(
                "default_priority",
                "ref",
                "Default priority",
                ref="lot_priority",
                required=True,
            ),
            F(
                "lot_id_rule",
                "ref",
                "Lot ID rule",
                ref="code_rule",
                required=True,
            ),
            F(
                "wafer_id_rule",
                "ref",
                "Wafer ID rule",
                ref="code_rule",
                required=True,
            ),
            F(
                "max_wafers",
                "int",
                "Max wafers / units per lot",
                default=25,
            ),
        ],
        phase=4,
        icon="Tag",
        order=1,
    ),
)


register(
    Entity(
        "split_merge_rule",
        "lot",
        "Split / merge rule",
        [
            F(
                "lot_type",
                "ref",
                "Lot type",
                ref="lot_type",
                required=True,
            ),
            F(
                "allow_split",
                "bool",
                "Allow split",
                default=True,
                filter=False,
            ),
            F(
                "max_children",
                "int",
                "Max child lots",
                default=5,
            ),
            F(
                "min_wafers",
                "int",
                "Min wafers per lot",
                default=1,
            ),
            F(
                "child_id_mode",
                "enum",
                "Child lot no.",
                enum="child_id_mode",
                default="suffix",
                list=False,
            ),
            F(
                "allow_merge",
                "bool",
                "Allow merge",
                default=True,
                filter=False,
            ),
            F(
                "merge_same_wo",
                "bool",
                "Merge: same work order",
                default=True,
                filter=False,
                list=False,
            ),
            F(
                "merge_same_product",
                "bool",
                "Merge: same product",
                default=True,
                filter=False,
            ),
            F(
                "merge_same_step",
                "bool",
                "Merge: same route step",
                default=True,
                filter=False,
            ),
            F(
                "merge_same_priority",
                "bool",
                "Merge: same priority required",
                default=False,
                filter=False,
                list=False,
            ),
        ],
        phase=4,
        icon="Split",
        order=2,
    ),
)


register(
    Entity(
        "qtime_rule",
        "lot",
        "Q-Time rule",
        [
            F("route", "ref", required=True, ref="route"),
            F(
                "from_step",
                "ref",
                "From step",
                required=True,
                ref="route_step",
                depends="route",
            ),
            F(
                "to_step",
                "ref",
                "To step",
                required=True,
                ref="route_step",
                depends="route",
            ),
            F("product", "ref", ref="product", list=False),
            F("min_minutes", "int", "Min (min)"),
            F("max_minutes", "int", "Max (min)"),
            F(
                "warn_minutes",
                "int",
                "Warn at (min)",
                help="Pre-expiry warning when elapsed ≥ this (blank: none)",
                list=False,
            ),
            F(
                "action",
                "enum",
                "On violation",
                required=True,
                enum="qtime_action",
                default="hold",
            ),
            F(
                "reason",
                "ref",
                "Reason code",
                ref="reason_code",
                list=False,
                # D25 / D26：原因码选填，hold 留空时用系统原因码 qtime_expired
                help="Optional; for hold, blank uses system reason qtime_expired",
            ),
            # D24/D25：被引用的规则不能删，改为停用（停用后不计时、不处置）
            F("is_active", "bool", default=True),
            F(
                "active_since",
                "datetime",
                "Active since",
                list=False,
                system=True,
            ),
        ],
        phase=4,
        icon="Timer",
        order=3,
    ),
)


ENUMS.update(
    {
        "wo_status": [
            ("draft", "Draft"),
            ("released", "Released"),
            ("in_progress", "In progress"),
            ("on_hold", "On hold"),
            ("completed", "Completed"),
            ("closed", "Closed"),
            ("cancelled", "Cancelled"),
        ],
        "lot_status": [
            ("waiting", "Waiting"),
            ("moved_in", "Moved in"),
            ("running", "Running"),
            ("tracked_out", "Tracked out"),
            ("completed", "Finished (to receive)"),
            ("stored", "Stored"),
            ("scrapped", "Scrapped"),
            ("merged", "Merged (terminated)"),
        ],
        "wafer_status": [
            ("waiting", "Waiting"),
            ("processing", "Processing"),
            ("rework", "Rework"),
            ("completed", "Completed"),
            ("scrapped", "Scrapped"),
        ],
        "track_unit_kind": [
            ("wafer", "Wafer"),
            ("strip", "Strip"),
            ("die", "Die"),
            ("package", "Package"),
            ("unit", "Unit"),
        ],
    }
)


register(
    Entity(
        "lot",
        "wo",
        "Lot",
        [
            F(
                "work_order",
                "ref",
                "Work order",
                ref="work_order",
                required=True,
            ),
            F("product", "ref", ref="product", required=True),
            F("route", "ref", ref="route", required=True, filter=False, list=False),
            F(
                "lot_type",
                "ref",
                "Lot type",
                ref="lot_type",
                required=True,
                list=False,
            ),
            F(
                "priority",
                "ref",
                "Priority",
                ref="lot_priority",
                list=False,
            ),
            F("qty", "int", "Qty", required=True),
            F(
                "tracking_level",
                "enum",
                "Tracking level",
                enum="tracking_level",
                default="wafer",
                list=False,
            ),
            F("scrapped_qty", "int", "Scrapped", default=0, list=False),
            F("bonus_qty", "int", "Bonus", default=0, list=False),
            F(
                "rework_count",
                "int",
                "Reworks",
                default=0,
                list=False,
            ),
            F("site", "ref", ref="site"),
            F(
                "current_step",
                "ref",
                "Current step",
                ref="route_step",
                filter=False,
            ),
            F(
                "lot_status",
                "enum",
                "Status",
                enum="lot_status",
                default="waiting",
            ),
            F("on_hold", "bool", "On hold", default=False),
            F("equipment", "ref", "Equipment", ref="equipment", list=False),
            F("recipe", "ref", "Recipe", ref="recipe", list=False),
            F(
                "step_in_at",
                "datetime",
                "Arrived at step",
                list=False,
            ),
            F("stage_at", "datetime", "Last action at", list=False),
            F(
                "pending_rework",
                "bool",
                "Rework pending",
                default=False,
                list=False,
            ),
            F("route_stack", "json", "Route stack", list=False),
            F(
                "exec_ctx",
                "json",
                "Execution context",
                list=False,
            ),
            F("completed_at", "datetime", "Completed at", list=False),
            F(
                "received_qty",
                "int",
                "Received qty (good + scrap)",
                default=0,
                list=False,
            ),
            F(
                "shipped_qty",
                "int",
                "Shipped qty",
                default=0,
                list=False,
            ),
            F(
                "stored_at",
                "datetime",
                "Stored at",
                list=False,
            ),
            F("carrier", "ref", "Carrier", ref="carrier"),
            F(
                "source_ref",
                "str",
                "Source wafer / material batch",
                search=True,
            ),
            F("started_at", "datetime", "Started at"),
            F("started_by", "str", "Started by", list=False),
        ],
        phase=5,
        icon="Layers",
        order=10,
        has_name=False,
        code_label="Lot no.",
        readonly=True,
        perm_module="lot",
        sort_default="created_at",
        children=["wafer"],
    ),
)


register(
    Entity(
        "wafer",
        "wo",
        "Wafer / unit",
        [
            F("lot", "ref", "Lot", ref="lot", required=True, cascade=True),
            F(
                "unit_kind",
                "enum",
                "Unit kind",
                enum="track_unit_kind",
                required=True,
                default="wafer",
            ),
            F(
                "slot",
                "int",
                "Slot",
                required_when={"unit_kind": ("wafer",)},
            ),
            F(
                "wafer_status",
                "enum",
                "Status",
                enum="wafer_status",
                default="waiting",
            ),
            F("source_ref", "str", "Source wafer", search=True),
            F(
                "scrap_reason",
                "ref",
                "Scrap reason",
                ref="reason_code",
                list=False,
            ),
            F(
                "rework_count",
                "int",
                "Rework count",
                default=0,
                list=False,
            ),
        ],
        phase=5,
        icon="Disc",
        order=20,
        has_name=False,
        code_label="Wafer ID",
        readonly=True,
        perm_module="lot",
        sort_default="code",
    ),
)


register(
    # ---------------- execution records ----------------
    Entity(
        "lot_hold",
        "exec",
        "Lot hold",
        [
            F("lot", "ref", "Lot", required=True, ref="lot", cascade=True),
            F(
                "reason",
                "ref",
                "Reason code",
                required=True,
                ref="reason_code",
            ),
            F(
                "hold_type",
                "enum",
                "Hold type",
                enum="hold_type",
                default="manual",
            ),
            F("source", "str", "Source", max_length=40),
            F("comment", "str", "Comment", max_length=300, search=True),
            F("is_active", "bool", "Active", default=True),
            F("held_at", "datetime", "Held at"),
            F("held_by", "str", "Held by"),
            # 系统生成的说明 {key, params}（前端按 mes.sysNote.<key> 翻译；人工备注在 comment）
            F("note", "json", "System note", list=False, system=True),
            F("route_step", "ref", ref="route_step", list=False, filter=False),
            # D20：Q-Time 自动 Hold 附加信息（手动 Hold / 旧记录为空）
            F(
                "qtime_rule",
                "ref",
                "Q-Time rule",
                ref="qtime_rule",
                list=False,
                filter=False,
            ),
            F(
                "qtime_from_step",
                "ref",
                "Q-Time from step",
                ref="route_step",
                list=False,
                filter=False,
            ),
            F(
                "qtime_to_step",
                "ref",
                "Q-Time to step",
                ref="route_step",
                list=False,
                filter=False,
            ),
            F(
                "qtime_overdue_seconds",
                "int",
                "Q-Time overdue (s)",
                list=False,
            ),
            F("released_at", "datetime", "Released at"),
            F("released_by", "str", "Released by", list=False),
            F(
                "release_reason",
                "ref",
                "Release reason",
                ref="reason_code",
                list=False,
            ),
            F(
                "release_comment",
                "str",
                "Release comment",
                max_length=300,
                list=False,
            ),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        icon="PauseCircle",
        order=2,
        sort_default="held_at",
        label_field="held_at",
    ),
)


register(
    Entity(
        "lot_history",
        "exec",
        "Lot history",
        [
            F("lot", "ref", "Lot", required=True, ref="lot", cascade=True),
            F(
                "unit",
                "ref",
                "Wafer / unit",
                ref="wafer",
                cascade=True,
                filter=False,
            ),
            F("action", "enum", "Action", enum="history_action"),
            F("route_step", "ref", ref="route_step", list=False, filter=False),
            F("step_seq", "int", "Seq."),
            F("operation", "ref", ref="operation"),
            F("equipment", "ref", "Equipment", ref="equipment"),
            F("recipe", "ref", "Recipe", ref="recipe", list=False),
            F("qty", "int", "Qty"),
            F(
                "from_status",
                "enum",
                "From",
                enum="lot_status",
                list=False,
            ),
            F("to_status", "enum", "To", enum="lot_status"),
            F(
                "reason",
                "ref",
                "Reason code",
                ref="reason_code",
                list=False,
            ),
            F(
                "comment",
                "str",
                "Comment",
                max_length=300,
                search=True,
                list=False,
            ),
            F("details", "json", "Details", list=False),
            F("username", "str", "User", max_length=255, search=True),
            F("at", "datetime", "Time"),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        icon="History",
        order=1,
        menu=False,
        sort_default="at",
        label_field="action",
    ),
)


register(
    Entity(
        "lot_recipe_run",
        "exec",
        "Recipe run",
        [
            F("lot", "ref", "Lot", required=True, ref="lot", cascade=True),
            F("route_step", "ref", ref="route_step", list=False, filter=False),
            F("operation", "ref", ref="operation"),
            F("equipment", "ref", "Equipment", ref="equipment"),
            F("recipe", "ref", "Recipe", ref="recipe"),
            F("recipe_version", "int", "Recipe version"),
            F(
                "eqp_recipe",
                "str",
                "Equipment recipe",
                max_length=200,
                search=True,
            ),
            F(
                "chambers",
                "str",
                "Chambers",
                max_length=300,
                list=False,
            ),
            F("params", "json", "Parameters", list=False),
            F(
                "param_specs",
                "json",
                "Parameter specs",
                list=False,
            ),
            F("qty", "int", "Qty"),
            F("track_in_at", "datetime", "Track in"),
            F("track_out_at", "datetime", "Track out"),
            F("username", "str", "User", max_length=255, search=True),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        icon="FileCode",
        order=2,
        sort_default="track_in_at",
        label_field="track_in_at",
    ),
)


register(
    Entity(
        "lot_material_use",
        "exec",
        "Material use",
        [
            F("lot", "ref", "Lot", required=True, ref="lot", cascade=True),
            F("route_step", "ref", ref="route_step"),
            F("operation", "ref", ref="operation"),
            F("equipment", "ref", ref="equipment"),
            F("material_lot", "ref", "Material lot", required=True, ref="material_lot"),
            F("material", "ref", "Material", required=True, ref="material"),
            F("qty", "float", "Quantity", required=True),
            F("uom", "ref", ref="uom"),
            F("at", "datetime", "Time", required=True),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        internal=True,  # 出站扣料明细：只供追溯查询，不开放通用接口与菜单
        sort_default="at",
        label_field="qty",
    ),
)


register(
    Entity(
        "lot_genealogy",
        "exec",
        "Lot genealogy",
        [
            F(
                "parent_lot",
                "ref",
                "Parent / source lot",
                required=True,
                ref="lot",
                cascade=True,
            ),
            F(
                "child_lot",
                "ref",
                "Child / target lot",
                required=True,
                ref="lot",
                cascade=True,
            ),
            F("relation", "enum", "Relation", enum="genealogy_relation"),
            F("qty", "int", "Qty"),
            F(
                "units",
                "json",
                "Wafers / units",
                list=False,
            ),
            F("route_step", "ref", ref="route_step", list=False, filter=False),
            F("username", "str", "User", max_length=255, search=True),
            F("at", "datetime", "Time"),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        icon="GitFork",
        order=3,
        menu=False,
        sort_default="at",
        label_field="relation",
    ),
)
