"""导航布局：业务域菜单分组与英文菜单标题（各语言显示文案在前端 ``menu.<key>``）。

纯数据（不导入数据库 / 模型），供菜单同步与前端 code 清单导出使用。每个菜单 key 只出现一次；
路径 / 图标 / 组件 / 权限由各模块的菜单定义提供。
"""

# 分组 key、标题、图标、排序。
# 顺序遵循 MES 常规：工作台 → 日常作业（执行 / 在制报表 / 计划 / 仓储 / 设备 / 质量）
# → 主数据（工艺（含卡控 / 批次规则）/ 产品物料 / 工厂 / 基础数据）→ 系统；
# 设备主数据位于设备管理组内日常作业之后。
# 低频从属主数据（类型 / 分类 / 配置链）以合并菜单的页签呈现，见 MERGED。
# 菜单同步（seed_menus）按此幂等更新已有库的排序与父级。
GROUPS: list[tuple[str, str, str, int]] = [
    ("g-workspace", "Workspace", "LayoutDashboard", 0),
    ("g-execution", "Lot Operation", "PlayCircle", 10),
    ("g-exception", "Exception Handling", "ShieldAlert", 15),
    ("g-wip", "WIP & Inquiry", "LineChart", 20),
    ("g-planning", "Production Planning", "ClipboardList", 30),
    ("g-warehouse", "Warehouse Management", "Warehouse", 40),
    # 机台管理：以后 EAP 的通讯状态 / 报警页面直接加在本组
    ("g-equipment", "Tool Management", "Cpu", 50),
    ("g-quality", "Quality", "BadgeCheck", 60),
    ("g-process", "Process Engineering", "Workflow", 70),
    ("g-product", "Product & Material", "Package", 80),
    ("g-factory", "Factory Modeling", "Factory", 90),
    ("g-master", "Master Data", "BookOpen", 100),
    ("g-system", "System", "Shield", 110),
]

# 分组 key -> [(菜单 key, 标题)]，按显示顺序（组内：日常作业在前，配置在后）
# 批次作业组只放操作员高频项；Hold / Q-Time 归「异常处理」；查询类（批次 / 晶圆）在「在制与查询」。
# 批次履历 / 晶圆状态 / 配方执行是批次操作台的页签，不单设菜单。
ITEMS: dict[str, list[tuple[str, str]]] = {
    "g-workspace": [
        ("dashboard", "Dashboard"),
        ("notifications", "Message Center"),
        ("settings", "Profile"),
    ],
    "g-execution": [
        (
            "mes-lot-console",
            "Lot Operation (Track In/Out)",
        ),
        ("mes-batch-ops", "Batch Operation"),
        ("mes-carrier-ops", "Carrier Operation"),
        ("mes-unit-ops", "Unit Conversion & Die Map"),
        ("mes-shift-handover", "Shift Handover"),
        ("mes-label-print", "Label Printing"),
    ],
    "g-exception": [
        ("mes-lot_hold", "Hold Management"),
        ("mes-qtime-monitor", "Q-Time Monitor"),
        ("mes-ncr", "NCR / MRB"),
        ("mes-future_hold", "Future Hold"),
        ("mes-check_log", "Interlock Log"),
    ],
    "g-wip": [
        ("mes-wip-dashboard", "WIP Dashboard"),
        ("mes-oee-report", "Equipment OEE"),
        ("mes-yield-report", "Yield Report"),
        ("mes-trace", "Traceability"),
        ("mes-lot_recipe_run", "Recipe Run"),
        ("mes-lot", "Lot Inquiry"),
        ("mes-wafer", "Wafer Inquiry"),
        ("mes-die_map", "Die Map Inquiry"),
    ],
    "g-planning": [
        # 投片/开批：叫法为推断，待产线确认
        ("mes-lot-start", "Lot Start"),
        ("mes-wo-board", "WO Progress"),
        ("mes-work_order", "Work Order"),
    ],
    "g-warehouse": [
        ("mes-bank-ops", "Wafer / Die Bank"),
        ("mes-receipt", "Finished Goods Receipt"),
        ("mes-material_receipt", "Material Receipt"),
        ("mes-material_issue", "Material Issue"),
        ("mes-shipment", "Shipment"),
        (
            "mes-material_lot",
            "Line-side Material Lot",
        ),
        ("mes-warehouse-master", "Warehouse Master"),
        ("mes-bank", "Bank Master"),
    ],
    "g-equipment": [
        ("mes-eqp-board", "Tool Status Board"),
        ("mes-pm_plan", "PM Plan"),
        ("mes-downtime", "Downtime"),
        ("mes-e10_history", "E10 History"),
        ("mes-equipment_material_mount", "Material Mount"),
        ("mes-tool", "Consumable Life"),
        ("mes-equipment-master", "Equipment Master"),
        ("mes-e10-model", "E10 State Configuration"),
    ],
    "g-quality": [
        ("mes-dc_result", "Metrology / DC Data"),
        ("mes-spc-chart", "SPC Chart"),
        ("mes-dc-config", "DC Configuration"),
        ("mes-defect_code", "Defect Code"),
        ("mes-bin_code", "Bin Code"),
    ],
    "g-process": [
        ("mes-route-master", "Route Configuration"),
        ("mes-recipe-param", "Recipe & Parameters"),
        ("mes-change_order", "ECN"),
        ("mes-qtime_rule", "Q-Time Rule"),
        ("mes-check-config", "Check Config"),
        ("mes-lot-rules", "Lot Rules"),
    ],
    "g-product": [
        ("mes-product-master", "Product Master"),
        ("mes-material-master", "Material Master"),
        ("mes-bom", "BOM"),
        ("mes-carrier-master", "Carrier Master"),
        ("mes-reticle", "Reticle"),
        ("mes-fixture", "Fixture"),
    ],
    "g-factory": [
        ("mes-factory-model", "Factory Model"),
        ("mes-calendar", "Calendar & Shifts"),
        ("mes-operator_qual", "Operator Qualification"),
    ],
    "g-master": [
        ("mes-reason_code", "Reason Code"),
        ("mes-code_rule", "Code Rule"),
        ("mes-uom", "UOM"),
        ("mes-dict_type", "Dictionary"),
        ("mes-attr_def", "Custom Attribute"),
    ],
    "g-system": [
        ("user-permissions", "Users & Permissions"),
        ("notify-subscriptions", "Notification Subscriptions"),
        ("config", "System Settings"),
        ("mes-audit_log", "Audit Log"),
    ],
}


