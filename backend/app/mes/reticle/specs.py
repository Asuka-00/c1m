"""光罩履历 / 关系表规格（P3-B4，docs p3-reticle-model v0.8.2 + D66–D69）。

6 张新表：适用关系、事故、挂载、计数、检查、状态履历。全部 ``mes_`` 前缀 + ``tenant_id`` + RLS
（迁移 0030 调 ``app.core.rls.enable_tenant_rls_sql``）；计数列 numeric(18,6)；时间列 timestamptz，
接口输出 UTC Z（D45）。``source`` 复用 ``alarm_source``（D66 Q13）。履历表通用 CRUD 只读。
"""

from typing import Any

from app.core.spec.engine import ENUMS, Entity, F, register

SRC = F(
    "source",
    "enum",
    "Source|来源|ソース",
    enum="reticle_source",
    required=True,
    default="manual",
)
EXT = F(
    "external_event_id",
    "str",
    "External event ID|外部事件号|外部イベント ID",
    max_length=128,
    list=False,
)
USER = F("username", "str", "User|用户|ユーザー", max_length=255, search=True)
CMT = F("comment", "str", "Comment|备注|コメント", max_length=300, list=False)


def _rt(cascade: bool = False) -> F:
    """光罩引用。

    D72：5 张履历表 ON DELETE RESTRICT（有履历的光罩不能删，只能 scrap）；
    适用关系表仍随光罩级联删除。
    """
    return F(
        "reticle",
        "ref",
        "Reticle|光罩|レチクル",
        ref="reticle",
        required=True,
        cascade=cascade,
    )


def _event_uq(table: str) -> list[tuple[str, tuple[str, ...], str]]:
    return [
        (
            f"uq_mes_reticle_{table}_event",
            ("source", "external_event_id"),
            "external_event_id IS NOT NULL",
        )
    ]


ENUMS.update(
    {
        "reticle_usage_kind": [
            ("track_out", "Track out|出站|トラックアウト"),
            ("report", "Reported|上报|報告"),
            ("adjust", "Adjust|调整|調整"),
            ("reset", "Life reset|寿命复位|寿命リセット"),
        ],
        "reticle_incident_kind": [
            ("collision", "Collision|碰撞|衝突"),
            ("drop", "Drop|掉落|落下"),
            ("other", "Other|其他|その他"),
        ],
        "reticle_inspection_kind": [
            ("particle", "Particle|颗粒|パーティクル"),
            ("haze", "Haze|雾化|ヘイズ"),
            ("cd", "CD|CD|CD"),
            ("other", "Other|其他|その他"),
        ],
        "reticle_inspection_result": [
            ("pass", "Pass|合格|合格"),
            ("fail", "Fail|不合格|不合格"),
        ],
        "reticle_disposition": [
            ("none", "None|无|なし"),
            ("clean", "Clean|清洗|洗浄"),
            ("hold", "Hold|Hold|ホールド"),
            ("repair", "Repair|维修|修理"),
            ("scrap", "Scrap|报废|廃棄"),
        ],
        # D80 G6：库里 CHECK (manual, eap, simulator, system)（迁移 0035）
        "reticle_source": [
            ("manual", "Manual|人工|手動"),
            ("eap", "EAP|EAP|EAP"),
            ("simulator", "Simulator|模拟器|シミュレータ"),
            ("system", "System|系统|システム"),
        ],
        "reticle_mount_event": [
            ("mount", "Mount|上机|装着"),
            ("unmount", "Unmount|下机|取外し"),
        ],
        "reticle_unmount_reason": [
            ("manual", "Manual|人工|手動"),
            ("hold", "Hold|Hold|ホールド"),
            ("incident", "Incident|事故|事故"),
            ("scrap", "Scrap|报废|廃棄"),
        ],
        "reticle_action": [
            ("mount", "Mount|挂载|装着"),
            ("unmount", "Unmount|卸载|取外し"),
            ("hold", "Hold|Hold|ホールド"),
            ("release", "Release|释放|解除"),
            ("restore", "Restore|恢复|復帰"),
            ("life_reset", "Life reset|寿命复位|寿命リセット"),
            ("clean_start", "Start cleaning|开始清洗|洗浄開始"),
            ("clean_complete", "Cleaning complete|清洗完成|洗浄完了"),
            ("repair_complete", "Repair complete|维修完成|修理完了"),
            ("inspect_start", "Start inspection|开始检查|検査開始"),
            ("inspection", "Inspection|检查|検査"),
            ("incident", "Incident|事故|事故"),
            ("scrap", "Scrap|报废|廃棄"),
            ("system", "System|系统|システム"),
        ],
        "reticle_trigger": [
            ("manual", "Manual|人工|手動"),
            ("system", "System|系统|システム"),
        ],
    }
)

