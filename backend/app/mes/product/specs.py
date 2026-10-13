"""产品与物料实体规格（单位、产品、物料、载具、光罩、治具、线边批次）。"""

from app.core.spec.engine import ENTITIES, ENUMS, Entity, F, register

ENUMS.update(
    {
        "uom_dimension": [
            ("count", "Count|数量|数量"),
            ("length", "Length|长度|長さ"),
            ("area", "Area|面积|面積"),
            ("volume", "Volume|体积|体積"),
            ("mass", "Mass|质量|質量"),
            ("time", "Time|时间|時間"),
            ("pressure", "Pressure|压力|圧力"),
            ("temperature", "Temperature|温度|温度"),
            ("energy_density", "Energy density|能量密度|エネルギー密度"),
        ],
        "wafer_size": [
            ("100", '100 mm (4")|100 mm（4 寸）|100 mm（4 インチ）'),
            ("150", '150 mm (6")|150 mm（6 寸）|150 mm（6 インチ）'),
            ("200", '200 mm (8")|200 mm（8 寸）|200 mm（8 インチ）'),
            ("300", '300 mm (12")|300 mm（12 寸）|300 mm（12 インチ）'),
        ],
        "product_type": [
            ("production", "Production|量产|量産"),
            ("engineering", "Engineering|工程|エンジニアリング"),
            ("monitor", "Monitor|监控片|モニター"),
            ("dummy", "Dummy|陪片|ダミー"),
        ],
        "material_category": [
            ("wafer", "Raw wafer|原始晶圆|原料ウェーハ"),
            ("chemical", "Chemical|化学品|薬液"),
            ("gas", "Gas|气体|ガス"),
            ("target", "Sputter target|靶材|ターゲット"),
            ("slurry", "Slurry|研磨液|スラリー"),
            ("photoresist", "Photoresist|光刻胶|フォトレジスト"),
            ("consumable", "Consumable|耗材|消耗品"),
        ],
        "carrier_category": [
            ("foup", "FOUP|FOUP|FOUP"),
            ("fosb", "FOSB|FOSB|FOSB"),
            ("cassette", "Cassette|片盒|カセット"),
            ("pod", "Reticle pod|光罩盒|レチクルポッド"),
            ("smif", "SMIF pod|SMIF 盒|SMIF ポッド"),
        ],
        "carrier_event_type": [
            ("load", "Load|装入|積込み"),
            ("unload", "Unload|移出|取出し"),
            ("clean", "Clean|清洗|洗浄"),
        ],
        "asset_status": [
            ("available", "Available|可用|使用可"),
            ("in_use", "In use|使用中|使用中"),
            ("dirty", "Needs cleaning|待清洗|要洗浄"),
            ("hold", "On hold|冻结|保留"),
            ("retired", "Retired|报废|廃棄"),
        ],
        "reticle_grade": [
            ("binary", "Binary|二元掩模|バイナリ"),
            ("psm", "Phase shift (PSM)|相移掩模|位相シフト"),
            ("euv", "EUV|EUV|EUV"),
        ],
        "fixture_kind": [
            ("probe_card", "Probe card|探针卡|プローブカード"),
            ("fixture", "Fixture|治具|治具"),
            ("jig", "Jig|夹具|ジグ"),
            ("tool", "Tool|工具|工具"),
        ],
        "eqp_category": [
            ("process", "Process|工艺设备|プロセス装置"),
            ("metrology", "Metrology|量测设备|計測装置"),
            ("inspection", "Inspection|检测设备|検査装置"),
            ("test", "Test|测试设备|テスト装置"),
            ("transport", "Transport (AMHS)|搬运设备|搬送装置"),
        ],
        "unit_kind": [
            ("main", "Main equipment|主设备|本体"),
            ("chamber", "Chamber|腔体|チャンバー"),
            ("load_port", "Load port|装载口|ロードポート"),
            ("port", "Port|端口|ポート"),
            ("sub_unit", "Sub-unit|子单元|サブユニット"),
        ],
        "tracking_level": [
            ("wafer", "Wafer (slots)|晶圆（槽位）|ウェーハ（スロット）"),
            ("unit", "Serialized unit|序列化单元|シリアル管理ユニット"),
            ("quantity", "Quantity|数量|数量"),
        ],
        "serial_kind": [
            ("strip", "Strip|条|ストリップ"),
            ("die", "Die|晶粒|ダイ"),
            ("package", "Package|封装体|パッケージ"),
            ("unit", "Unit|单元|ユニット"),
        ],
        "e10_category": [
            ("PRD", "PRD · Productive|PRD · 生产|PRD · 生産"),
            ("SBY", "SBY · Standby|SBY · 待机|SBY · 待機"),
            ("ENG", "ENG · Engineering|ENG · 工程|ENG · エンジニアリング"),
            ("SDT", "SDT · Scheduled down|SDT · 计划停机|SDT · 計画停止"),
            ("UDT", "UDT · Unscheduled down|UDT · 非计划停机|UDT · 計画外停止"),
            ("NST", "NST · Non-scheduled|NST · 非排程|NST · 非稼働予定"),
        ],
    }
)

