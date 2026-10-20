"""质量实体规格：量测项、DC 计划、抽样、缺陷 / 原因代码、DC 结果。"""

from app.core.spec.engine import ENUMS, Entity, F, register

ENUMS.update(
    {
        "child_id_mode": [
            ("suffix", "Parent no. + suffix"),
            ("code_rule", "Lot type ID rule"),
        ],
        "meas_type": [
            ("numeric", "Numeric"),
            ("attribute", "Attribute (pass/fail)"),
            ("count", "Count"),
        ],
        "sample_level": [
            ("lot", "Lot"),
            ("wafer", "Wafer"),
        ],
        "wafer_selection": [
            ("first", "First N"),
            ("last", "Last N"),
            ("random", "Random"),
            ("alternate", "Alternate slots"),
            ("fixed", "Fixed slots"),
        ],
        "defect_category": [
            ("particle", "Particle"),
            ("scratch", "Scratch"),
            ("pattern", "Pattern"),
            ("residue", "Residue"),
            ("electrical", "Electrical"),
            ("other", "Other"),
        ],
        "severity": [
            ("minor", "Minor"),
            ("major", "Major"),
            ("critical", "Critical"),
        ],
        "reason_type": [
            ("scrap", "Scrap"),
            ("rework", "Rework"),
            ("hold", "Hold"),
            ("e10", "Equipment state change"),
            ("downtime", "Equipment downtime"),
            ("release", "Release"),
            ("jump", "Jump step"),
            ("bonus", "Bonus (qty added)"),
        ],
        "oos_action": [
            ("warn", "Warn"),
            ("rework", "Rework"),
            ("auto_hold", "Auto hold"),
            ("block", "Block track out"),
        ],
        "qtime_action": [
            ("warn", "Warn"),
            ("hold", "Hold lot"),
            ("rework", "Rework"),
            # D26：scrap 已去掉（迁移 0011 改成 hold）
        ],
    }
)

register(
    # ---------------- quality ----------------
    Entity(
        "measurement_item",
        "quality",
        "Measurement item",
        [
            F(
                "meas_type",
                "enum",
                "Data type",
                required=True,
                enum="meas_type",
                default="numeric",
            ),
            F("uom", "ref", ref="uom", required_when={"meas_type": ("numeric",)}),
            F("precision", "int", "Decimals", default=3),
            F(
                "oos_action",
                "enum",
                "OOS action",
                required=True,
                enum="oos_action",
                default="auto_hold",
            ),
            F(
                "oos_reason",
                "ref",
                "OOS hold reason",
                ref="reason_code",
                list=False,
            ),
        ],
        phase=4,
        icon="Ruler",
    ),
)


register(
    Entity(
        "dc_plan",
        "quality",
        "Data collection plan",
        [F("operation", "ref", ref="operation", required=True)],
        phase=4,
        versioned=True,
        children=["dc_plan_item"],
        icon="ClipboardList",
        order=1,
    ),
)


register(
    Entity(
        "dc_plan_item",
        "quality",
        "DC plan item",
        [
            F(
                "dc_plan",
                "ref",
                "DC plan",
                required=True,
                ref="dc_plan",
                cascade=True,
            ),
            F(
                "measurement_item",
                "ref",
                "Measurement item",
                required=True,
                ref="measurement_item",
            ),
            F("seq", "int", "Seq.", default=10),
            F(
                "sites",
                "int",
                "Sites per wafer",
                default=5,
            ),
            F("target", "float"),
            F("lsl", "float"),
            F("usl", "float"),
        ],
        phase=4,
        has_code=False,
        parent="dc_plan",
        unique=[("dc_plan", "measurement_item")],
        icon="List",
        order=2,
        sort_default="seq",
        label_field="seq",
    ),
)


register(
    Entity(
        "sampling_rule",
        "quality",
        "Sampling rule",
        [
            F(
                "level",
                "enum",
                "Level",
                required=True,
                enum="sample_level",
                default="lot",
            ),
            F("operation", "ref", ref="operation", required=True),
            F("dc_plan", "ref", "DC plan", ref="dc_plan"),
            F("product", "ref", ref="product", list=False),
            F(
                "lot_frequency",
                "int",
                "Every N lots",
                default=1,
            ),
            F(
                "wafer_count",
                "int",
                "Wafers per lot",
                required_when={"level": ("wafer",)},
            ),
            F(
                "wafer_selection",
                "enum",
                "Wafer selection",
                enum="wafer_selection",
                required_when={"level": ("wafer",)},
            ),
            F(
                "fixed_slots",
                "str",
                "Fixed slots",
                max_length=100,
                list=False,
                help="Comma separated slot numbers, e.g. 1,13,25",
                required_when={"wafer_selection": ("fixed",)},
            ),
            F("is_active", "bool", default=True),
        ],
        phase=4,
        icon="Target",
        order=3,
    ),
)


register(
    Entity(
        "defect_code",
        "quality",
        "Defect code",
        [
            F("category", "enum", required=True, enum="defect_category"),
            F(
                "severity",
                "enum",
                "Severity",
                required=True,
                enum="severity",
                default="minor",
            ),
            F("is_killer", "bool", "Killer defect", default=False),
        ],
        phase=4,
        icon="Bug",
        order=4,
    ),
)


register(
    Entity(
        "reason_code",
        "quality",
        "Reason code",
        [
            F(
                "reason_type",
                "enum",
                "Reason type",
                required=True,
                enum="reason_type",
            ),
            F("area", "ref", ref="area"),
            F(
                "comment_required",
                "bool",
                "Comment required",
                default=False,
            ),
            F("is_active", "bool", default=True),
        ],
        phase=4,
        unique=[("reason_type", "code")],
        icon="Flag",
        order=5,
    ),
)


register(
    Entity(
        "dc_result",
        "exec",
        "DC result",
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
            F("route_step", "ref", ref="route_step", list=False, filter=False),
            F("dc_plan", "ref", "DC plan", ref="dc_plan"),
            F(
                "measurement_item",
                "ref",
                "Measurement item",
                ref="measurement_item",
            ),
            F("site_no", "int", "Site", default=1),
            F("value", "float", "Value"),
            F("is_oos", "bool", "OOS", default=False),
            F(
                "oos_action",
                "enum",
                "OOS action",
                enum="oos_action",
            ),
            F(
                "username",
                "str",
                "User",
                max_length=255,
                search=True,
                list=False,
            ),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        icon="LineChart",
        order=3,
        sort_default="created_at",
        label_field="value",
    ),
)
