"""坐标图实体规格（B4，bom.md §7.4 / §9 / §10 / §12）：

- ``bin_set`` / ``bin_definition``：bin 定义集 + 版本（按版本管理，B8 引用）；
- ``map_import``：导入记录（来源 manual/eap、外部事件号、文件名、导入人 / 时间）；
- ``substrate_map``：坐标图（同一基板重复导入生成新版本），原点 / 轴向取自文件头；
- ``map_cell``：坐标格（行、列、bin 码）。

全部只读（通用接口只能查），写入只走 ``/mes/map`` 导入接口。
"""

from app.core.spec.engine import ENUMS, Entity, F, register

register(
    Entity(
        "bin_set",
        "map",
        "Bin definition set|bin 定义集|ビン定義セット",
        [
            F("version", "int", "Version|版本|版", required=True),
            F(
                "map_import",
                "ref",
                "Import|导入记录|インポート",
                ref="map_import",
                list=False,
            ),
        ],
        phase=6,
        has_name=False,
        code_label="Bin set|定义集|定義セット",
        unique=[("code", "version")],
        readonly=True,
        icon="ListOrdered",
        order=20,
        sort_default="code",
        children=["bin_definition"],
    ),
    Entity(
        "bin_definition",
        "map",
        "Bin definition|bin 定义|ビン定義",
        [
            F(
                "bin_set",
                "ref",
                "Bin set|定义集|定義セット",
                ref="bin_set",
                required=True,
                cascade=True,
            ),
            F(
                "bin_code",
                "str",
                "Bin code|bin 码|ビンコード",
                max_length=32,
                required=True,
            ),
            F(
                "bin_type",
                "enum",
                "Bin type|bin 类型|ビン種別",
                enum="bin_type",
                required=True,
            ),
            F("description", "str", "Description|说明|説明", max_length=200),
        ],
        phase=6,
        has_code=False,
        unique=[("bin_set", "bin_code")],
        readonly=True,
        menu=False,
        parent="bin_set",
        sort_default="bin_code",
        label_field="bin_code",
    ),
    Entity(
        "map_import",
        "map",
        "Map import|坐标图导入记录|マップインポート",
        [
            F(
                "import_kind",
                "enum",
                "Kind|类型|種別",
                enum="map_import_kind",
                required=True,
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
            F("file_name", "str", "File|文件|ファイル", max_length=255, search=True),
            F("row_count", "int", "Rows|行数|行数"),
            F("imported_by", "str", "Imported by|导入人|インポート者", max_length=255),
            F("imported_at", "datetime", "Imported at|导入时间|インポート日時"),
        ],
        phase=6,
        has_code=False,
        readonly=True,
        menu=False,
        partial_unique=[
            (
                "uq_mes_map_import_event",
                ("source", "external_event_id"),
                "external_event_id IS NOT NULL",
            ),
        ],
        sort_default="imported_at",
        label_field="imported_at",
    ),
    Entity(
        "substrate_map",
        "map",
        "Substrate map|坐标图|座標マップ",
        [
            F(
                "substrate_type",
                "enum",
                "Substrate type|基板类型|基板種別",
                enum="substrate_type",
                required=True,
            ),
            F("map_version", "int", "Version|版本|版", required=True),
            F("rows", "int", "Rows|行数|行数", required=True),
            F("cols", "int", "Columns|列数|列数", required=True),
            F(
                "origin_location",
                "enum",
                "Origin|坐标原点|原点",
                enum="origin_location",
                required=True,
            ),
            F(
                "x_axis",
                "enum",
                "X axis|X 轴方向|X 軸方向",
                enum="x_axis",
                required=True,
            ),
            F(
                "y_axis",
                "enum",
                "Y axis|Y 轴方向|Y 軸方向",
                enum="y_axis",
                required=True,
            ),
            F(
                "bin_set",
                "ref",
                "Bin set|定义集|定義セット",
                ref="bin_set",
                required=True,
            ),
            F(
                "map_import",
                "ref",
                "Import|导入记录|インポート",
                ref="map_import",
                required=True,
                list=False,
            ),
            F("total_qty", "int", "Total|坐标总数|総数", required=True),
            F("good_qty", "int", "Good|良品数|良品数"),
            F("excluded_qty", "int", "Excluded|排除数|除外数"),
            F("bin_counts", "json", "Bin counts|各 bin 数量|ビン別数量", list=False),
            # D39：可选关联（批次未给时按晶圆号找晶圆记录所在批次自动关联）
            F("lot", "ref", "Lot|批次|ロット", ref="lot"),
            F("equipment", "ref", "Equipment|设备|設備", ref="equipment"),
            F("operation", "ref", "Operation|工序|工程", ref="operation"),
        ],
        phase=6,
        has_name=False,
        code_label="Substrate ID|基板编号|基板 ID",
        unique=[("code", "map_version")],
        readonly=True,
        icon="Grid3x3",
        order=21,
        sort_default="code",
        children=["map_cell"],
    ),
    Entity(
        "map_cell",
        "map",
        "Map cell|坐标格|マップセル",
        [
            F(
                "substrate_map",
                "ref",
                "Map|坐标图|座標マップ",
                ref="substrate_map",
                required=True,
                cascade=True,
            ),
            F("row", "int", "Row|行|行", required=True),
            F("col", "int", "Column|列|列", required=True),
            F(
                "bin_code",
                "str",
                "Bin code|bin 码|ビンコード",
                max_length=32,
                required=True,
            ),
        ],
        phase=6,
        has_code=False,
        unique=[("substrate_map", "row", "col")],
        readonly=True,
        menu=False,
        parent="substrate_map",
        sort_default="row",
        label_field="bin_code",
    ),
)

ENUMS.update(
    {
        # 排除类（不计入可用颗数）：edge / unusable（B8 拆批层守恒用）
        "bin_type": [
            ("good", "Good|良品|良品"),
            ("fail", "Fail|不良|不良"),
            ("edge", "Edge|边缘|エッジ"),
            ("unusable", "Unusable|不可用|使用不可"),
        ],
        "map_import_kind": [
            ("map", "Substrate map|坐标图|座標マップ"),
            ("bin_set", "Bin definition set|bin 定义集|ビン定義セット"),
        ],
        "substrate_type": [
            ("wafer", "Wafer|晶圆|ウェーハ"),
            ("strip", "Strip|条|ストリップ"),
        ],
        "origin_location": [
            ("UL", "Upper left|左上|左上"),
            ("UR", "Upper right|右上|右上"),
            ("LL", "Lower left|左下|左下"),
            ("LR", "Lower right|右下|右下"),
        ],
        "x_axis": [("right", "Right|向右|右"), ("left", "Left|向左|左")],
        "y_axis": [("down", "Down|向下|下"), ("up", "Up|向上|上")],
    }
)

EXCLUDED_BIN_TYPES = frozenset({"edge", "unusable"})
GOOD_BIN_TYPES = frozenset({"good"})