# 已下线的菜单 key：菜单同步只增改不删，这里列出的在同步时从已有库删除。
RETIRED: list[str] = ["mes-lot-history"]

# 合并菜单：key -> (路径, 图标, 视图, [页签 key])。
# 视图 "tabs"：页签页（各页签复用原页面组件，页签写入 URL ?tab=）；
# "tree"：层级树 + 详情（页签顺序即层级，下级实体的父字段名 = 上级实体编码）。
MERGED: dict[str, tuple[str, str, str, list[str]]] = {
    "mes-check-config": (
        "/mes/check-config",
        "ShieldAlert",
        "tabs",
        ["mes-check_rule", "mes-check_plan", "mes-check_binding"],
    ),
    "mes-product-master": (
        "/mes/product-master",
        "Package",
        "tabs",
        ["mes-product", "mes-product_family", "mes-tech_node"],
    ),
    "mes-material-master": (
        "/mes/material-master",
        "Boxes",
        "tabs",
        ["mes-material", "mes-material_type"],
    ),
    "mes-carrier-master": (
        "/mes/carrier-master",
        "Container",
        "tabs",
        ["mes-carrier", "mes-carrier_type"],
    ),
    "mes-equipment-master": (
        "/mes/equipment-master",
        "Cpu",
        "tabs",
        [
            "mes-equipment",
            "mes-equipment_type",
            "mes-equipment_group",
            "mes-equipment_capability",
        ],
    ),
    "mes-e10-model": (
        "/mes/e10-model",
        "Activity",
        "tabs",
        ["mes-e10_state", "mes-e10_auto_rule"],
    ),
    "mes-lot-rules": (
        "/mes/lot-rules",
        "Layers",
        "tabs",
        ["mes-lot_type", "mes-lot_priority", "mes-split_merge_rule"],
    ),
    "mes-factory-model": (
        "/mes/factory-model",
        "Factory",
        "tree",
        ["mes-site", "mes-area", "mes-workcenter"],
    ),
    "mes-calendar": (
        "/mes/calendar",
        "CalendarDays",
        "tabs",
        ["mes-work_calendar", "mes-shift"],
    ),
    "mes-route-master": (
        "/mes/route-master",
        "Workflow",
        "tabs",
        ["mes-route", "mes-operation", "mes-product_route"],
    ),
    "mes-recipe-param": (
        "/mes/recipe-param",
        "FlaskConical",
        "tabs",
        ["mes-recipe", "mes-param_spec"],
    ),
    "mes-dc-config": (
        "/mes/dc-config",
        "ClipboardCheck",
        "tabs",
        ["mes-dc_plan", "mes-measurement_item", "mes-sampling_rule"],
    ),
    "mes-warehouse-master": (
        "/mes/warehouse-master",
        "Warehouse",
        "tree",
        ["mes-warehouse", "mes-storage_location"],
    ),
    "user-permissions": (
        "/user-permissions",
        "UserCog",
        "tabs",
        ["members", "user-roles"],
    ),
}

