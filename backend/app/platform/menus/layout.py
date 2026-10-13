"""导航布局：业务域菜单分组与菜单标题（"en|zh|ja"）。

纯数据（不导入数据库 / 模型），供菜单同步与 i18n 包导出共同使用。每个菜单 key 只出现一次；
路径 / 图标 / 组件 / 权限由各模块的菜单定义提供。
"""

# 分组 key、标题、图标、排序。
# 顺序遵循 MES 常规：工作台 → 日常作业（执行 / 在制报表 / 计划 / 仓储 / 设备 / 质量）
# → 主数据（工艺（含卡控 / 批次规则）/ 产品物料 / 工厂 / 基础数据）→ 系统；
# 设备主数据位于设备管理组内日常作业之后。
# 低频从属主数据（类型 / 分类 / 配置链）以合并菜单的页签呈现，见 MERGED。
# 菜单同步（seed_menus）按此幂等更新已有库的排序与父级。
GROUPS: list[tuple[str, str, str, int]] = [
    ("g-workspace", "Workspace|工作台|ワークスペース", "LayoutDashboard", 0),
    ("g-execution", "Production Execution|生产执行|生産実行", "PlayCircle", 10),
    ("g-wip", "WIP & Reports|在制与报表|仕掛・レポート", "LineChart", 20),
    ("g-planning", "Production Planning|生产计划|生産計画", "ClipboardList", 30),
    ("g-warehouse", "Warehouse Management|仓储管理|倉庫管理", "Warehouse", 40),
    ("g-equipment", "Equipment Management|设备管理|設備管理", "Cpu", 50),
    ("g-quality", "Quality|质量管理|品質管理", "BadgeCheck", 60),
    ("g-process", "Process Engineering|工艺管理|工程管理", "Workflow", 70),
    ("g-product", "Product & Material|产品与物料|製品・資材", "Package", 80),
    ("g-factory", "Factory Modeling|工厂建模|工場モデリング", "Factory", 90),
    ("g-master", "Master Data|基础数据|基準データ", "BookOpen", 100),
    ("g-system", "System|系统管理|システム管理", "Shield", 110),
]

