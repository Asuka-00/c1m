"""工艺实体规格：工序、路线、工步、资源、配方、参数规格。"""

from app.core.spec.engine import ENTITIES, ENUMS, Entity, F, register

ENUMS.update(
    {
        "operation_type": [
            ("process", "Process|加工|加工"),
            ("metrology", "Metrology|量测|計測"),
            ("inspection", "Inspection|检验|検査"),
            ("test", "Test|测试|テスト"),
            ("clean", "Clean|清洗|洗浄"),
            ("move", "Move / stocker|搬送|搬送"),
        ],
        "route_type": [
            ("main", "Main route|主流程|メインルート"),
            ("sub", "Sub-route|子流程|サブルート"),
            ("rework", "Rework route|返工流程|リワークルート"),
        ],
        "step_type": [
            ("operation", "Operation|工序|工程"),
            ("sub_route", "Call sub-route|调用子流程|サブルート呼出"),
        ],
        "recipe_type": [
            ("production", "Production|生产|生産"),
            ("monitor", "Monitor|监控|モニター"),
            ("clean", "Clean / seasoning|清洗 / 暖机|洗浄 / シーズニング"),
            ("rework", "Rework|返工|リワーク"),
        ],
        "rework_return": [
            (
                "same_step",
                "Same step (re-process)|原步骤（重做）|同一ステップ（再処理）",
            ),
            ("next_step", "Next step|下一步骤|次ステップ"),
        ],
        "qty_basis": [
            ("per_lot", "Per lot|每批|ロット当たり"),
            ("per_unit", "Per unit / wafer|每单元/片|ユニット・ウェーハ当たり"),
        ],
        "resource_kind": [
            ("equipment", "Equipment|设备|設備"),
            ("equipment_group", "Equipment group|设备组|設備グループ"),
            ("reticle", "Reticle|光罩|レチクル"),
            ("material", "Material|物料|資材"),
            ("fixture", "Fixture / tool|治具 / 工具|治具・工具"),
        ],
    }
)

RESOURCE_REFS = ("equipment", "equipment_group", "reticle", "material", "fixture")

register(
    Entity(
        "operation",
        "process",
        "Operation / step|工序|工程",
        [
            F(
                "operation_type",
                "enum",
                "Type|类型|種別",
                required=True,
                enum="operation_type",
                default="process",
            ),
            F("area", "ref", ref="area", required=True),
            F(
                "std_minutes",
                "float",
                "Standard time (min)|标准工时（分钟）|標準時間（分）",
            ),
            F("is_active", "bool", default=True),
        ],
        phase=3,
        icon="ClipboardList",
    ),
)


register(
    Entity(
        "route",
        "process",
        "Route / flow|工艺流程|ルート / フロー",
        [
            F(
                "route_type",
                "enum",
                "Route type|流程类型|ルート種別",
                required=True,
                enum="route_type",
                default="main",
            ),
            F(
                "product_family",
                "ref",
                "Product family|产品族|製品ファミリー",
                ref="product_family",
            ),
        ],
        phase=3,
        versioned=True,
        children=["route_step"],
        icon="Route",
        order=1,
    ),
)


register(
    Entity(
        "route_step",
        "process",
        "Route step|流程步骤|ルートステップ",
        [
            F("route", "ref", required=True, ref="route", cascade=True),
            F("seq", "int", "Seq.|序号|順番", required=True),
            F(
                "step_type",
                "enum",
                "Step type|步骤类型|ステップ種別",
                required=True,
                enum="step_type",
                default="operation",
            ),
            F(
                "operation",
                "ref",
                ref="operation",
                required_when={"step_type": ("operation",)},
            ),
            F(
                "sub_route",
                "ref",
                "Sub-route|子流程|サブルート",
                ref="route",
                required_when={"step_type": ("sub_route",)},
            ),
            F(
                "rework_route",
                "ref",
                "Rework route|返工流程|リワークルート",
                ref="route",
            ),
            F("is_optional", "bool", "Optional|可选|任意", default=False),
            F(
                "branch_condition",
                "str",
                "Branch condition|分支条件|分岐条件",
                max_length=200,
                search=True,
                help="e.g. lot_type == 'ENG' — evaluated at execution time (not in this module)|"
                "例如 lot_type == 'ENG'，执行时判定（不在本模块）|"
                "例：lot_type == 'ENG'（実行時に判定。本モジュール対象外）",
                required_when={"branch_to_seq": ("*",)},
            ),
            F("branch_to_seq", "int", "Branch to seq.|分支跳转序号|分岐先順番"),
            F(
                "rework_return",
                "enum",
                "Rework returns to|返工返回|リワーク復帰先",
                enum="rework_return",
                default="same_step",
                list=False,
            ),
            F(
                "auto_move_in",
                "bool",
                "Auto move in|自动进站|自動ムーブイン",
                default=False,
                list=False,
            ),
            F(
                "auto_track_in",
                "bool",
                "Auto track in|自动上机|自動トラックイン",
                default=False,
                list=False,
            ),
            F(
                "auto_track_out",
                "bool",
                "Auto track out|自动下机|自動トラックアウト",
                default=False,
                list=False,
            ),
            F(
                "auto_move_out",
                "bool",
                "Auto move out|自动出站|自動ムーブアウト",
                default=False,
                list=False,
            ),
            F("note", "str", "Note|备注|備考", max_length=200, list=False),
        ],
        phase=3,
        has_code=False,
        parent="route",
        children=["step_resource"],
        unique=[("route", "seq")],
        icon="ListTree",
        order=2,
        sort_default="seq",
        label_field="seq",
        label_ref="operation",
    ),
)