COMMON: dict[str, Any] = {
    "phase": 6,
    "has_code": False,
    "readonly": True,
    "menu": False,
    "perm_module": "reticle",
}

register(
    Entity(
        "reticle_applicability",
        "product",
        "Reticle applicability|光罩适用关系|レチクル適用",
        [
            _rt(cascade=True),
            F("product", "ref", ref="product", required=True),
            F("layer", "str", "Layer|层|レイヤー", max_length=40, required=True),
            F(
                "shots_per_wafer",
                "float",
                "Shots per wafer|每片曝光次数|ウェーハ当たりショット数",
                scale=6,
            ),
            F("is_primary", "bool", "Primary|主适用|主適用", default=False),
            CMT,
        ],
        phase=6,
        has_code=False,
        menu=False,
        parent="reticle",
        perm_module="reticle",
        unique=[("reticle", "product", "layer")],
        sort_default="layer",
        label_field="layer",
    ),
    Entity(
        "reticle_incident",
        "product",
        "Reticle incident|光罩事故|レチクル事故",
        [
            _rt(),
            F(
                "kind",
                "enum",
                "Kind|类型|種別",
                enum="reticle_incident_kind",
                required=True,
            ),
            F("occurred_at", "datetime", "Time|时间|日時", required=True),
            F("equipment", "ref", "Equipment|设备|設備", ref="equipment"),
            F("lot", "ref", "Lot|批次|ロット", ref="lot"),
            F(
                "description",
                "str",
                "Description|说明|説明",
                max_length=300,
                list=False,
            ),
            SRC,
            EXT,
            USER,
        ],
        partial_unique=_event_uq("incident"),
        sort_default="occurred_at",
        label_field="kind",
        **COMMON,
    ),
    Entity(
        "reticle_mount_log",
        "product",
        "Reticle mount log|光罩挂载履历|レチクル装着履歴",
        [
            _rt(),
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
            F("slot_code", "str", "Slot|槽位|スロット", max_length=64),
            F("mounted_at", "datetime", "Mounted at|挂载时间|装着日時", required=True),
            F("unmounted_at", "datetime", "Unmounted at|卸载时间|取外し日時"),
            F(
                "unmount_reason",
                "enum",
                "Unmount reason|卸载原因|取外し理由",
                enum="reticle_unmount_reason",
            ),
            F(
                "shots_at_mount",
                "float",
                "Shots at mount|挂载时 shot|装着時ショット",
                scale=6,
            ),
            F(
                "shots_at_unmount",
                "float",
                "Shots at unmount|卸载时 shot|取外し時ショット",
                scale=6,
            ),
            # D80 G1：上机行 mount；下机单独一行 unmount（mount_log 指向上机行）
            F(
                "event_type",
                "enum",
                "Event|事件|イベント",
                enum="reticle_mount_event",
                required=True,
                default="mount",
            ),
            F(
                "mount_log",
                "ref",
                "Mount record|上机记录|装着記録",
                ref="reticle_mount_log",
                list=False,
                filter=False,
            ),
            CMT,
            SRC,
            EXT,
            USER,
        ],
        partial_unique=[
            ("uq_mes_reticle_mount_open", ("reticle_id",), "unmounted_at IS NULL"),
            (
                "uq_mes_reticle_slot_open",
                ("equipment_id", "slot_code"),
                "unmounted_at IS NULL AND slot_code IS NOT NULL",
            ),
            *_event_uq("mount"),
        ],
        sort_default="mounted_at",
        label_field="mounted_at",
        **COMMON,
    ),
    Entity(
        "reticle_usage",
        "product",
        "Reticle usage|光罩计数履历|レチクル使用履歴",
        [
            _rt(),
            F("equipment", "ref", "Equipment|设备|設備", ref="equipment"),
            F("lot", "ref", "Lot|批次|ロット", ref="lot"),
            F("operation", "ref", "Operation|工序|工程", ref="operation"),
            F("delta", "float", "Delta|增量|増分", required=True, scale=6),
            F("count_after", "float", "Count after|计数后|カウント後", scale=6),
            F(
                "kind",
                "enum",
                "Kind|类型|種別",
                enum="reticle_usage_kind",
                required=True,
            ),
            F("occurred_at", "datetime", "Time|时间|日時", required=True),
            F("reason", "ref", "Reason|原因|理由", ref="reason_code", list=False),
            CMT,
            SRC,
            EXT,
            USER,
            F("counted", "bool", "Counted|已累加|加算済", default=True),
            F("estimated", "bool", "Estimated|估算|推定", default=False),
            F("corrected_at", "datetime", "Corrected at|修正时间|修正日時", list=False),
            F(
                "estimated_delta",
                "float",
                "Estimated delta|估算增量|推定増分",
                scale=6,
                list=False,
            ),
        ],
        partial_unique=_event_uq("usage"),
        sort_default="occurred_at",
        label_field="delta",
        **COMMON,
    ),
    Entity(
        "reticle_inspection",
        "product",
        "Reticle inspection|光罩检查记录|レチクル検査記録",
        [
            _rt(),
            F(
                "kind",
                "enum",
                "Kind|类型|種別",
                enum="reticle_inspection_kind",
                required=True,
            ),
            F(
                "result",
                "enum",
                "Result|结果|結果",
                enum="reticle_inspection_result",
                required=True,
            ),
            F("defect_count", "int", "Defects|缺陷数|欠陥数"),
            F("measured", "json", "Measured data|测量数据|測定データ", list=False),
            F("equipment", "ref", "Inspection tool|检查机|検査機", ref="equipment"),
            F(
                "inspected_at",
                "datetime",
                "Inspected at|检查时间|検査日時",
                required=True,
            ),
            F(
                "disposition",
                "enum",
                "Disposition|处置|処置",
                enum="reticle_disposition",
                required=True,
                default="none",
            ),
            F("shots_at_inspection", "float", "Shots|shot 数|ショット数", scale=6),
            CMT,
            USER,  # D71 补充：检查记录不带 source / external_event_id（迁移 0031）
        ],
        sort_default="inspected_at",
        label_field="result",
        **COMMON,
    ),
    Entity(
        "reticle_status_log",
        "product",
        "Reticle status history|光罩状态履历|レチクル状態履歴",
        [
            _rt(),
            F("from_status", "enum", "From|原状态|変更前", enum="reticle_status"),
            F(
                "to_status",
                "enum",
                "To|新状态|変更後",
                enum="reticle_status",
                required=True,
            ),
            F(
                "action",
                "enum",
                "Action|动作|操作",
                enum="reticle_action",
                required=True,
            ),
            F(
                "hold_reason_from",
                "enum",
                "Hold reason (from)|原 Hold 原因|変更前ホールド理由",
                enum="reticle_hold_reason",
                list=False,
            ),
            F(
                "hold_reason_to",
                "enum",
                "Hold reason (to)|新 Hold 原因|変更後ホールド理由",
                enum="reticle_hold_reason",
                list=False,
            ),
            F("reason", "str", "Reason|原因|理由", max_length=300),
            CMT,
            F(
                "trigger",
                "enum",
                "Trigger|触发|トリガー",
                enum="reticle_trigger",
                required=True,
                default="manual",
            ),
            USER,
            F("at", "datetime", "Time|时间|日時", required=True),
        ],
        sort_default="at",
        label_field="action",
        **COMMON,
    ),
)
