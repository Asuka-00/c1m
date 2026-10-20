"""工艺实体规格：工序、路线、工步、资源、配方、参数规格。"""

from app.core.spec.engine import ENTITIES, ENUMS, Entity, F, register

ENUMS.update(
    {
        "operation_type": [
            ("process", "Process"),
            ("metrology", "Metrology"),
            ("inspection", "Inspection"),
            ("test", "Test"),
            ("clean", "Clean"),
            ("move", "Move / stocker"),
        ],
        "route_type": [
            ("main", "Main route"),
            ("sub", "Sub-route"),
            ("rework", "Rework route"),
        ],
        "step_type": [
            ("operation", "Operation"),
            ("sub_route", "Call sub-route"),
        ],
        "recipe_type": [
            ("production", "Production"),
            ("monitor", "Monitor"),
            ("clean", "Clean / seasoning"),
            ("rework", "Rework"),
        ],
        "rework_return": [
            (
                "same_step",
                "Same step (re-process)",
            ),
            ("next_step", "Next step"),
        ],
        "qty_basis": [
            ("per_lot", "Per lot"),
            ("per_unit", "Per unit / wafer"),
        ],
        "change_type": [
            ("route", "Route"),
            ("recipe", "Recipe"),
        ],
        "wip_rule": [
            ("keep_old", "WIP keeps old version"),
            ("switch_new", "WIP switches to new"),
        ],
        "ecn_status": [
            ("draft", "Draft"),
            ("released", "Released (pending)"),
            ("applied", "Effective"),
            ("cancelled", "Cancelled"),
        ],
        "resource_kind": [
            ("equipment", "Equipment"),
            ("equipment_group", "Equipment group"),
            ("reticle", "Reticle"),
            ("material", "Material"),
            ("fixture", "Fixture / tool"),
        ],
    }
)

RESOURCE_REFS = ("equipment", "equipment_group", "reticle", "material", "fixture")

register(
    Entity(
        "operation",
        "process",
        "Operation / step",
        [
            F(
                "operation_type",
                "enum",
                "Type",
                required=True,
                enum="operation_type",
                default="process",
            ),
            F("area", "ref", ref="area", required=True),
            F(
                "std_minutes",
                "float",
                "Standard time (min)",
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
        "Route / flow",
        [
            F(
                "route_type",
                "enum",
                "Route type",
                required=True,
                enum="route_type",
                default="main",
            ),
            F(
                "product_family",
                "ref",
                "Product family",
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
        "Route step",
        [
            F("route", "ref", required=True, ref="route", cascade=True),
            F("seq", "int", "Seq.", required=True),
            F(
                "step_type",
                "enum",
                "Step type",
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
                "Sub-route",
                ref="route",
                required_when={"step_type": ("sub_route",)},
            ),
            F(
                "rework_route",
                "ref",
                "Rework route",
                ref="route",
            ),
            F("is_optional", "bool", "Optional", default=False),
            F(
                "branch_condition",
                "str",
                "Branch condition",
                max_length=200,
                search=True,
                help="e.g. lot_type == 'ENG'",
                required_when={"branch_to_seq": ("*",)},
            ),
            F("branch_to_seq", "int", "Branch to seq."),
            F(
                "max_rework",
                "int",
                "Max reworks",
                help="Blank: unlimited",
                list=False,
            ),
            F(
                "rework_return",
                "enum",
                "Rework returns to",
                enum="rework_return",
                default="same_step",
                list=False,
            ),
            F(
                "auto_move_in",
                "bool",
                "Auto move in",
                default=False,
                list=False,
            ),
            F(
                "auto_track_in",
                "bool",
                "Auto track in",
                default=False,
                list=False,
            ),
            F(
                "auto_track_out",
                "bool",
                "Auto track out",
                default=False,
                list=False,
            ),
            F(
                "auto_move_out",
                "bool",
                "Auto move out",
                default=False,
                list=False,
            ),
            F("note", "str", "Note", max_length=200, list=False),
            F("layout", "json", "Canvas layout", list=False, system=True),
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
        "Step resource",
        [
            F(
                "route_step",
                "ref",
                "Route step",
                required=True,
                ref="route_step",
                cascade=True,
            ),
            F(
                "resource_kind",
                "enum",
                "Resource kind",
                required=True,
                enum="resource_kind",
            ),
            F("equipment", "ref", ref="equipment"),
            F(
                "equipment_group",
                "ref",
                "Equipment group",
                ref="equipment_group",
            ),
            F("reticle", "ref", "Reticle", ref="reticle"),
            F("material", "ref", "Material", ref="material"),
            F("fixture", "ref", "Fixture / tool", ref="fixture"),
            F("recipe", "ref", ref="recipe"),
            F("qty", "float", "Quantity"),
            F("uom", "ref", ref="uom", list=False, required_when={"qty": ("*",)}),
            F(
                "qty_basis",
                "enum",
                "Quantity basis",
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
        "Product ↔ route",
        [
            F("product", "ref", required=True, ref="product"),
            F("route", "ref", required=True, ref="route"),
            F("is_default", "bool", "Default", default=True),
            F("priority", "int", "Priority", default=1),
            F("effective_from", "date", "Effective from"),
            F("effective_to", "date", "Effective to"),
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
        "Recipe",
        [
            F("equipment_type", "ref", ref="equipment_type", required=True),
            F(
                "recipe_type",
                "enum",
                "Recipe type",
                required=True,
                enum="recipe_type",
                default="production",
            ),
            F(
                "body",
                "json",
                "Parameters (JSON)",
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
        "Recipe ↔ equipment",
        [
            F("recipe", "ref", required=True, ref="recipe", cascade=True),
            F("equipment", "ref", required=True, ref="equipment"),
            F(
                "eqp_recipe",
                "str",
                "Equipment recipe name",
                max_length=120,
                search=True,
            ),
            F(
                "ideal_uph",
                "float",
                "Ideal throughput (UPH)",
                help="Optional; overrides the equipment UPH for OEE",
                list=False,
            ),
            F("is_enabled", "bool", "Enabled", default=True),
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
        "Parameter spec",
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


register(
    Entity(
        "change_order",
        "process",
        "Engineering change",
        [
            F(
                "change_type",
                "enum",
                "Change of",
                required=True,
                enum="change_type",
                default="route",
            ),
            F(
                "route",
                "ref",
                "New route version",
                ref="route",
                required_when={"change_type": ("route",)},
                only_when_required=True,
            ),
            F(
                "recipe",
                "ref",
                "New recipe version",
                ref="recipe",
                required_when={"change_type": ("recipe",)},
                only_when_required=True,
            ),
            F("effective_at", "datetime", "Effective at"),
            F(
                "wip_rule",
                "enum",
                "WIP rule",
                enum="wip_rule",
                default="keep_old",
                required=True,
                help="Route changes: waiting lots stay on the old version or move to the new one by step seq",
            ),
            F("reason", "text", "Reason", list=False),
            F(
                "ecn_status",
                "enum",
                "Status",
                enum="ecn_status",
                system=True,
                default="draft",
            ),
            F(
                "applied_at",
                "datetime",
                "Applied at",
                system=True,
            ),
            F("result", "json", "Result", system=True, list=False),
        ],
        phase=3,
        icon="GitPullRequestArrow",
        order=9,
        sort_default="created_at",
    ),
)
