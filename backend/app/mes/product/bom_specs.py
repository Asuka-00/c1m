"""BOM 实体规格（D28，bom.md v1.1）：版本主表、明细、替代料。

状态（``bom_status``）由后端维护：draft → active（同产品只一个 active，旧版自动
superseded）；draft / active → void。只有 draft 可改，明细与替代料随主表锁定。
"""

from app.core.spec.engine import ENUMS, Entity, F, register

# 两级 BOM：激活时校验展开深度（bom.md §10）
MAX_BOM_DEPTH = 2
# 数量精度：Decimal(18, 6)
QTY_SCALE = 6

ENUMS.update(
    {
        "bom_status": [
            ("draft", "Draft|草稿|下書き"),
            ("active", "Active|生效|有効"),
            ("superseded", "Superseded|已替代|置換済"),
            ("void", "Void|作废|無効"),
        ],
        "bom_component_type": [
            ("material", "Material|物料|資材"),
            ("product", "Semi-finished product|半成品|半製品"),
        ],
        # 每多少“什么”：沿用 track_unit_kind，另加 lot
        "bom_per_basis": [
            ("wafer", "Wafer|晶圆|ウェーハ"),
            ("strip", "Strip|条|ストリップ"),
            ("die", "Die|晶粒|ダイ"),
            ("package", "Package|封装体|パッケージ"),
            ("unit", "Unit|单元|ユニット"),
            ("lot", "Lot|批|ロット"),
        ],
        "bom_consume_mode": [
            ("issue", "Issue at track-out|出站扣料|トラックアウト時払出"),
            ("mounted", "Mounted on equipment|机台上料|装置装着"),
        ],
    }
)

register(
    Entity(
        "bom",
        "bom",
        "BOM|物料清单（BOM）|部品表（BOM）",
        [
            F("product", "ref", ref="product", required=True),
            F("version", "int", "Version|版本|バージョン", system=True),
            F(
                "status",
                "enum",
                "Status|状态|状態",
                enum="bom_status",
                default="draft",
                system=True,
            ),
            F(
                "effective_at",
                "datetime",
                "Effective at|生效时间|有効日時",
                system=True,
            ),
            F(
                "confirmed_by",
                "str",
                "Confirmed by|确认人|確認者",
                max_length=255,
                system=True,
            ),
            F(
                "confirmed_at",
                "datetime",
                "Confirmed at|确认时间|確認日時",
                system=True,
                list=False,
            ),
            F(
                "copied_from",
                "ref",
                "Copied from|复制自|コピー元",
                ref="bom",
                system=True,
                list=False,
                filter=False,
            ),
            F("description", "text", list=False, search=True),
        ],
        phase=2,
        has_code=False,
        has_name=False,
        unique=[("product", "version")],
        partial_unique=[("uq_mes_bom_active", ("product",), "status = 'active'")],
        children=["bom_line"],
        icon="ListTree",
        order=4,
        label_field="version",
        label_ref="product",
        sort_default="version",
        menu=False,
    ),
)

register(
    Entity(
        "bom_line",
        "bom",
        "BOM line|BOM 明细|BOM 明細",
        [
            F("bom", "ref", "BOM|BOM|BOM", ref="bom", required=True, cascade=True),
            F("line_no", "int", "Line no.|行号|行番号", required=True),
            F(
                "component_type",
                "enum",
                "Component type|组件类型|構成品種別",
                enum="bom_component_type",
                required=True,
                default="material",
            ),
            F(
                "material",
                "ref",
                "Material|物料|資材",
                ref="material",
                required_when={"component_type": ("material",)},
                only_when_required=True,
            ),
            F(
                "component_product",
                "ref",
                "Semi-finished product|半成品|半製品",
                ref="product",
                required_when={"component_type": ("product",)},
                only_when_required=True,
            ),
            F("qty", "float", "Qty|用量|使用量", required=True, scale=QTY_SCALE),
            F("uom", "ref", "UOM|单位|単位", ref="uom", required=True),
            F(
                "per_basis",
                "enum",
                "Per|每|当たり",
                enum="bom_per_basis",
                required=True,
                default="wafer",
            ),
            F(
                "scrap_rate",
                "float",
                "Scrap rate|损耗率|ロス率",
                default=0,
                scale=QTY_SCALE,
                help="Fraction, e.g. 0.02 = 2%|小数，如 0.02 表示 2%|小数（例：0.02 = 2%）",
            ),
            F(
                "consume_mode",
                "enum",
                "Consume mode|扣料方式|消費方式",
                enum="bom_consume_mode",
                required=True,
            ),
            F(
                "operation",
                "ref",
                "Operation|工序|工程",
                ref="operation",
                list=False,
                filter=False,
                help="Optional: compared at every step of this operation|可选：该工序的所有工步出站时比对|任意：この工程の全ステップで比較",
            ),
            F("remark", "str", "Remark|备注|備考", max_length=300, list=False),
        ],
        phase=2,
        has_code=False,
        parent="bom",
        unique=[("bom", "line_no")],
        children=["bom_line_substitute"],
        icon="List",
        order=1,
        sort_default="line_no",
        label_field="line_no",
        menu=False,
    ),
)

register(
    Entity(
        "bom_line_substitute",
        "bom",
        "Substitute material|替代料|代替資材",
        [
            F(
                "bom_line",
                "ref",
                "BOM line|BOM 明细|BOM 明細",
                ref="bom_line",
                required=True,
                cascade=True,
            ),
            F("material", "ref", "Material|物料|資材", ref="material", required=True),
            F("priority", "int", "Priority|优先级|優先度", required=True, default=1),
            F("remark", "str", "Remark|备注|備考", max_length=300, list=False),
        ],
        phase=2,
        has_code=False,
        parent="bom_line",
        unique=[("bom_line", "material"), ("bom_line", "priority")],
        icon="Replace",
        order=2,
        sort_default="priority",
        label_field="priority",
        menu=False,
    ),
)
