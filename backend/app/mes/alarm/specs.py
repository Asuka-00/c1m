"""报警实体规格（P2-B9，eap/p2/alarm-code-model.md 定稿 + D53）。

- ``alarm_code``：报警码主数据，按设备类型定义（可按单台设备覆盖），通用 CRUD；
- ``alarm_log``：报警履历（只读，写入只走 ``/mes/eqp/{eq_id}/alarms`` 与 EAP 入口）；
  未登记 ALID 也记录，``unregistered=true``，不联动（D53-2）；原始上报存 ``raw``；
- ``alarm_lot``：报警关联批次子表（发生时在该设备上 moved_in / running 的批次 + 上报带的批次）。
"""

from app.core.spec.engine import ENUMS, Entity, F, register

register(
    Entity(
        "alarm_code",
        "alarm",
        "Alarm code|报警码|アラームコード",
        [
            F(
                "equipment_type",
                "ref",
                "Equipment type|设备类型|設備タイプ",
                ref="equipment_type",
                required=True,
            ),
            F(
                "equipment",
                "ref",
                "Equipment (override)|设备（单台覆盖）|設備（個別上書き）",
                ref="equipment",
            ),
            F(
                "alid",
                "str",
                "ALID|ALID|ALID",
                max_length=32,
                required=True,
                search=True,
            ),
            F("alcd_category", "int", "ALCD category|ALCD 分类|ALCD 分類", default=0),
            F(
                "severity",
                "enum",
                "Severity|等级|重大度",
                enum="alarm_severity",
                required=True,
                default="warning",
            ),
            F("text_en", "str", "Text (EN)|文本（英）|テキスト（英）", max_length=300),
            F(
                "text_zh",
                "str",
                "Text (ZH)|文本（中）|テキスト（中）",
                max_length=300,
                search=True,
            ),
            F("text_ja", "str", "Text (JA)|文本（日）|テキスト（日）", max_length=300),
            F(
                "category",
                "enum",
                "Category|分类|分類",
                enum="alarm_category",
                default="other",
            ),
            F(
                "action",
                "enum",
                "Action|联动|連動",
                enum="alarm_action",
                required=True,
                default="none",
            ),
            F(
                "target_e10_state",
                "ref",
                "Target E10 state|目标 E10 状态|遷移先 E10 状態",
                ref="e10_state",
                required_when={"action": ("hold_equipment", "hold_both")},
            ),
            F(
                "hold_reason",
                "ref",
                "Hold reason|Hold 原因|ホールド理由",
                ref="reason_code",
                list=False,
                help="Blank: system reason equipment_alarm"
                "|留空使用系统原因码 equipment_alarm"
                "|空欄：システム理由 equipment_alarm",
            ),
            F(
                "require_qual_on_clear",
                "bool",
                "Qual after clear|清除后需 Qual|解除後 Qual 必要",
                default=False,
                list=False,
            ),
            F("disposition", "text", "Disposition|处置说明|処置", list=False),
            F("is_active", "bool", default=True),
        ],
        phase=6,
        has_code=False,
        partial_unique=[
            (
                "uq_mes_alarm_code_type",
                ("equipment_type_id", "alid"),
                "equipment_id IS NULL",
            ),
            (
                "uq_mes_alarm_code_eqp",
                ("equipment_id", "alid"),
                "equipment_id IS NOT NULL",
            ),
        ],
        icon="Siren",
        order=30,
        sort_default="alid",
        label_field="alid",
    ),
    Entity(
        "alarm_log",
        "alarm",
        "Alarm log|报警履历|アラーム履歴",
        [
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
            F(
                "alarm_code",
                "ref",
                "Alarm code|报警码|アラームコード",
                ref="alarm_code",
            ),
            F("unregistered", "bool", "Unregistered|未登记|未登録", default=False),
            F(
                "alid",
                "str",
                "ALID|ALID|ALID",
                max_length=32,
                required=True,
                search=True,
            ),
            F("alcd_raw", "int", "ALCD (raw)|ALCD 原值|ALCD（生値）", list=False),
            F(
                "alarm_text",
                "str",
                "Text|报警文本|テキスト",
                max_length=300,
                search=True,
            ),
            F("severity", "enum", "Severity|等级|重大度", enum="alarm_severity"),
            F("action", "enum", "Action|联动|連動", enum="alarm_action"),
            F(
                "alarm_status",
                "enum",
                "Status|状态|状態",
                enum="alarm_status",
                required=True,
                default="active",
            ),
            F("set_at", "datetime", "Set at|发生时间|発生日時", required=True),
            F("cleared_at", "datetime", "Cleared at|清除时间|解除日時"),
            F(
                "cleared_by",
                "str",
                "Cleared by|清除人|解除者",
                max_length=255,
                list=False,
            ),
            F(
                "clear_source",
                "enum",
                "Clear source|清除来源|解除ソース",
                enum="alarm_source",
                list=False,
            ),
            F(
                "clear_event_id",
                "str",
                "Clear event ID|清除事件号|解除イベント ID",
                max_length=128,
                list=False,
            ),
            F("hold_ids", "json", "Holds|联动 Hold|連動ホールド", list=False),
            F("e10_change", "json", "E10 change|E10 联动|E10 連動", list=False),
            F("raw", "json", "Raw report|原始上报|生データ", list=False),
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
        partial_unique=[
            (
                "uq_mes_alarm_log_event",
                ("source", "external_event_id"),
                "external_event_id IS NOT NULL",
            ),
            (
                "uq_mes_alarm_log_active",
                ("equipment_id", "alid"),
                "alarm_status = 'active'",
            ),
        ],
        icon="BellRing",
        order=31,
        sort_default="set_at",
        label_field="alid",
        children=["alarm_lot"],
    ),
    Entity(
        "alarm_lot",
        "alarm",
        "Alarm lot|报警关联批次|アラーム関連ロット",
        [
            F(
                "alarm_log",
                "ref",
                "Alarm|报警|アラーム",
                ref="alarm_log",
                required=True,
                cascade=True,
            ),
            F("lot", "ref", "Lot|批次|ロット", ref="lot", required=True),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        menu=False,
        parent="alarm_log",
        unique=[("alarm_log", "lot")],
        sort_default="created_at",
        label_field="lot",
    ),
)

ENUMS.update(
    {
        "alarm_severity": [
            ("info", "Info|提示|情報"),
            ("warning", "Warning|警告|警告"),
            ("minor", "Minor|轻微|軽度"),
            ("major", "Major|严重|重度"),
            ("critical", "Critical|致命|致命的"),
        ],
        "alarm_category": [
            ("process", "Process|工艺|プロセス"),
            ("hardware", "Hardware|硬件|ハードウェア"),
            ("safety", "Safety|安全|安全"),
            ("material", "Material|物料|資材"),
            ("communication", "Communication|通信|通信"),
            ("other", "Other|其他|その他"),
        ],
        "alarm_action": [
            ("none", "None|不联动|連動なし"),
            ("hold_lot", "Hold lots|Hold 批次|ロットホールド"),
            ("hold_equipment", "Equipment state|切换设备状态|設備状態変更"),
            ("hold_both", "Both|两者|両方"),
        ],
        "alarm_status": [
            ("active", "Active|报警中|発生中"),
            ("cleared", "Cleared|已清除|解除済"),
        ],
        "alarm_source": [
            ("manual", "Manual|人工|手動"),
            ("eap", "EAP|EAP|EAP"),
            ("simulator", "Simulator|模拟器|シミュレータ"),
        ],
    }
)
