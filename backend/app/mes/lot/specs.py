"""批次实体规格：批次、晶圆、批次规则、Hold、历史、谱系。"""

from app.core.spec.engine import ENUMS, Entity, F, register

register(
    # ---------------- customer (B7) ----------------
    Entity(
        "customer",
        "lot",
        "Customer|客户|顧客",
        [
            F("short_name", "str", "Short name|简称|略称", max_length=50, search=True),
        ],
        phase=4,
        icon="Building2",
        order=0,
    ),
)

CUSTOMER_FIELDS = [
    F(
        "customer_lot_no",
        "str",
        "Customer lot no.|客户批号|顧客ロット番号",
        max_length=100,
        search_exact=True,  # D37：不区分大小写的精确匹配
    ),
    F(
        "ownership",
        "enum",
        "Ownership|物料归属|所有区分",
        enum="ownership",
        default="own",
        list=False,
    ),
    F("customer", "ref", "Customer|客户|顧客", ref="customer", list=False),
]

register(
    # ---------------- lot / wafer rules ----------------
    Entity(
        "lot_priority",
        "lot",
        "Lot priority|批次优先级|ロット優先度",
        [
            F(
                "level",
                "int",
                "Level (1 = highest)|级别（1 = 最高）|レベル（1 = 最高）",
                required=True,
            ),
            F("color", "str", max_length=20),
            F("is_hot", "bool", "Hot lot|紧急批|ホットロット", default=False),
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
        "Lot type|批次类型|ロットタイプ",
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
                "Default priority|默认优先级|既定優先度",
                ref="lot_priority",
                required=True,
            ),
            F(
                "lot_id_rule",
                "ref",
                "Lot ID rule|批次号规则|ロット ID ルール",
                ref="code_rule",
                required=True,
            ),
            F(
                "wafer_id_rule",
                "ref",
                "Wafer ID rule|晶圆号规则|ウェーハ ID ルール",
                ref="code_rule",
                required=True,
            ),
            F(
                "max_wafers",
                "int",
                "Max wafers / units per lot|每批最大片数/数量|ロット最大枚数・数量",
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
        "Split / merge rule|分批合批规则|分割・統合規則",
        [
            F(
                "lot_type",
                "ref",
                "Lot type|批次类型|ロットタイプ",
                ref="lot_type",
                required=True,
            ),
            F(
                "allow_split",
                "bool",
                "Allow split|允许分批|分割可",
                default=True,
                filter=False,
            ),
            F(
                "max_children",
                "int",
                "Max child lots|最大子批数|最大子ロット数",
                default=5,
            ),
            F(
                "min_wafers",
                "int",
                "Min wafers per lot|每批最少片数|ロット最少枚数",
                default=1,
            ),
            F(
                "child_id_mode",
                "enum",
                "Child lot no.|子批号生成|子ロット番号",
                enum="child_id_mode",
                default="suffix",
                list=False,
            ),
            F(
                "allow_merge",
                "bool",
                "Allow merge|允许合批|統合可",
                default=True,
                filter=False,
            ),
            F(
                "merge_same_wo",
                "bool",
                "Merge: same work order|合批：同工单|統合：同一作業指示",
                default=True,
                filter=False,
                list=False,
            ),
            F(
                "merge_same_product",
                "bool",
                "Merge: same product|合批：同产品|統合：同一製品",
                default=True,
                filter=False,
            ),
            F(
                "merge_same_step",
                "bool",
                "Merge: same route step|合批：同流程步骤|統合：同一ステップ",
                default=True,
                filter=False,
            ),
            F(
                "merge_same_priority",
                "bool",
                "Merge: same priority required|合批：要求同优先级（否则取最高）|統合：同一優先度必須（否則最高を採用）",
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
        "Q-Time rule|Q-Time 规则|Q-Time ルール",
        [
            F("route", "ref", required=True, ref="route"),
            F(
                "from_step",
                "ref",
                "From step|起始步骤|開始ステップ",
                required=True,
                ref="route_step",
                depends="route",
            ),
            F(
                "to_step",
                "ref",
                "To step|结束步骤|終了ステップ",
                required=True,
                ref="route_step",
                depends="route",
            ),
            F("product", "ref", ref="product", list=False),
            F("min_minutes", "int", "Min (min)|最短（分钟）|最短（分）"),
            F("max_minutes", "int", "Max (min)|最长（分钟）|最長（分）"),
            F(
                "warn_minutes",
                "int",
                "Warn at (min)|预警阈值（分钟）|事前警告（分）",
                help="Pre-expiry warning when elapsed ≥ this (blank: none)|已用时间达到该值即预警（留空不预警）|経過がこの値以上で事前警告（空欄：なし）",
                list=False,
            ),
            F(
                "action",
                "enum",
                "On violation|超时动作|違反時処置",
                required=True,
                enum="qtime_action",
                default="hold",
            ),
            F(
                "reason",
                "ref",
                "Reason code|原因代码|理由コード",
                ref="reason_code",
                list=False,
                # D25 / D26：原因码选填，hold 留空时用系统原因码 qtime_expired
                help="Optional; for hold, blank uses system reason qtime_expired"
                "|选填；处置为 hold 时留空使用系统原因码 qtime_expired"
                "|任意。hold で空欄の場合はシステム理由 qtime_expired（Q-Time 超過）を使用",
            ),
            # D24/D25：被引用的规则不能删，改为停用（停用后不计时、不处置）
            F("is_active", "bool", default=True),
            F(
                "active_since",
                "datetime",
                "Active since|启用时间|有効化日時",
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
        "ownership": [
            ("own", "Own|自有|自社"),
            ("customer", "Customer-owned|客户来料|顧客支給"),
        ],
        "wo_status": [
            ("draft", "Draft|草稿|下書き"),
            ("released", "Released|已下达|リリース済"),
            ("in_progress", "In progress|生产中|生産中"),
            ("on_hold", "On hold|暂停|保留中"),
            ("completed", "Completed|已完工|完了"),
            ("closed", "Closed|已关闭|クローズ"),
            ("cancelled", "Cancelled|已取消|取消"),
        ],
        "lot_status": [
            ("waiting", "Waiting|等待|待機"),
            ("moved_in", "Moved in|已进站|ムーブイン済"),
            ("running", "Running|加工中|処理中"),
            ("tracked_out", "Tracked out|已下机|トラックアウト済"),
            ("completed", "Finished (to receive)|待入库|入庫待ち"),
            ("stored", "Stored|已入库|入庫済"),
            ("scrapped", "Scrapped|已报废|廃棄"),
            ("merged", "Merged (terminated)|已合批（终止）|統合済（終了）"),
            ("converted", "Converted (terminated)|已转换（终止）|変換済（終了）"),
        ],
        "wafer_status": [
            ("waiting", "Waiting|等待|待機"),
            ("processing", "Processing|加工中|処理中"),
            ("rework", "Rework|返工|リワーク"),
            ("completed", "Completed|已完成|完了"),
            ("scrapped", "Scrapped|已报废|廃棄"),
            ("converted", "Converted|已转换|変換済"),
        ],
        "track_unit_kind": [
            ("wafer", "Wafer|晶圆|ウェーハ"),
            ("strip", "Strip|条|ストリップ"),
            ("die", "Die|晶粒|ダイ"),
            ("package", "Package|封装体|パッケージ"),
            ("unit", "Unit|单元|ユニット"),
        ],
    }
)


register(
    Entity(
        "lot",
        "wo",
        "Lot|批次|ロット",
        [
            F(
                "work_order",
                "ref",
                "Work order|工单|作業指示",
                ref="work_order",
                required=True,
            ),
            F("product", "ref", ref="product", required=True),
            F("route", "ref", ref="route", required=True, filter=False, list=False),
            F(
                "lot_type",
                "ref",
                "Lot type|批次类型|ロットタイプ",
                ref="lot_type",
                required=True,
                list=False,
            ),
            F(
                "priority",
                "ref",
                "Priority|优先级|優先度",
                ref="lot_priority",
                list=False,
            ),
            F("qty", "int", "Qty|数量|数量", required=True),
            F(
                "tracking_level",
                "enum",
                "Tracking level|追踪层级|追跡レベル",
                enum="tracking_level",
                default="wafer",
                list=False,
            ),
            F("scrapped_qty", "int", "Scrapped|报废数|廃棄数", default=0, list=False),
            F("bonus_qty", "int", "Bonus|补数|追加数", default=0, list=False),
            F(
                "rework_count",
                "int",
                "Reworks|返工次数|リワーク回数",
                default=0,
                list=False,
            ),
            F("site", "ref", ref="site"),
            # B8：按 bin 拆出的子批所属 bin（多个 bin 合成一个子批时用逗号连接）
            F("bin_code", "str", "Bin|bin 码|ビン", max_length=64, search_exact=True),
            F(
                "current_step",
                "ref",
                "Current step|当前步骤|現在ステップ",
                ref="route_step",
                filter=False,
            ),
            F(
                "lot_status",
                "enum",
                "Status|状态|状態",
                enum="lot_status",
                default="waiting",
            ),
            F("on_hold", "bool", "On hold|Hold 中|ホールド中", default=False),
            F("equipment", "ref", "Equipment|设备|設備", ref="equipment", list=False),
            F("recipe", "ref", "Recipe|配方|レシピ", ref="recipe", list=False),
            F(
                "step_in_at",
                "datetime",
                "Arrived at step|到站时间|ステップ到着",
                list=False,
            ),
            F("stage_at", "datetime", "Last action at|最近操作|最終操作", list=False),
            F(
                "pending_rework",
                "bool",
                "Rework pending|待返工|リワーク待ち",
                default=False,
                list=False,
            ),
            F("route_stack", "json", "Route stack|流程栈|ルートスタック", list=False),
            F(
                "exec_ctx",
                "json",
                "Execution context|作业上下文|実行コンテキスト",
                list=False,
            ),
            F("completed_at", "datetime", "Completed at|完成时间|完了日時", list=False),
            F(
                "received_qty",
                "int",
                "Received qty (good + scrap)|已入库数（良品 + 报废）|入庫済数（良品 + 廃棄）",
                default=0,
                list=False,
            ),
            F(
                "stored_at",
                "datetime",
                "Stored at|入库完成时间|入庫完了日時",
                list=False,
            ),
            F("carrier", "ref", "Carrier|载具|キャリア", ref="carrier"),
            F(
                "source_ref",
                "str",
                "Source wafer / material batch|来源晶圆 / 物料批次|元ウェーハ・資材ロット",
                search=True,
            ),
            F("started_at", "datetime", "Started at|投产时间|投入日時"),
            F("started_by", "str", "Started by|投产人|投入者", list=False),
            F(
                "bom",
                "ref",
                "BOM version|BOM 版本|BOM 版",
                ref="bom",
                list=False,
                filter=False,
                help="Locked at lot start (D28); blank = no active BOM then|开批时锁定（D28），为空表示当时没有生效的 BOM|投入時に固定（D28）、空欄は当時有効な BOM なし",
            ),
            *CUSTOMER_FIELDS,  # B7：开批时填写，拆批 / 合批 / 单位转换的子批继承
        ],
        phase=5,
        icon="Layers",
        order=10,
        has_name=False,
        code_label="Lot no.|批次号|ロット番号",
        readonly=True,
        perm_module="lot",
        sort_default="created_at",
        children=["wafer"],
        indexes=[("ix_mes_lot_customer_lot_no", ("upper:customer_lot_no",))],  # D36/D37
    ),
)


register(
    Entity(
        "wafer",
        "wo",
        "Wafer / unit|晶圆 / 单元|ウェーハ・ユニット",
        [
            F("lot", "ref", "Lot|批次|ロット", ref="lot", required=True, cascade=True),
            F(
                "unit_kind",
                "enum",
                "Unit kind|单元类型|ユニット種別",
                enum="track_unit_kind",
                required=True,
                default="wafer",
            ),
            F(
                "slot",
                "int",
                "Slot|槽位|スロット",
                required_when={"unit_kind": ("wafer",)},
            ),
            F(
                "wafer_status",
                "enum",
                "Status|状态|状態",
                enum="wafer_status",
                default="waiting",
            ),
            F("source_ref", "str", "Source wafer|来源晶圆|元ウェーハ", search=True),
            F(
                "scrap_reason",
                "ref",
                "Scrap reason|报废原因|廃棄理由",
                ref="reason_code",
                list=False,
            ),
            F(
                "rework_count",
                "int",
                "Rework count|返工次数|リワーク回数",
                default=0,
                list=False,
            ),
        ],
        phase=5,
        icon="Disc",
        order=20,
        has_name=False,
        code_label="Wafer ID|晶圆号|ウェーハ ID",
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
        "Lot hold|批次 Hold|ロットホールド",
        [
            F("lot", "ref", "Lot|批次|ロット", required=True, ref="lot", cascade=True),
            F(
                "reason",
                "ref",
                "Reason code|原因代码|理由コード",
                required=True,
                ref="reason_code",
            ),
            F(
                "hold_type",
                "enum",
                "Hold type|Hold 类型|ホールド種別",
                enum="hold_type",
                default="manual",
            ),
            F("source", "str", "Source|来源|発生元", max_length=40),
            F("comment", "str", "Comment|备注|コメント", max_length=300, search=True),
            F("is_active", "bool", "Active|生效中|有効", default=True),
            F("held_at", "datetime", "Held at|Hold 时间|ホールド日時"),
            F("held_by", "str", "Held by|Hold 人|ホールド者"),
            F("route_step", "ref", ref="route_step", list=False, filter=False),
            # D20：Q-Time 自动 Hold 附加信息（手动 Hold / 旧记录为空）
            F(
                "qtime_rule",
                "ref",
                "Q-Time rule|Q-Time 规则|Q-Time ルール",
                ref="qtime_rule",
                list=False,
                filter=False,
            ),
            F(
                "qtime_from_step",
                "ref",
                "Q-Time from step|Q-Time 起始工步|Q-Time 開始ステップ",
                ref="route_step",
                list=False,
                filter=False,
            ),
            F(
                "qtime_to_step",
                "ref",
                "Q-Time to step|Q-Time 终点工步|Q-Time 終了ステップ",
                ref="route_step",
                list=False,
                filter=False,
            ),
            F(
                "qtime_overdue_seconds",
                "int",
                "Q-Time overdue (s)|Q-Time 超时秒数|Q-Time 超過秒",
                list=False,
            ),
            F("released_at", "datetime", "Released at|解除时间|解除日時"),
            F("released_by", "str", "Released by|解除人|解除者", list=False),
            F(
                "release_reason",
                "ref",
                "Release reason|解除原因|解除理由",
                ref="reason_code",
                list=False,
            ),
            F(
                "release_comment",
                "str",
                "Release comment|解除备注|解除コメント",
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
        "Lot history|批次履历|ロット履歴",
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
            F("action", "enum", "Action|操作|操作", enum="history_action"),
            F("route_step", "ref", ref="route_step", list=False, filter=False),
            F("step_seq", "int", "Seq.|序号|順番"),
            F("operation", "ref", ref="operation"),
            F("equipment", "ref", "Equipment|设备|設備", ref="equipment"),
            F("recipe", "ref", "Recipe|配方|レシピ", ref="recipe", list=False),
            F("qty", "int", "Qty|数量|数量"),
            F(
                "from_status",
                "enum",
                "From|原状态|変更前",
                enum="lot_status",
                list=False,
            ),
            F("to_status", "enum", "To|新状态|変更後", enum="lot_status"),
            F(
                "reason",
                "ref",
                "Reason code|原因代码|理由コード",
                ref="reason_code",
                list=False,
            ),
            F(
                "comment",
                "str",
                "Comment|备注|コメント",
                max_length=300,
                search=True,
                list=False,
            ),
            F("details", "json", "Details|详情|詳細", list=False),
            F("username", "str", "User|用户|ユーザー", max_length=255, search=True),
            F("at", "datetime", "Time|时间|日時"),
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
        "Recipe run|配方执行记录|レシピ実行記録",
        [
            F("lot", "ref", "Lot|批次|ロット", required=True, ref="lot", cascade=True),
            F("route_step", "ref", ref="route_step", list=False, filter=False),
            F("operation", "ref", ref="operation"),
            F("equipment", "ref", "Equipment|设备|設備", ref="equipment"),
            F("recipe", "ref", "Recipe|配方|レシピ", ref="recipe"),
            F("recipe_version", "int", "Recipe version|配方版本|レシピ版数"),
            F(
                "eqp_recipe",
                "str",
                "Equipment recipe|设备端配方|装置レシピ",
                max_length=200,
                search=True,
            ),
            F(
                "chambers",
                "str",
                "Chambers|腔体|チャンバー",
                max_length=300,
                list=False,
            ),
            F("params", "json", "Parameters|参数|パラメータ", list=False),
            F(
                "param_specs",
                "json",
                "Parameter specs|参数规格|パラメータ規格",
                list=False,
            ),
            F("qty", "int", "Qty|数量|数量"),
            F("track_in_at", "datetime", "Track in|上机时间|着工日時"),
            F("track_out_at", "datetime", "Track out|下机时间|完了日時"),
            F("username", "str", "User|用户|ユーザー", max_length=255, search=True),
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
        "lot_genealogy",
        "exec",
        "Lot genealogy|批次谱系|ロット系譜",
        [
            F(
                "parent_lot",
                "ref",
                "Parent / source lot|母批 / 来源批|親・元ロット",
                required=True,
                ref="lot",
                cascade=True,
            ),
            F(
                "child_lot",
                "ref",
                "Child / target lot|子批 / 目标批|子・統合先ロット",
                required=True,
                ref="lot",
                cascade=True,
            ),
            F("relation", "enum", "Relation|关系|関係", enum="genealogy_relation"),
            F("qty", "int", "Qty|数量|数量"),
            F(
                "units",
                "json",
                "Wafers / units|晶圆 / 单元|ウェーハ・ユニット",
                list=False,
            ),
            F("route_step", "ref", ref="route_step", list=False, filter=False),
            F("username", "str", "User|用户|ユーザー", max_length=255, search=True),
            F("at", "datetime", "Time|时间|日時"),
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


ENUMS.update(
    {
        "consumption_source": [
            ("step_resource", "Step resource|工步资源|ステップ資源"),
            ("manual", "Manual|人工|手動"),
            ("eap", "EAP|EAP|EAP"),
        ],
        "usage_type": [
            ("normal", "Normal|正常|通常"),
            ("rework", "Rework|返工|リワーク"),
            ("scrap", "Scrap|报废|スクラップ"),
        ],
    }
)


register(
    # 用料记录（D28 / B2）：Track Out 扣料逐条记录；BOM 出站比对只累计 usage_type=normal
    Entity(
        "material_consumption",
        "exec",
        "Material consumption|用料记录|資材使用記録",
        [
            F("lot", "ref", "Lot|批次|ロット", required=True, ref="lot", cascade=True),
            F("route_step", "ref", ref="route_step", list=False, filter=False),
            F("operation", "ref", ref="operation"),
            F("material", "ref", "Material|物料|資材", ref="material"),
            F(
                "material_lot",
                "ref",
                "Material lot|物料批|資材ロット",
                ref="material_lot",
            ),
            F("qty", "float", "Qty|用量|使用量", scale=6),
            F("uom", "ref", "UOM|单位|単位", ref="uom"),
            F(
                "source",
                "enum",
                "Source|来源|ソース",
                enum="consumption_source",
                default="step_resource",
            ),
            F(
                "usage_type",
                "enum",
                "Usage type|用途|用途",
                enum="usage_type",
                default="normal",
            ),
            F(
                "external_event_id",
                "str",
                "External event ID|外部事件号|外部イベント ID",
                max_length=128,
                list=False,
            ),
            F("username", "str", "User|用户|ユーザー", max_length=255, search=True),
            F("at", "datetime", "Time|时间|日時"),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        icon="PackageOpen",
        order=4,
        menu=False,
        # 外部上报（EAP / 人工）去重：同一来源同一事件号只记一次
        partial_unique=[
            (
                "uq_mes_mat_consumption_event",
                ("source", "external_event_id"),
                "external_event_id IS NOT NULL",
            ),
        ],
        sort_default="at",
        label_field="qty",
    ),
)


# ---------------- 单位转换与谱系（B5，bom.md §7.5 / §10） ----------------
register(
    Entity(
        "unit_transform",
        "lot",
        "Unit transform|单位转换|単位変換",
        [
            F(
                "transform_type",
                "enum",
                "Type|类型|種別",
                enum="transform_type",
                required=True,
            ),
            F("route_step", "ref", ref="route_step", list=False, filter=False),
            F("reason", "ref", "Reason|原因|理由", ref="reason_code", list=False),
            F("comment", "str", "Comment|备注|コメント", max_length=300, list=False),
            F("warnings", "json", "Warnings|提示|警告", list=False),
            F("username", "str", "User|用户|ユーザー", max_length=255, search=True),
            F("at", "datetime", "Time|时间|日時"),
            # 预留给 EAP 上报（本期人工接口固定 manual / 空）
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
        menu=False,
        partial_unique=[
            (
                "uq_mes_unit_transform_event",
                ("source", "external_event_id"),
                "external_event_id IS NOT NULL",
            ),
        ],
        sort_default="at",
        label_field="transform_type",
        children=["unit_transform_input", "unit_transform_output"],
    ),
    Entity(
        "unit_transform_input",
        "lot",
        "Transform input|转换输入|変換入力",
        [
            F(
                "unit_transform",
                "ref",
                "Transform|转换|変換",
                ref="unit_transform",
                required=True,
                cascade=True,
            ),
            F("lot", "ref", "Lot|批次|ロット", ref="lot", required=True),
            F("wafer", "ref", "Wafer|晶圆|ウェーハ", ref="wafer"),
            F("substrate_map", "ref", "Map|坐标图|座標マップ", ref="substrate_map"),
            F("qty_before", "int", "Qty before|转换前数量|変換前数量"),
            F("good_qty", "int", "Good|良品数|良品数"),
            F("fail_qty", "int", "Fail|不良数|不良数"),
            F("excluded_qty", "int", "Excluded|排除数|除外数"),
            F(
                "good_source",
                "enum",
                "Good qty from|良品数来源|良品数の出所",
                enum="good_source",
            ),
            # B8：所用坐标图的 bin 定义集与版本、各 bin 数量
            F("bin_set", "ref", "Bin set|定义集|定義セット", ref="bin_set"),
            F("bin_set_version", "int", "Bin set version|定义集版本|定義セット版"),
            F("bin_counts", "json", "Bin counts|各 bin 数量|ビン別数量", list=False),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        menu=False,
        parent="unit_transform",
        sort_default="created_at",
        label_field="good_qty",
    ),
    Entity(
        "unit_transform_output",
        "lot",
        "Transform output|转换输出|変換出力",
        [
            F(
                "unit_transform",
                "ref",
                "Transform|转换|変換",
                ref="unit_transform",
                required=True,
                cascade=True,
            ),
            F("lot", "ref", "Lot|批次|ロット", ref="lot", required=True),
            F("product", "ref", ref="product", required=True),
            F(
                "track_unit_kind",
                "enum",
                "Unit kind|单元类型|ユニット種別",
                enum="track_unit_kind",
                required=True,
            ),
            F("qty", "int", "Qty|数量|数量", required=True),
            F("die_qty", "int", "Dies|颗数|ダイ数"),
            F("bin_code", "str", "Bin|bin 码|ビン", max_length=64),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        menu=False,
        parent="unit_transform",
        sort_default="created_at",
        label_field="qty",
    ),
    Entity(
        "unit_origin",
        "lot",
        "Unit origin|单元来源|ユニット由来",
        [
            F(
                "unit_transform",
                "ref",
                "Transform|转换|変換",
                ref="unit_transform",
                required=True,
                cascade=True,
            ),
            F("child_lot", "ref", "Child lot|子批|子ロット", ref="lot", required=True),
            F(
                "child_unit",
                "ref",
                "Child unit (strip)|子单元（条）|子ユニット（ストリップ）",
                ref="wafer",
            ),
            F("child_seq", "int", "Position / seq|子位置 / 颗序号|位置・連番"),
            F(
                "parent_lot",
                "ref",
                "Parent lot|母批|親ロット",
                ref="lot",
                required=True,
            ),
            F("parent_wafer", "ref", "Parent wafer|母晶圆|親ウェーハ", ref="wafer"),
            F("die_row", "int", "Die row|die 行|ダイ行"),
            F("die_col", "int", "Die col|die 列|ダイ列"),
            F("qty", "int", "Qty|数量|数量", required=True, default=1),
            F("bin_code", "str", "Bin|bin 码|ビン", max_length=64),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        menu=False,
        sort_default="child_seq",
        label_field="child_seq",
    ),
)

ENUMS.update(
    {
        "transform_type": [
            ("dicing", "Dicing|划片|ダイシング"),
            ("die_attach", "Die attach|粘片|ダイアタッチ"),
            ("singulation", "Singulation|切单|個片化"),
            ("bin_split", "Bin split|按 bin 拆批|ビン分割"),
        ],
        "good_source": [
            ("map", "Substrate map|坐标图|座標マップ"),
            ("gross_die", "Product gross die|产品总晶粒数|製品総ダイ数"),
            ("manual", "Manual (reason)|人工录入（原因码）|手入力（理由）"),
        ],
    }
)
