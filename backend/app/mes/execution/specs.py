"""执行实体规格：检查规则 / 方案 / 绑定 / 日志。"""

from app.core.spec.engine import ENUMS, FIELD_LABELS, Entity, F, register

TRIGGERS = [
    ("move_in", "Move in|进站|ムーブイン"),
    ("track_in", "Track in|上机|トラックイン"),
    ("track_out", "Track out|下机|トラックアウト"),
    ("move_out", "Move out|出站|ムーブアウト"),
    ("split", "Split|分批|分割"),
    ("merge", "Merge|合批|統合"),
    ("jump", "Jump step|跳站|ステップジャンプ"),
    ("adjust", "Scrap / bonus|报废 / 补数|廃棄・追加"),
    ("sort", "Wafer sort|晶圆整理|ウェーハソート"),
    ("priority", "Priority change|优先级变更|優先度変更"),
]
# built-in check types (app.mes.checks implements them; plugins may add more)
CHECK_TYPES = [
    (
        "e10_available",
        "Equipment E10 state available|设备 E10 状态可用|設備 E10 状態使用可",
    ),
    (
        "eqp_capability",
        "Equipment capability / recipe match|设备能力 / 配方匹配|設備能力・レシピ整合",
    ),
    ("recipe_active", "Recipe active|配方已生效|レシピ有効"),
    ("reticle_available", "Reticle available|光罩可用|レチクル使用可"),
    ("material_sufficient", "Material sufficient|物料充足|資材充足"),
    ("tool_life", "Tool available + life|工具可用 + 寿命|工具使用可・寿命"),
    ("carrier_available", "Carrier available|载具可用|キャリア使用可"),
    ("batch_same_step", "Batch: same step|批量：同一工步|一括：同一ステップ"),
    ("sort_order", "Sort keeps wafer order|整理保持晶圆顺序|ソート順序維持"),
    ("hot_lot_limit", "Hot lot WIP limit|急件在制上限|ホットロット仕掛上限"),
    (
        "handover_ack_other",
        "Handover confirmed by another user|接班须由他人确认|引継ぎは別ユーザーが確認",
    ),
    ("operator_qualified", "Operator qualified|操作员具备资质|作業者資格あり"),
    (
        "qual_expiry_notice",
        "Qualification expiry notice|资质到期提醒|資格期限通知",
    ),
    ("future_hold", "Future hold at step|预约 Hold|予約ホールド"),
    ("wo_due", "Work order due notice|工单交期提醒|作業指示納期通知"),
    ("carrier_clean", "Carrier cleaning due|载具清洗周期|キャリア洗浄周期"),
    ("carrier_usage", "Carrier usage limit|载具使用次数|キャリア使用回数"),
    ("chamber_required", "Chamber selected|已选腔体|チャンバー選択済"),
    (
        "chamber_available",
        "Chamber E10 state available|腔体 E10 状态可用|チャンバー E10 状態使用可",
    ),
    ("qtime", "Q-Time|Q-Time|Q タイム"),
    ("lot_hold", "Lot not on hold|批次未 Hold|ロット非ホールド"),
    ("wo_status", "Work order status|工单状态|作業指示状態"),
    ("dc_complete", "DC completeness|数据收集完整|データ収集完了"),
    ("oos", "Out of spec|超规|規格外"),
    ("sampling", "Sampling decision|抽样判定|サンプリング判定"),
    ("split_merge_rule", "Split / merge rule|分批合批规则|分割・統合規則"),
    ("recipe_match", "Recipe ↔ equipment mapping|配方设备映射|レシピ・設備対応"),
    ("pm_due", "Equipment PM not overdue|设备 PM 未超期|設備 PM 期限内"),
    ("rework_limit", "Rework count limit|返工次数上限|リワーク回数上限"),
    (
        "qty_adjust_limit",
        "Scrap / bonus qty limit|报废 / 补数数量上限|廃棄・追加数量上限",
    ),
]
ENUMS.update(
    {
        "exec_trigger": TRIGGERS,
        "check_type": list(CHECK_TYPES),
        "check_severity": [
            ("block", "Block|拦截|ブロック"),
            ("warn", "Warn|预警|警告"),
            ("off", "Off (control disabled)|关闭（不管控）|無効（管控なし）"),
        ],
        "check_result": [
            ("pass", "Pass|通过|合格"),
            ("warn", "Warn|预警|警告"),
            ("block", "Block|拦截|ブロック"),
            ("overridden", "Overridden|强制放行|強制解除"),
        ],
        "check_scope": [
            ("route_step", "Route step|流程步骤|ルートステップ"),
            ("equipment", "Equipment|设备|設備"),
            ("operation", "Operation|工序|工程"),
            ("equipment_type", "Equipment type|设备类型|設備タイプ"),
            ("product", "Product|产品|製品"),
        ],
        "ml_status": [
            ("available", "Available|可用|使用可"),
            ("hold", "On hold|冻结|保留"),
            ("empty", "Used up|已用完|使用済"),
            ("expired", "Expired|已过期|期限切れ"),
        ],
        "tool_status": [
            ("available", "Available|可用|使用可"),
            ("in_use", "In use|使用中|使用中"),
            ("pending_maintenance", "Pending maintenance|待保养|保全待ち"),
            ("expired", "Expired|已过期|期限切れ"),
            ("retired", "Retired|已报废|廃棄"),
        ],
        "e10_trigger": [
            ("track_in", "Track in|上机|トラックイン"),
            (
                "track_out",
                "Track out (no other running lots)|下机（无其他加工批次）|トラックアウト（他の処理ロットなし）",
            ),
        ],
        "hold_type": [
            ("manual", "Manual|手动|手動"),
            ("auto", "Automatic|自动|自動"),
            ("future", "Future hold|预约 Hold|予約ホールド"),
        ],
        "shift_log_status": [
            ("open", "Awaiting handover|待接班|引継ぎ待ち"),
            ("acknowledged", "Acknowledged|已接班|引継ぎ済"),
        ],
        "fh_status": [
            ("active", "Waiting|待触发|待機中"),
            ("triggered", "Triggered|已触发|発動済"),
            ("cancelled", "Cancelled|已取消|取消"),
        ],
        "history_action": [
            ("start", "Lot start|投产|投入"),
            ("move_in", "Move in|进站|ムーブイン"),
            ("track_in", "Track in|上机|トラックイン"),
            ("track_out", "Track out|下机|トラックアウト"),
            ("move_out", "Move out|出站|ムーブアウト"),
            ("hold", "Hold|Hold|ホールド"),
            ("release", "Release|解除 Hold|ホールド解除"),
            ("scrap", "Scrap|报废|スクラップ"),
            ("rework", "Rework|返工|リワーク"),
            ("branch", "Branch|分支|分岐"),
            ("sub_route", "Enter sub-route|进入子流程|サブルート開始"),
            (
                "return",
                "Return from sub/rework route|子流程/返工返回|サブ・リワーク復帰",
            ),
            ("complete", "Finished (to receive)|完工待入库|完了（入庫待ち）"),
            ("receive", "Received|入库|入庫"),
            ("override", "Check override|卡控放行|チェック強制解除"),
            ("qtime", "Q-Time violation|Q-Time 超时|Q タイム違反"),
            ("oos", "Out of spec|超规|規格外"),
            ("split", "Split|分批|分割"),
            ("merge", "Merge|合批|統合"),
            ("jump", "Jump step|跳站|ステップジャンプ"),
            ("bonus", "Bonus|补数|追加"),
            ("carrier_change", "Carrier change|换载具|キャリア変更"),
            ("sort", "Wafer sort|晶圆整理|ウェーハソート"),
            ("priority", "Priority change|优先级变更|優先度変更"),
        ],
        "genealogy_relation": [
            ("split", "Split|分批|分割"),
            ("merge", "Merge|合批|統合"),
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


FIELD_LABELS.setdefault("route_step", "Route step|流程步骤|ルートステップ")

register(
    # ---------------- checks ----------------
    Entity(
        "check_rule",
        "check",
        "Check rule|卡控规则|チェックルール",
        [
            F(
                "check_type",
                "enum",
                "Check type|卡控类型|チェック種別",
                required=True,
                enum="check_type",
            ),
            F(
                "severity",
                "enum",
                "Severity|严重度|重大度",
                required=True,
                enum="check_severity",
                default="block",
            ),
            F(
                "params",
                "json",
                "Parameters (JSON)|参数（JSON）|パラメータ（JSON）",
                list=False,
                help='e.g. {"allowed": ["SBY", "PRD"]} for E10; {"days": 7} for warn ahead|'
                '例如 E10 用 {"allowed": ["SBY", "PRD"]}|例：E10 は {"allowed": ["SBY", "PRD"]}',
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
        "Check plan|卡控方案|チェックプラン",
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
        "Plan rule|方案规则|プランルール",
        [
            F(
                "check_plan",
                "ref",
                "Check plan|卡控方案|チェックプラン",
                required=True,
                ref="check_plan",
                cascade=True,
            ),
            F(
                "check_rule",
                "ref",
                "Check rule|卡控规则|チェックルール",
                required=True,
                ref="check_rule",
            ),
            F("seq", "int", "Seq.|序号|順番", default=10),
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
        "Check binding|卡控绑定|チェック割当",
        [
            F(
                "check_plan",
                "ref",
                "Check plan|卡控方案|チェックプラン",
                required=True,
                ref="check_plan",
            ),
            F(
                "trigger",
                "enum",
                "Trigger|触发时机|トリガー",
                required=True,
                enum="exec_trigger",
            ),
            F(
                "scope",
                "enum",
                "Scope|范围|スコープ",
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
        "Check log|卡控记录|チェック記録",
        [
            F("lot", "ref", "Lot|批次|ロット", ref="lot", cascade=True),
            F("trigger", "enum", "Trigger|触发时机|トリガー", enum="exec_trigger"),
            F("route_step", "ref", ref="route_step", list=False, filter=False),
            F("equipment", "ref", ref="equipment"),
            F(
                "check_rule",
                "ref",
                "Check rule|卡控规则|チェックルール",
                ref="check_rule",
            ),
            F(
                "check_plan",
                "ref",
                "Check plan|卡控方案|チェックプラン",
                ref="check_plan",
                list=False,
            ),
            F(
                "check_type",
                "enum",
                "Check type|卡控类型|チェック種別",
                enum="check_type",
            ),
            F(
                "severity",
                "enum",
                "Severity|严重度|重大度",
                enum="check_severity",
                list=False,
            ),
            F("result", "enum", "Result|结果|結果", enum="check_result"),
            F("message", "str", "Message|信息|メッセージ", max_length=500, search=True),
            F("context", "json", "Context|上下文|コンテキスト", list=False),
            F(
                "override_reason",
                "str",
                "Override reason|放行原因|強制解除理由",
                max_length=300,
                list=False,
            ),
            F("username", "str", "User|用户|ユーザー", max_length=255, search=True),
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
        "Future hold|预约 Hold|予約ホールド",
        [
            F("lot", "ref", "Lot|批次|ロット", required=True, ref="lot", cascade=True),
            F(
                "route_step",
                "ref",
                "Hold at step|Hold 工步|ホールド工程",
                required=True,
                ref="route_step",
            ),
            F(
                "reason",
                "ref",
                "Reason code|原因代码|理由コード",
                ref="reason_code",
                help="Blank: default hold reason|留空则使用默认 Hold 原因|空欄：既定のホールド理由",
            ),
            F("comment", "str", "Comment|备注|コメント", max_length=300, search=True),
            F(
                "fh_status",
                "enum",
                "Status|状态|状態",
                enum="fh_status",
                system=True,
                default="active",
            ),
            F(
                "triggered_at",
                "datetime",
                "Triggered at|触发时间|発動日時",
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
        "Shift handover|交接班日志|シフト引継ぎ",
        [
            F("shift_date", "date", "Date|日期|日付", required=True),
            F("shift", "ref", "Shift|班次|シフト", ref="shift", required=True),
            F("area", "ref", ref="area"),
            F("summary", "text", "Handover notes|交接事项|引継ぎ事項", search=True),
            F("open_items", "text", "Open items|未结事项|未完了事項", search=True),
            F("handed_by", "str", "Handed over by|交班人|引継ぎ者"),
            F("handed_at", "datetime", "Handed over at|交班时间|引継ぎ日時"),
            F(
                "log_status",
                "enum",
                "Status|状态|状態",
                enum="shift_log_status",
                default="open",
            ),
            F("received_by", "str", "Received by|接班人|受領者"),
            F("received_at", "datetime", "Received at|接班时间|受領日時"),
            F(
                "receive_comment",
                "str",
                "Receiver note|接班备注|受領メモ",
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
        "Operator qualification|操作员资质|作業者資格",
        [
            F("username", "str", "User|用户|ユーザー", required=True, search=True),
            F("operation", "ref", ref="operation", required=True),
            F(
                "equipment_type",
                "ref",
                "Equipment type|设备类型|設備タイプ",
                ref="equipment_type",
                help="Blank: any equipment type|留空则适用全部设备类型|空欄：全設備タイプ",
            ),
            F("certified_on", "date", "Certified on|认证日期|認定日"),
            F("expires_on", "date", "Expires on|有效期至|有効期限"),
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