register(
    Entity(
        "step_resource",
        "process",
        "Step resource|步骤资源|ステップ資源",
        [
            F(
                "route_step",
                "ref",
                "Route step|流程步骤|ルートステップ",
                required=True,
                ref="route_step",
                cascade=True,
            ),
            F(
                "resource_kind",
                "enum",
                "Resource kind|资源类型|資源種別",
                required=True,
                enum="resource_kind",
            ),
            F("equipment", "ref", ref="equipment"),
            F(
                "equipment_group",
                "ref",
                "Equipment group|设备组|設備グループ",
                ref="equipment_group",
            ),
            F("reticle", "ref", "Reticle|光罩|レチクル", ref="reticle"),
            F("material", "ref", "Material|物料|資材", ref="material"),
            F("fixture", "ref", "Fixture / tool|治具 / 工具|治具・工具", ref="fixture"),
            F("recipe", "ref", ref="recipe"),
            F("qty", "float", "Quantity|数量|数量"),
            F("uom", "ref", ref="uom", list=False, required_when={"qty": ("*",)}),
            F(
                "qty_basis",
                "enum",
                "Quantity basis|用量基准|数量基準",
                enum="qty_basis",
                default="per_lot",
                list=False,
            ),
        ],
        phase=3,
        has_code=False,
        parent="route_step",
        unique=[("route_step", "resource_kind", *RESOURCE_REFS, "recipe")],
        icon="Boxes",
        order=3,
        sort_default="resource_kind",
        label_field="resource_kind",
    ),
)


register(
    Entity(
        "product_route",
        "process",
        "Product ↔ route|产品流程绑定|製品・ルート割当",
        [
            F("product", "ref", required=True, ref="product"),
            F("route", "ref", required=True, ref="route"),
            F("is_default", "bool", "Default|默认|デフォルト", default=True),
            F("priority", "int", "Priority|优先级|優先度", default=1),
            F("effective_from", "date", "Effective from|生效日期|有効開始日"),
            F("effective_to", "date", "Effective to|失效日期|有効終了日"),
        ],
        phase=3,
        has_code=False,
        unique=[("product", "route")],
        icon="Workflow",
        order=4,
        sort_default="priority",
        label_field="priority",
    ),
)


register(
    Entity(
        "recipe",
        "process",
        "Recipe|配方|レシピ",
        [
            F("equipment_type", "ref", ref="equipment_type", required=True),
            F(
                "recipe_type",
                "enum",
                "Recipe type|配方类型|レシピ種別",
                required=True,
                enum="recipe_type",
                default="production",
            ),
            F(
                "body",
                "json",
                "Parameters (JSON)|参数（JSON）|パラメータ（JSON）",
                list=False,
            ),
        ],
        phase=3,
        versioned=True,
        children=["recipe_equipment"],
        icon="FileCode",
        order=5,
    ),
)


register(
    Entity(
        "recipe_equipment",
        "process",
        "Recipe ↔ equipment|配方设备映射|レシピ・設備対応",
        [
            F("recipe", "ref", required=True, ref="recipe", cascade=True),
            F("equipment", "ref", required=True, ref="equipment"),
            F(
                "eqp_recipe",
                "str",
                "Equipment recipe name|设备端配方名|装置レシピ名",
                max_length=120,
                search=True,
            ),
            F("is_enabled", "bool", "Enabled|启用|有効", default=True),
        ],
        phase=3,
        has_code=False,
        parent="recipe",
        unique=[("recipe", "equipment")],
        icon="Server",
        order=6,
        sort_default="eqp_recipe",
        label_field="eqp_recipe",
    ),
)


register(
    Entity(
        "param_spec",
        "process",
        "Parameter spec|工艺参数规格|プロセスパラメータ規格",
        [
            F("operation", "ref", ref="operation"),
            F("recipe", "ref", ref="recipe"),
            F("product", "ref", ref="product"),
            F("uom", "ref", ref="uom", list=False, required=True),
            F("target", "float"),
            F("lsl", "float"),
            F("usl", "float"),
        ],
        phase=3,
        unique=[("code", "operation", "recipe", "product")],
        icon="Gauge",
        order=7,
    ),
)


# equipment detail sheet shows its capabilities
ENTITIES["equipment"].children.append("equipment_capability")