register(
    # ---------------- product & material ----------------
    Entity(
        "uom",
        "product",
        "Unit of measure|计量单位|単位",
        [
            F("symbol", "str", "Symbol|符号|記号", max_length=20, search=True),
            F(
                "dimension",
                "enum",
                "Dimension|量纲|次元",
                required=True,
                enum="uom_dimension",
            ),
        ],
        phase=2,
        icon="Ruler",
        children=["uom_conversion"],
    ),
)


register(
    Entity(
        "uom_conversion",
        "product",
        "UOM conversion|单位换算|単位換算",
        [
            F(
                "from_uom",
                "ref",
                "From|源单位|換算元",
                required=True,
                ref="uom",
                cascade=True,
            ),
            F("to_uom", "ref", "To|目标单位|換算先", required=True, ref="uom"),
            F(
                "factor",
                "float",
                "Factor|换算系数|換算係数",
                required=True,
                help="to = from × factor|目标 = 源 × 系数|換算先 = 換算元 × 係数",
            ),
            F("offset", "float", "Offset|偏移量|オフセット", default=0, list=False),
        ],
        phase=2,
        has_code=False,
        parent="uom",
        unique=[("from_uom", "to_uom")],
        icon="ArrowLeftRight",
        order=1,
        sort_default="factor",
        label_field="factor",
    ),
)


register(
    Entity(
        "tech_node",
        "product",
        "Technology node|工艺节点|テクノロジーノード",
        [
            F("feature_nm", "float", "Feature size (nm)|特征尺寸（nm）|最小寸法（nm）"),
            F("wafer_size", "enum", enum="wafer_size", default="300"),
            F(
                "tracking_level",
                "enum",
                "Tracking level|追踪层级|追跡レベル",
                required=True,
                enum="tracking_level",
                default="wafer",
            ),
        ],
        phase=2,
        icon="Atom",
        order=2,
    ),
)


register(
    Entity(
        "product_family",
        "product",
        "Product family|产品族|製品ファミリー",
        [
            F(
                "tech_node",
                "ref",
                "Technology node|工艺节点|テクノロジーノード",
                ref="tech_node",
                required=True,
            )
        ],
        phase=2,
        icon="Boxes",
        order=3,
    ),
)


register(
    Entity(
        "product",
        "product",
        "Product|产品|製品",
        [
            F(
                "family",
                "ref",
                "Family|产品族|ファミリー",
                ref="product_family",
                required_when={"product_type": ("production", "engineering")},
            ),
            F(
                "tech_node",
                "ref",
                "Technology node|工艺节点|テクノロジーノード",
                ref="tech_node",
                required_when={"product_type": ("production", "engineering")},
            ),
            F(
                "product_type",
                "enum",
                "Type|类型|種別",
                enum="product_type",
                default="production",
            ),
            F("wafer_size", "enum", enum="wafer_size", default="300"),
            F(
                "gross_die",
                "int",
                "Gross die / wafer|每片总晶粒数|ウェーハ当たりダイ数",
            ),
            F("uom", "ref", ref="uom", list=False, required=True),
            F(
                "tracking_level",
                "enum",
                "Tracking level|追踪层级|追跡レベル",
                enum="tracking_level",
                list=False,
                help="Blank: inherit from the technology node|留空则继承工艺节点|空欄：テクノロジーノードを継承",
            ),
            F(
                "serial_kind",
                "enum",
                "Serialized unit kind|序列化单元类型|シリアル単位種別",
                enum="serial_kind",
                list=False,
                required_when={"tracking_level": ("unit",)},
            ),
            F(
                "unit_code_rule",
                "ref",
                "Unit serial rule|单元序列号规则|ユニット採番ルール",
                ref="code_rule",
                list=False,
                required_when={"tracking_level": ("unit",)},
            ),
        ],
        phase=2,
        versioned=True,
        icon="Package",
        order=4,
    ),
)


register(
    Entity(
        "material_type",
        "product",
        "Material type|物料类型|資材タイプ",
        [F("category", "enum", required=True, enum="material_category")],
        phase=2,
        icon="FlaskConical",
        order=5,
    ),
)


register(
    Entity(
        "material",
        "product",
        "Material|物料|資材",
        [
            F(
                "material_type",
                "ref",
                "Material type|物料类型|資材タイプ",
                required=True,
                ref="material_type",
            ),
            F("uom", "ref", required=True, ref="uom"),
            F("vendor", "str", max_length=100, search=True),
            F(
                "shelf_life_days",
                "int",
                "Shelf life (days)|保质期（天）|使用期限（日）",
            ),
            F(
                "storage",
                "str",
                "Storage condition|存储条件|保管条件",
                max_length=200,
                list=False,
            ),
            F("is_active", "bool", default=True),
        ],
        phase=2,
        icon="Beaker",
        order=6,
    ),
)