# 分组 key -> [(菜单 key, 标题)]，按显示顺序（组内：日常作业在前，配置在后）
ITEMS: dict[str, list[tuple[str, str]]] = {
    "g-workspace": [
        ("dashboard", "Dashboard|仪表盘|ダッシュボード"),
        ("notifications", "Message Center|消息中心|メッセージセンター"),
        ("settings", "Profile|个人设置|個人設定"),
    ],
    "g-execution": [
        ("mes-lot-console", "Lot Operation|批次作业|ロット作業"),
        ("mes-qtime-monitor", "Q-Time Monitor|Q-Time 监控|Q タイム監視"),
        ("mes-lot_hold", "Hold Management|Hold 管理|ホールド管理"),
        ("mes-lot", "Lot List|批次列表|ロット一覧"),
        ("mes-wafer", "Wafer|晶圆|ウェーハ"),
    ],
    "g-wip": [
        ("mes-wip-dashboard", "WIP Dashboard|WIP 看板|WIP ダッシュボード"),
        ("mes-oee-report", "Equipment OEE|设备 OEE|設備 OEE"),
        ("mes-lot-history", "Lot History & Trace|批次履历与追溯|ロット履歴・トレース"),
        ("mes-check_log", "Check Log|卡控记录|チェック記録"),
        ("mes-lot_recipe_run", "Recipe Run|配方执行记录|レシピ実行記録"),
    ],
    "g-planning": [
        ("mes-work_order", "Work Order|工单|作業指示"),
        ("mes-lot-start", "Lot Start|投产|ロット投入"),
    ],
    "g-warehouse": [
        ("mes-receipt", "Finished Goods Receipt|完工入库|完成品入庫"),
        (
            "mes-material_lot",
            "Line-side Material Lot|线边物料批|ラインサイド資材ロット",
        ),
        ("mes-warehouse-master", "Warehouse|仓库|倉庫"),
    ],
    "g-equipment": [
        ("mes-eqp-board", "Equipment Status Board|设备状态看板|設備状態ボード"),
        ("mes-pm_plan", "PM Plan|PM 计划|PM 計画"),
        ("mes-downtime", "Downtime|停机记录|停止記録"),
        ("mes-e10_history", "E10 History|E10 状态履历|E10 状態履歴"),
        ("mes-tool", "Tool Life|工具寿命|工具寿命"),
        ("mes-equipment-master", "Equipment|设备|設備"),
        ("mes-e10-model", "E10 State Model|E10 状态模型|E10 状態モデル"),
    ],
    "g-quality": [
        ("mes-dc_result", "DC Data|量测数据|測定データ"),
        ("mes-dc-config", "DC Configuration|数据收集配置|データ収集設定"),
        ("mes-defect_code", "Defect Code|缺陷代码|欠陥コード"),
    ],
    "g-process": [
        ("mes-route-master", "Route|工艺流程|ルート"),
        ("mes-recipe-param", "Recipe & Parameters|配方与参数|レシピ・パラメータ"),
        ("mes-qtime_rule", "Q-Time Rule|Q-Time 规则|Q タイムルール"),
        ("mes-check-config", "Check Config|卡控配置|チェック設定"),
        ("mes-lot-rules", "Lot Rules|批次规则|ロット規則"),
    ],
    "g-product": [
        ("mes-product-master", "Product|产品|製品"),
        ("mes-material-master", "Material|物料|資材"),
        ("mes-carrier-master", "Carrier|载具|キャリア"),
        ("mes-reticle", "Reticle|光罩|レチクル"),
        ("mes-fixture", "Fixture|治具|治具"),
    ],
    "g-factory": [
        ("mes-factory-model", "Factory Model|工厂模型|工場モデル"),
        ("mes-calendar", "Work Calendar|工作日历|稼働カレンダー"),
    ],
    "g-master": [
        ("mes-reason_code", "Reason Code|原因代码|理由コード"),
        ("mes-code_rule", "Code Rule|编码规则|採番ルール"),
        ("mes-uom", "UOM|计量单位|単位"),
        ("mes-dict_type", "Dictionary|数据字典|データ辞書"),
        ("mes-attr_def", "Custom Attribute|自定义属性|カスタム属性"),
    ],
    "g-system": [
        ("user-permissions", "Users & Permissions|用户与权限|ユーザーと権限"),
        ("notify-subscriptions", "Notification Subscriptions|通知订阅|通知購読"),
        ("config", "System Settings|系统设置|システム設定"),
        ("mes-audit_log", "Audit Log|审计日志|監査ログ"),
    ],
}


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
    "mes-lot-history": (
        "/mes/lot-history",
        "History",
        "tabs",
        ["mes-lot-trace", "mes-trace"],
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
    "mes-check_rule": "Check Rule|卡控规则|チェックルール",
    "mes-check_plan": "Check Plan|卡控方案|チェックプラン",
    "mes-check_binding": "Check Binding|卡控绑定|チェック割当",
    "mes-product": "Product|产品|製品",
    "mes-product_family": "Product Family|产品族|製品ファミリー",
    "mes-tech_node": "Technology Node|工艺节点|テクノロジーノード",
    "mes-material": "Material|物料|資材",
    "mes-material_type": "Material Type|物料类型|資材タイプ",
    "mes-carrier": "Carrier|载具|キャリア",
    "mes-carrier_type": "Carrier Type|载具类型|キャリアタイプ",
    "mes-equipment": "Equipment|设备|設備",
    "mes-equipment_type": "Equipment Type|设备类型|設備タイプ",
    "mes-equipment_group": "Equipment Group|设备组|設備グループ",
    "mes-equipment_capability": "Capability|设备能力|設備能力",
    "mes-e10_state": "E10 State Model|E10 状态模型|E10 状態モデル",
    "mes-e10_auto_rule": "E10 Auto Transition|E10 自动迁移|E10 自動遷移",
    "mes-lot_type": "Lot Type|批次类型|ロットタイプ",
    "mes-lot_priority": "Priority|优先级|優先度",
    "mes-split_merge_rule": "Split / Merge Rule|分批合批规则|分割・統合ルール",
    "mes-site": "Site|工厂|工場",
    "mes-area": "Area|区域|エリア",
    "mes-workcenter": "Work Center|工作中心|ワークセンター",
    "mes-work_calendar": "Work Calendar|工作日历|稼働カレンダー",
    "mes-shift": "Shift|班次|シフト",
    "mes-route": "Route|工艺流程|ルート",
    "mes-operation": "Operation|工序|工程",
    "mes-product_route": "Product Route|产品流程|製品ルート",
    "mes-recipe": "Recipe|配方|レシピ",
    "mes-param_spec": "Parameter Spec|参数规格|パラメータ規格",
    "mes-dc_plan": "DC Plan|数据收集计划|データ収集計画",
    "mes-measurement_item": "Measurement Item|量测项目|測定項目",
    "mes-sampling_rule": "Sampling Rule|抽样规则|サンプリング規則",
    "mes-lot-trace": "Lot History|批次履历|ロット履歴",
    "mes-trace": "Traceability|追溯查询|トレーサビリティ",
    "mes-warehouse": "Warehouse|仓库|倉庫",
    "mes-storage_location": "Storage Location|库位|ロケーション",
    "members": "Users|用户|ユーザー",
    "user-roles": "Roles|角色|ロール",
}