# 页签标题（原独立菜单的标题，"en|zh|ja"）
TAB_TITLES: dict[str, str] = {
    "mes-check_rule": "Check Rule",
    "mes-check_plan": "Check Plan",
    "mes-check_binding": "Check Binding",
    "mes-product": "Product",
    "mes-product_family": "Product Family",
    "mes-tech_node": "Technology Node",
    "mes-material": "Material",
    "mes-material_type": "Material Type",
    "mes-carrier": "Carrier",
    "mes-carrier_type": "Carrier Type",
    "mes-equipment": "Equipment",
    "mes-equipment_type": "Equipment Type",
    "mes-equipment_group": "Equipment Group",
    "mes-equipment_capability": "Capability",
    "mes-e10_state": "E10 State Model",
    "mes-e10_auto_rule": "E10 Auto Transition",
    "mes-lot_type": "Lot Type",
    "mes-lot_priority": "Priority",
    "mes-split_merge_rule": "Split / Merge Rule",
    "mes-site": "Site",
    "mes-area": "Area",
    "mes-workcenter": "Work Center",
    "mes-work_calendar": "Work Calendar",
    "mes-shift": "Shift",
    "mes-route": "Route",
    "mes-operation": "Operation",
    "mes-product_route": "Product Route",
    "mes-recipe": "Recipe",
    "mes-param_spec": "Parameter Spec",
    "mes-dc_plan": "DC Plan",
    "mes-measurement_item": "Measurement Item",
    "mes-sampling_rule": "Sampling Rule",
    "mes-warehouse": "Warehouse",
    "mes-storage_location": "Storage Location",
    "members": "Users",
    "user-roles": "Roles",
}


# ---------------- 平台管理控制台（space = platform，仅超级用户） ----------------
# 分组：(key, 标题, 图标, 排序)
PLATFORM_GROUPS: list[tuple[str, str, str, int]] = [
    ("p-g-tenants", "Tenant Management", "Building2", 0),
    ("p-g-rbac", "Platform Access", "ShieldCheck", 10),
    (
        "p-g-settings",
        "Platform Settings",
        "SlidersHorizontal",
        20,
    ),
    ("p-g-ops", "Operations & Audit", "ScrollText", 30),
]
# 页面：key -> (分组, 标题, 路径, 图标, 组件)
PLATFORM_ITEMS: dict[str, tuple[str, str, str, str, str]] = {
    "p-tenants": (
        "p-g-tenants",
        "Tenants",
        "/platform/tenants",
        "Building2",
        "platform-tenants",
    ),
    "p-users": (
        "p-g-rbac",
        "Platform Users",
        "/platform/users",
        "UserCog",
        "users",
    ),
    "p-roles": (
        "p-g-rbac",
        "Platform Roles",
        "/platform/roles",
        "Shield",
        "roles",
    ),
    "p-permissions": (
        "p-g-rbac",
        "Permission Tree",
        "/platform/permissions",
        "KeyRound",
        "platform-permissions",
    ),
    "p-config": (
        "p-g-settings",
        "Platform Defaults",
        "/platform/config",
        "SlidersHorizontal",
        "platform-config",
    ),
    "p-channels": (
        "p-g-settings",
        "Notification Channels",
        "/platform/notify-channels",
        "Send",
        "notify-channels",
    ),
    "p-audit": (
        "p-g-ops",
        "Cross-tenant Audit Log",
        "/platform/audit",
        "History",
        "platform-audit",
    ),
    "p-login-log": (
        "p-g-ops",
        "Login Log",
        "/platform/login-log",
        "LogIn",
        "login-log",
    ),
    "p-ops-log": (
        "p-g-ops",
        "Platform Operation Log",
        "/platform/ops-log",
        "ScrollText",
        "platform-ops-log",
    ),
}


def tab_keys() -> set[str]:
    """所有合并页签的 key（不再作为独立菜单存在）。"""
    return {k for _, _, _, tabs in MERGED.values() for k in tabs}