register(
    Entity(
        "carrier_type",
        "product",
        "Carrier type|载具类型|キャリアタイプ",
        [
            F("category", "enum", required=True, enum="carrier_category"),
            F(
                "capacity",
                "int",
                "Capacity (slots)|容量（槽位）|容量（スロット）",
                required=True,
            ),
            F("wafer_size", "enum", enum="wafer_size", default="300"),
            F(
                "clean_interval_days",
                "int",
                "Clean interval (days)|清洗周期（天）|洗浄周期（日）",
                list=False,
            ),
        ],
        phase=2,
        icon="Container",
        order=7,
    ),
)


register(
    Entity(
        "carrier",
        "product",
        "Carrier|载具|キャリア",
        [
            F(
                "carrier_type",
                "ref",
                "Carrier type|载具类型|キャリアタイプ",
                required=True,
                ref="carrier_type",
            ),
            F("status_code", "enum", enum="asset_status", default="available"),
            F("max_uses", "int", "Max uses|最大使用次数|最大使用回数"),
            F(
                "use_count",
                "int",
                "Uses since clean|清洗后使用次数|洗浄後使用回数",
                system=True,
            ),
            F(
                "last_cleaned_at",
                "datetime",
                "Last cleaned|上次清洗|前回洗浄",
                system=True,
            ),
            F(
                "rfid",
                "str",
                "RFID tag|RFID 标签|RFID タグ",
                max_length=64,
                search=True,
                list=False,
            ),
        ],
        phase=2,
        icon="Archive",
        order=8,
    ),
)


register(
    Entity(
        "carrier_event",
        "product",
        "Carrier event|载具履历|キャリア履歴",
        [
            F(
                "carrier",
                "ref",
                "Carrier|载具|キャリア",
                required=True,
                ref="carrier",
                cascade=True,
            ),
            F("event", "enum", "Event|事件|イベント", enum="carrier_event_type"),
            F("lot", "ref", "Lot|批次|ロット", ref="lot"),
            F(
                "other_carrier",
                "ref",
                "From / to carrier|来源 / 目标载具|移動元・先キャリア",
                ref="carrier",
            ),
            F("qty", "int", "Qty|数量|数量"),
            F("comment", "str", "Comment|备注|コメント", max_length=300, search=True),
            F("username", "str", "User|用户|ユーザー", max_length=255, search=True),
            F("at", "datetime", "Time|时间|日時"),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        icon="History",
        order=10,
        menu=False,
        sort_default="at",
        label_field="event",
    ),
)


register(
    Entity(
        "reticle",
        "product",
        "Reticle|光罩|レチクル",
        [
            F("product", "ref", ref="product", required=True),
            F(
                "layer",
                "str",
                "Layer|层|レイヤー",
                max_length=40,
                search=True,
                required=True,
            ),
            F(
                "grade",
                "enum",
                "Grade|类型|グレード",
                enum="reticle_grade",
                default="binary",
            ),
            F("max_shots", "int", "Max shots|最大曝光次数|最大ショット数"),
            F("status_code", "enum", enum="asset_status", default="available"),
        ],
        phase=2,
        icon="Aperture",
        order=9,
    ),
)


register(
    Entity(
        "fixture",
        "product",
        "Fixture / tool|治具 / 工具|治具・工具",
        [
            F("kind", "enum", "Kind|类型|種別", required=True, enum="fixture_kind"),
            F("max_uses", "int", "Max uses|最大使用次数|最大使用回数"),
            F("status_code", "enum", enum="asset_status", default="available"),
        ],
        phase=2,
        icon="Hammer",
        order=10,
    ),
)


register(
    # ---------------- line-side material & tools ----------------
    Entity(
        "material_lot",
        "inventory",
        "Material lot|线边物料批|ラインサイド資材ロット",
        [
            F("material", "ref", "Material|物料|資材", required=True, ref="material"),
            F("qty_remaining", "float", "Qty remaining|剩余数量|残数量", required=True),
            F("initial_qty", "float", "Received qty|收料数量|受入数量", list=False),
            F("uom", "ref", ref="uom", required=True),
            F("expiry_date", "date", "Expiry|有效期|有効期限"),
            F(
                "location",
                "str",
                "Location|库位|ロケーション",
                max_length=100,
                search=True,
            ),
            F(
                "ml_status",
                "enum",
                "Status|状态|状態",
                enum="ml_status",
                required=True,
                default="available",
            ),
        ],
        phase=6,
        has_name=False,
        code_label="Material lot no.|物料批号|資材ロット番号",
        icon="PackageOpen",
        order=0,
    ),
)

ENTITIES["carrier"].children.append("carrier_event")