# ---------------- 平台管理控制台（space = platform，仅超级用户） ----------------
# 分组：(key, 标题, 图标, 排序)
PLATFORM_GROUPS: list[tuple[str, str, str, int]] = [
    ("p-g-tenants", "Tenant Management|租户管理|テナント管理", "Building2", 0),
    ("p-g-rbac", "Platform Access|平台权限|プラットフォーム権限", "ShieldCheck", 10),
    (
        "p-g-settings",
        "Platform Settings|平台设置|プラットフォーム設定",
        "SlidersHorizontal",
        20,
    ),
    ("p-g-ops", "Operations & Audit|运维与审计|運用・監査", "ScrollText", 30),
]
# 页面：key -> (分组, 标题, 路径, 图标, 组件)
PLATFORM_ITEMS: dict[str, tuple[str, str, str, str, str]] = {
    "p-tenants": (
        "p-g-tenants",
        "Tenants|租户列表|テナント一覧",
        "/platform/tenants",
        "Building2",
        "platform-tenants",
    ),
    "p-users": (
        "p-g-rbac",
        "Platform Users|平台用户|プラットフォームユーザー",
        "/platform/users",
        "UserCog",
        "users",
    ),
    "p-roles": (
        "p-g-rbac",
        "Platform Roles|平台角色|プラットフォームロール",
        "/platform/roles",
        "Shield",
        "roles",
    ),
    "p-permissions": (
        "p-g-rbac",
        "Permission Tree|权限树|権限ツリー",
        "/platform/permissions",
        "KeyRound",
        "platform-permissions",
    ),
    "p-config": (
        "p-g-settings",
        "Platform Defaults|系统配置（平台默认）|システム設定（既定値）",
        "/platform/config",
        "SlidersHorizontal",
        "platform-config",
    ),
    "p-channels": (
        "p-g-settings",
        "Notification Channels|通知渠道|通知チャネル",
        "/platform/notify-channels",
        "Send",
        "notify-channels",
    ),
    "p-audit": (
        "p-g-ops",
        "Cross-tenant Audit Log|跨租户审计日志|テナント横断監査ログ",
        "/platform/audit",
        "History",
        "platform-audit",
    ),
    "p-login-log": (
        "p-g-ops",
        "Login Log|登录日志|ログイン履歴",
        "/platform/login-log",
        "LogIn",
        "login-log",
    ),
    "p-ops-log": (
        "p-g-ops",
        "Platform Operation Log|平台操作日志|プラットフォーム操作ログ",
        "/platform/ops-log",
        "ScrollText",
        "platform-ops-log",
    ),
}


def tab_keys() -> set[str]:
    """所有合并页签的 key（不再作为独立菜单存在）。"""
    return {k for _, _, _, tabs in MERGED.values() for k in tabs}


def titles(lang_index: int) -> dict[str, str]:
    """菜单 key → 标题。

    Args:
        lang_index: 0 = en，1 = zh-CN，2 = ja。
    """
    out = {k: lbl.split("|")[lang_index] for k, lbl, _, _ in GROUPS}
    for items in ITEMS.values():
        out.update({k: lbl.split("|")[lang_index] for k, lbl in items})
    out.update({k: lbl.split("|")[lang_index] for k, lbl in TAB_TITLES.items()})
    out.update({k: lbl.split("|")[lang_index] for k, lbl, _, _ in PLATFORM_GROUPS})
    out.update({k: v[1].split("|")[lang_index] for k, v in PLATFORM_ITEMS.items()})
    return out
