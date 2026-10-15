"""设备实体规格：类型、组、E10 状态/迁移/自动规则、能力、工具。"""

from app.core.spec.engine import ENUMS, Entity, F, register

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
            F(
                "qual_state",
                "enum",
                "Qual state|Qual 状态|Qual 状態",
                enum="qual_state",
                default="ready",
                system=True,
                help="Waits for Qual after an OK PM until a Qual passes|PM 判 OK 后进入待 Qual，"
                "Qual 通过才恢复|PM OK 後は Qual 合格まで Qual 待ち",
            ),
            F(
                "ideal_uph",
                "float",
                "Ideal throughput (UPH)|理论产能（UPH）|理論スループット（UPH）",
                help="Optional; reserved for OEE performance rate|可选，预留给 OEE 性能稼动率|任意。OEE 性能稼働率用に予約",
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
            # P2-B10：按 life_unit 计数，numeric(18,6)（0026）
            F(
                "usage_count",
                "float",
                "Usage|已用寿命|使用量",
                required=True,
                default=0,
                scale=6,
            ),
            F(
                "max_usage",
                "float",
                "Max life|寿命上限|寿命上限",
                scale=6,
                help="Blank: the tool type's max life|留空则使用工具类型的寿命上限|空欄：工具タイプの寿命上限",
            ),
            F(
                "warn_pct",
                "int",
                "Warn at (% of life)|预警阈值（寿命%）|警告しきい値（寿命%）",
                default=90,
                list=False,
            ),
            # D54：预警区间 max × warn_ratio <= 已用 < max（可放行）；
            # 空则取工具类型的 warn_ratio，再空取 warn_pct / 100（默认 90 → 0.9）
            F(
                "warn_ratio",
                "float",
                "Warn ratio|预警比例|警告比率",
                scale=4,
                list=False,
            ),
            F(
                "sub_unit",
                "ref",
                "Sub-unit|子单元|サブユニット",
                ref="equipment",
                list=False,
                filter=False,
            ),
            F("mounted_at", "datetime", "Mounted at|安装时间|装着日時", list=False),
            F(
                "life_reset_count",
                "int",
                "Refurbish count|修磨次数|再生回数",
                default=0,
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
    # ---------------- P2-B10 工具寿命履历 ----------------
    Entity(
        "tool_usage",
        "inventory",
        "Tool usage|工具计数履历|工具使用履歴",
        [
            F("tool", "ref", "Tool|工具|工具", ref="tool", required=True, cascade=True),
            F("equipment", "ref", "Equipment|设备|設備", ref="equipment"),
            F(
                "sub_unit",
                "ref",
                "Sub-unit|子单元|サブユニット",
                ref="equipment",
                list=False,
                filter=False,
            ),
            F("lot", "ref", "Lot|批次|ロット", ref="lot"),
            F("operation", "ref", "Operation|工序|工程", ref="operation"),
            F("delta", "float", "Delta|增量|増分", required=True, scale=6),
            F("count_after", "float", "Count after|计数后|カウント後", scale=6),
            F("kind", "enum", "Kind|类型|種別", enum="tool_usage_kind", required=True),
            F("occurred_at", "datetime", "Time|时间|日時", required=True),
            F("reason", "ref", "Reason|原因|理由", ref="reason_code", list=False),
            F("comment", "str", "Comment|备注|コメント", max_length=300, list=False),
            F(
                "source",
                "enum",
                "Source|来源|ソース",
                enum="alarm_source",
                required=True,
                default="manual",
            ),
            F(
                "external_event_id",
                "str",
                "External event ID|外部事件号|外部イベント ID",
                max_length=128,
                list=False,
            ),
            F("username", "str", "User|用户|ユーザー", max_length=255, search=True),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        menu=False,
        partial_unique=[
            (
                "uq_mes_tool_usage_event",
                ("source", "external_event_id"),
                "external_event_id IS NOT NULL",
            ),
        ],
        sort_default="occurred_at",
        label_field="delta",
    ),
    Entity(
        "tool_mount_log",
        "inventory",
        "Tool mount log|工具装卸履历|工具装着履歴",
        [
            F("tool", "ref", "Tool|工具|工具", ref="tool", required=True, cascade=True),
            F(
                "equipment",
                "ref",
                "Equipment|设备|設備",
                ref="equipment",
                required=True,
            ),
            F(
                "sub_unit",
                "ref",
                "Sub-unit|子单元|サブユニット",
                ref="equipment",
                list=False,
                filter=False,
            ),
            F("port_code", "str", "Position|位置|位置", max_length=64),
            F("mounted_at", "datetime", "Mounted at|安装时间|装着日時", required=True),
            F("unmounted_at", "datetime", "Unmounted at|卸下时间|取外し日時"),
            F(
                "unmount_reason",
                "enum",
                "Unmount reason|卸下原因|取外し理由",
                enum="tool_unmount_reason",
            ),
            F("replaced_by_tool", "ref", "Replaced by|更换为|交換先", ref="tool"),
            F("usage_at_mount", "float", "Usage at mount|安装时计数|装着時", scale=6),
            F(
                "usage_at_unmount",
                "float",
                "Usage at unmount|卸下时计数|取外し時",
                scale=6,
            ),
            F("comment", "str", "Comment|备注|コメント", max_length=300, list=False),
            F(
                "source",
                "enum",
                "Source|来源|ソース",
                enum="alarm_source",
                required=True,
                default="manual",
            ),
            F(
                "external_event_id",
                "str",
                "External event ID|外部事件号|外部イベント ID",
                max_length=128,
                list=False,
            ),
            F("username", "str", "User|用户|ユーザー", max_length=255, search=True),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        menu=False,
        partial_unique=[
            (
                "uq_mes_tool_mount_open",
                ("tool_id",),
                "unmounted_at IS NULL",
            ),
        ],
        sort_default="mounted_at",
        label_field="mounted_at",
    ),
)

ENUMS.update(
    {
        "tool_usage_kind": [
            ("track_out", "Track out|出站|トラックアウト"),
            ("report", "Reported|上报|報告"),
            ("adjust", "Adjust|调整|調整"),
            ("reset", "Reset / refurbish|重置 / 修磨|リセット・再生"),
        ],
        "tool_unmount_reason": [
            ("life_end", "End of life|寿命到期|寿命到達"),
            ("broken", "Broken|损坏|破損"),
            ("pm", "PM|保养|PM"),
            ("swap", "Swap|更换|交換"),
            ("other", "Other|其他|その他"),
        ],
    }
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


ENUMS.update(
    {
        "e10_source": [
            ("manual", "Manual|手动|手動"),
            ("auto", "Automatic|自动|自動"),
            # D53-3：报警等设备上报触发（D58 前的旧记录）
            ("equipment", "Equipment|设备|設備"),
            # D53-4 / D58：EAP / 模拟器上报
            ("eap", "EAP|EAP|EAP"),
            ("simulator", "Simulator|模拟器|シミュレータ"),
        ],
        # D58：E10 变化的触发方式（人工 / 设备事件或报警 / 系统规则）
        "e10_history_trigger": [
            ("manual", "Manual|人工|手動"),
            ("equipment", "Equipment event|设备事件|設備イベント"),
            ("system", "System|系统|システム"),
        ],
        "pm_result": [
            ("ok", "OK|合格|合格"),
            ("ng", "NG|不合格|不合格"),
        ],
        # B6：PM 后 Qual 放行（wait_qual 即设计中的 WAIT_QUAL）
        "qual_state": [
            ("ready", "Ready|可生产|生産可"),
            ("wait_qual", "Waiting Qual (WAIT_QUAL)|待 Qual|Qual 待ち"),
        ],
        "qual_status": [
            ("open", "Open|待登记|未登録"),
            ("passed", "Passed|通过|合格"),
            ("failed", "Failed|不通过|不合格"),
        ],
    }
)


# ---------------- E10 履历 / PM / 停机（二期阶段 5） ----------------
register(
    Entity(
        "e10_history",
        "equipment",
        "E10 history|E10 状态履历|E10 状態履歴",
        [
            F("equipment", "ref", required=True, ref="equipment", cascade=True),
            F("from_state", "ref", "From state|源状态|遷移元", ref="e10_state"),
            F("to_state", "ref", "To state|目标状态|遷移先", ref="e10_state"),
            F("source", "enum", "Source|来源|ソース", enum="e10_source"),
            F(
                "trigger",
                "enum",
                "Trigger|触发方式|トリガー",
                enum="e10_history_trigger",
            ),
            F("reason", "ref", "Reason code|原因代码|理由コード", ref="reason_code"),
            F("comment", "str", "Comment|备注|コメント", max_length=300, search=True),
            F("username", "str", "User|用户|ユーザー", max_length=255, search=True),
            F("at", "datetime", "Time|时间|日時"),
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
        "PM plan|PM 计划|PM 計画",
        [
            F(
                "equipment",
                "ref",
                ref="equipment",
                help="Blank: all equipment of the type|留空则适用该类型全部设备|空欄：タイプの全設備",
            ),
            F("equipment_type", "ref", ref="equipment_type"),
            F("interval_days", "int", "Interval (days)|周期（天）|周期（日）"),
            F(
                "interval_lots",
                "int",
                "Interval (lots)|周期（批次数）|周期（ロット数）",
            ),
            F(
                "warn_days",
                "int",
                "Warn before (days)|提前预警（天）|事前警告（日）",
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
        "PM record|PM 执行记录|PM 実施記録",
        [
            F(
                "pm_plan",
                "ref",
                "PM plan|PM 计划|PM 計画",
                required=True,
                ref="pm_plan",
                cascade=True,
            ),
            F("equipment", "ref", required=True, ref="equipment"),
            F("result", "enum", "Result|结果|結果", enum="pm_result", default="ok"),
            F("comment", "str", "Comment|备注|コメント", max_length=300),
            F("username", "str", "User|用户|ユーザー", max_length=255),
            F("done_at", "datetime", "Done at|完成时间|実施日時"),
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
        "Downtime|停机记录|停止記録",
        [
            F("equipment", "ref", required=True, ref="equipment"),
            F("start_at", "datetime", "Start|开始时间|開始", required=True),
            F("end_at", "datetime", "End|结束时间|終了"),
            F(
                "reason",
                "ref",
                "Reason code|原因代码|理由コード",
                ref="reason_code",
                required=True,
            ),
            F("e10_state", "ref", "E10 state|E10 状态|E10 状態", ref="e10_state"),
            F("comment", "str", "Comment|备注|コメント", max_length=300, search=True),
        ],
        phase=6,
        has_code=False,
        icon="PowerOff",
        order=10,
        sort_default="start_at",
        label_field="start_at",
    ),
)


ENUMS.update(
    {
        "mount_source": [
            ("manual", "Manual|人工|手動"),
            ("eap", "EAP|EAP|EAP"),
        ],
    }
)

register(
    # 机台上料记录（D28 / B3）：上料口 = (equipment, port_code)；同一上料口同时只装一批
    Entity(
        "equipment_material_mount",
        "equipment",
        "Equipment material mount|机台上料记录|装置資材装着記録",
        [
            F(
                "equipment",
                "ref",
                "Equipment|设备|設備",
                ref="equipment",
                required=True,
            ),
            F(
                "port_code",
                "str",
                "Load port|上料口|投入口",
                required=True,
                max_length=64,
                search=True,
            ),
            F(
                "material_lot",
                "ref",
                "Material lot|物料批|資材ロット",
                ref="material_lot",
                required=True,
            ),
            F("material", "ref", "Material|物料|資材", ref="material"),
            F("mounted_at", "datetime", "Mounted at|装上时间|装着日時", required=True),
            F("unmounted_at", "datetime", "Unmounted at|卸下时间|取外し日時"),
            F(
                "source",
                "enum",
                "Source|来源|ソース",
                enum="mount_source",
                required=True,
                default="manual",
            ),
            F(
                "external_event_id",
                "str",
                "External event ID|外部事件号|外部イベント ID",
                max_length=128,
                search=True,
                list=False,
            ),
            F("mounted_by", "str", "Mounted by|上料人|装着者", max_length=255),
            F(
                "unmounted_by",
                "str",
                "Unmounted by|卸料人|取外し者",
                max_length=255,
                list=False,
            ),
            F("comment", "str", "Comment|备注|コメント", max_length=300, list=False),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        partial_unique=[
            (
                "uq_mes_eqp_mount_port_open",
                ("equipment", "port_code"),
                "unmounted_at IS NULL",
            ),
            (
                "uq_mes_eqp_mount_event",
                ("source", "external_event_id"),
                "external_event_id IS NOT NULL",
            ),
        ],
        icon="PackagePlus",
        order=20,
        sort_default="mounted_at",
        label_field="port_code",
    ),
)


register(
    # PM 后 Qual 任务（B6）：PM 判 OK 生成；登记通过后机台恢复可生产，不通过生成复测任务
    Entity(
        "equipment_qual",
        "equipment",
        "Qual task|Qual 任务|Qual タスク",
        [
            F("equipment", "ref", required=True, ref="equipment", cascade=True),
            F("pm_plan", "ref", "PM plan|PM 计划|PM 計画", ref="pm_plan"),
            F(
                "pm_record",
                "ref",
                "PM record|PM 记录|PM 記録",
                ref="pm_record",
                list=False,
            ),
            F(
                "qual_status",
                "enum",
                "Status|状态|状態",
                enum="qual_status",
                default="open",
            ),
            F(
                "retry_of",
                "ref",
                "Retry of|复测自|再テスト元",
                ref="equipment_qual",
                list=False,
            ),
            F("requested_at", "datetime", "Requested at|生成时间|作成日時"),
            F("done_by", "str", "Recorded by|登记人|登録者", max_length=255),
            F("done_at", "datetime", "Recorded at|登记时间|登録日時"),
            F("comment", "str", "Comment|备注|コメント", max_length=300, list=False),
            # 预留给 EAP 上报（本期人工登记不开放，一律 manual / 空）
            F(
                "sub_unit",
                "ref",
                "Sub-unit (chamber / spindle / test head / bond head)|子单元（腔体 / 主轴 / 测试头 / 焊头）|サブユニット（チャンバー・スピンドル・テストヘッド・ボンドヘッド）",
                ref="equipment",
                list=False,
            ),
            F(
                "source",
                "enum",
                "Source|来源|ソース",
                enum="mount_source",
                required=True,
                default="manual",
            ),
            F(
                "external_event_id",
                "str",
                "External event ID|外部事件号|外部イベント ID",
                max_length=128,
                list=False,
            ),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        partial_unique=[
            (
                "uq_mes_eqp_qual_event",
                ("source", "external_event_id"),
                "external_event_id IS NOT NULL",
            ),
        ],
        icon="BadgeCheck",
        order=10,
        sort_default="requested_at",
        label_field="requested_at",
    ),
)
