"""仓储实体规格：仓库、库位、完工入库单及其明细。"""

from app.core.spec.engine import ENUMS, Entity, F, register

ENUMS.update(
    {
        "warehouse_type": [
            ("finished_goods", "Finished goods|成品仓|完成品倉庫"),
            ("semi_finished", "Semi-finished|半成品仓|半製品倉庫"),
            ("raw_material", "Raw material|原材料仓|原材料倉庫"),
            ("quarantine", "Quarantine|待检隔离仓|隔離倉庫"),
            ("scrap", "Scrap|废品仓|廃棄品倉庫"),
        ],
        "location_type": [
            ("rack", "Rack|货架|ラック"),
            ("shelf", "Shelf|层板|棚"),
            ("bin", "Bin|料箱|ビン"),
            (
                "dry_cabinet",
                "Dry cabinet / N2 cabinet|干燥柜 / 氮气柜|ドライ・N2 キャビネット",
            ),
            ("floor", "Floor area|地面区|平置き"),
        ],
        "receipt_status": [
            ("draft", "Draft|草稿|下書き"),
            ("submitted", "Submitted|已提交|提出済"),
            ("confirmed", "Confirmed|已确认|確認済"),
            ("cancelled", "Cancelled|已取消|取消"),
        ],
    }
)


register(
    Entity(
        "warehouse",
        "wh",
        "Warehouse|仓库|倉庫",
        [
            F("site", "ref", required=True, ref="site"),
            F(
                "warehouse_type",
                "enum",
                "Warehouse type|仓库类型|倉庫種別",
                enum="warehouse_type",
                default="finished_goods",
                required=True,
            ),
            F("address", "str", "Address|地址|住所", max_length=300, list=False),
            F("keeper", "str", "Keeper|仓管员|倉庫管理者", search=True),
            F("is_active", "bool", default=True),
        ],
        phase=7,
        icon="Warehouse",
        order=1,
    ),
)


register(
    Entity(
        "storage_location",
        "wh",
        "Storage location|库位|ロケーション",
        [
            F(
                "warehouse",
                "ref",
                "Warehouse|仓库|倉庫",
                required=True,
                ref="warehouse",
            ),
            F(
                "location_type",
                "enum",
                "Location type|库位类型|ロケーション種別",
                enum="location_type",
                default="rack",
                required=True,
            ),
            F(
                "capacity",
                "int",
                "Capacity (lots)|容量（批）|容量（ロット）",
                help="Blank: unlimited|留空表示不限|空欄：無制限",
            ),
            F("is_active", "bool", default=True),
        ],
        phase=7,
        icon="MapPin",
        order=2,
    ),
)


register(
    Entity(
        "receipt",
        "wh",
        "Finished-goods receipt|完工入库单|完成品入庫伝票",
        [
            F(
                "warehouse",
                "ref",
                "Warehouse|仓库|倉庫",
                required=True,
                ref="warehouse",
            ),
            F(
                "location",
                "ref",
                "Storage location|库位|ロケーション",
                ref="storage_location",
                depends="warehouse",
            ),
            F(
                "receipt_status",
                "enum",
                "Status|状态|状態",
                enum="receipt_status",
                system=True,
                default="draft",
            ),
            F("lot_count", "int", "Lots|批次数|ロット数", system=True, default=0),
            F("total_good", "int", "Good qty|良品数|良品数", system=True, default=0),
            F("total_scrap", "int", "Scrap qty|报废数|廃棄数", system=True, default=0),
            F("remarks", "text", "Remarks|备注|備考", list=False),
            F(
                "submitted_at",
                "datetime",
                "Submitted at|提交时间|提出日時",
                system=True,
                list=False,
            ),
            F(
                "submitted_by",
                "str",
                "Submitted by|提交人|提出者",
                system=True,
                list=False,
            ),
            F(
                "confirmed_at",
                "datetime",
                "Confirmed at|确认时间|確認日時",
                system=True,
            ),
            F(
                "confirmed_by",
                "str",
                "Confirmed by|确认人|確認者",
                system=True,
                list=False,
            ),
        ],
        phase=7,
        icon="PackageCheck",
        order=0,
        has_name=False,
        code_label="Receipt no.|入库单号|入庫伝票番号",
        code_auto=True,
        sort_default="created_at",
        children=["receipt_line"],
    ),
)


register(
    Entity(
        "receipt_line",
        "wh",
        "Receipt line|入库明细|入庫明細",
        [
            F(
                "receipt",
                "ref",
                "Receipt|入库单|入庫伝票",
                required=True,
                ref="receipt",
                cascade=True,
            ),
            F(
                "lot",
                "ref",
                "Lot|批次|ロット",
                required=True,
                ref="lot",
                ref_filter={"lot_status": "completed"},
                help="Only finished lots awaiting receipt|仅可选择待入库的批次|入庫待ちロットのみ",
            ),
            F(
                "work_order",
                "ref",
                "Work order|工单|作業指示",
                ref="work_order",
                system=True,
            ),
            F("product", "ref", ref="product", system=True),
            F("good_qty", "int", "Good qty|良品数|良品数", required=True),
            F("scrap_qty", "int", "Scrap qty|报废数|廃棄数", default=0),
            F("remarks", "str", "Remarks|备注|備考", max_length=300, list=False),
        ],
        phase=7,
        has_code=False,
        parent="receipt",
        unique=[("receipt", "lot")],
        icon="List",
        order=3,
        sort_default="created_at",
        label_field="good_qty",
    ),
)
