"""质量实体规格：量测项、DC 计划、抽样、缺陷 / 原因代码、DC 结果。"""

from app.core.spec.engine import ENUMS, Entity, F, register

ENUMS.update(
    {
        "child_id_mode": [
            ("suffix", "Parent no. + suffix|母批号 + 后缀|親番号 + 接尾辞"),
            ("code_rule", "Lot type ID rule|批次类型编码规则|ロットタイプ ID ルール"),
        ],
        "meas_type": [
            ("numeric", "Numeric|数值型|数値"),
            ("attribute", "Attribute (pass/fail)|属性型（合格/不合格）|属性（合否）"),
            ("count", "Count|计数型|計数"),
        ],
        "sample_level": [
            ("lot", "Lot|批次|ロット"),
            ("wafer", "Wafer|晶圆|ウェーハ"),
        ],
        "wafer_selection": [
            ("first", "First N|前 N 片|先頭 N 枚"),
            ("last", "Last N|后 N 片|末尾 N 枚"),
            ("random", "Random|随机|ランダム"),
            ("alternate", "Alternate slots|隔槽|交互スロット"),
            ("fixed", "Fixed slots|固定槽位|固定スロット"),
        ],
        "defect_category": [
            ("particle", "Particle|颗粒|パーティクル"),
            ("scratch", "Scratch|划伤|スクラッチ"),
            ("pattern", "Pattern|图形缺陷|パターン欠陥"),
            ("residue", "Residue|残留|残渣"),
            ("electrical", "Electrical|电性|電気特性"),
            ("other", "Other|其他|その他"),
        ],
        "severity": [
            ("minor", "Minor|轻微|軽微"),
            ("major", "Major|严重|重大"),
            ("critical", "Critical|致命|致命的"),
        ],
        "reason_type": [
            ("scrap", "Scrap|报废|スクラップ"),
            ("rework", "Rework|返工|リワーク"),
            ("hold", "Hold|冻结|ホールド"),
            ("e10", "Equipment state change|设备状态变更|設備状態変更"),
            ("downtime", "Equipment downtime|设备停机|設備停止"),
            ("release", "Release|解冻|リリース"),
            ("jump", "Jump step|跳站|ステップジャンプ"),
            ("bonus", "Bonus (qty added)|补数|追加"),
        ],
        "oos_action": [
            ("warn", "Warn|预警|警告"),
            ("rework", "Rework|返工|リワーク"),
            ("auto_hold", "Auto hold|自动 Hold|自動ホールド"),
            ("block", "Block track out|禁止下机|トラックアウト禁止"),
        ],
        "qtime_action": [
            ("warn", "Warn|预警|警告"),
            ("hold", "Hold lot|冻结批次|ロット保留"),
            ("rework", "Rework|返工|リワーク"),
            ("scrap", "Scrap|报废|スクラップ"),
        ],
    }
)

register(
    # ---------------- quality ----------------
    Entity(
        "measurement_item",
        "quality",
        "Measurement item|量测项目|測定項目",
        [
            F(
                "meas_type",
                "enum",
                "Data type|数据类型|データ型",
                required=True,
                enum="meas_type",
                default="numeric",
            ),
            F("uom", "ref", ref="uom", required_when={"meas_type": ("numeric",)}),
            F("precision", "int", "Decimals|小数位|小数桁", default=3),
            F(
                "oos_action",
                "enum",
                "OOS action|超规动作|規格外処置",
                required=True,
                enum="oos_action",
                default="auto_hold",
            ),
            F(
                "oos_reason",
                "ref",
                "OOS hold reason|超规 Hold 原因|規格外ホールド理由",
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
        "Data collection plan|数据收集计划|データ収集計画",
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
        "DC plan item|收集项|収集項目",
        [
            F(
                "dc_plan",
                "ref",
                "DC plan|数据收集计划|データ収集計画",
                required=True,
                ref="dc_plan",
                cascade=True,
            ),
            F(
                "measurement_item",
                "ref",
                "Measurement item|量测项目|測定項目",
                required=True,
                ref="measurement_item",
            ),
            F("seq", "int", "Seq.|序号|順番", default=10),
            F(
                "sites",
                "int",
                "Sites per wafer|每片测点数|ウェーハ当たり測定点",
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
        "Sampling rule|抽样规则|サンプリング規則",
        [
            F(
                "level",
                "enum",
                "Level|抽样层级|レベル",
                required=True,
                enum="sample_level",
                default="lot",
            ),
            F("operation", "ref", ref="operation", required=True),
            F("dc_plan", "ref", "DC plan|数据收集计划|データ収集計画", ref="dc_plan"),
            F("product", "ref", ref="product", list=False),
            F(
                "lot_frequency",
                "int",
                "Every N lots|每 N 批抽 1 批|N ロット毎",
                default=1,
            ),
            F(
                "wafer_count",
                "int",
                "Wafers per lot|每批抽片数|ロット当たり枚数",
                required_when={"level": ("wafer",)},
            ),
            F(
                "wafer_selection",
                "enum",
                "Wafer selection|选片方式|ウェーハ選択",
                enum="wafer_selection",
                required_when={"level": ("wafer",)},
            ),
            F(
                "fixed_slots",
                "str",
                "Fixed slots|固定槽位|固定スロット",
                max_length=100,
                list=False,
                help="Comma separated slot numbers, e.g. 1,13,25|逗号分隔的槽位号，例如 1,13,25|カンマ区切りのスロット番号（例：1,13,25）",
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
        "Defect code|缺陷代码|欠陥コード",
        [
            F("category", "enum", required=True, enum="defect_category"),
            F(
                "severity",
                "enum",
                "Severity|严重度|重大度",
                required=True,
                enum="severity",
                default="minor",
            ),
            F("is_killer", "bool", "Killer defect|致命缺陷|キラー欠陥", default=False),
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
        "Reason code|原因代码|理由コード",
        [
            F(
                "reason_type",
                "enum",
                "Reason type|原因类型|理由種別",
                required=True,
                enum="reason_type",
            ),
            F("area", "ref", ref="area"),
            F(
                "comment_required",
                "bool",
                "Comment required|需填写备注|コメント必須",
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
        "DC result|量测数据|測定データ",
        [
            F("lot", "ref", "Lot|批次|ロット", required=True, ref="lot", cascade=True),
            F(
                "unit",
                "ref",
                "Wafer / unit|晶圆 / 单元|ウェーハ・ユニット",
                ref="wafer",
                cascade=True,
                filter=False,
            ),
            F("route_step", "ref", ref="route_step", list=False, filter=False),
            F("dc_plan", "ref", "DC plan|数据收集计划|データ収集計画", ref="dc_plan"),
            F(
                "measurement_item",
                "ref",
                "Measurement item|量测项目|測定項目",
                ref="measurement_item",
            ),
            F("site_no", "int", "Site|测点|測定点", default=1),
            F("value", "float", "Value|值|値"),
            F("is_oos", "bool", "OOS|超规|規格外", default=False),
            F(
                "oos_action",
                "enum",
                "OOS action|超规动作|規格外処置",
                enum="oos_action",
            ),
            F(
                "username",
                "str",
                "User|用户|ユーザー",
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
