"""导航布局：业务域菜单分组与菜单标题（"en|zh|ja"）。

纯数据（不导入数据库 / 模型），供菜单同步与 i18n 包导出共同使用。每个菜单 key 只出现一次；
路径 / 图标 / 组件 / 权限由各模块的菜单定义提供。
"""

# 分组 key、标题、图标、排序。
# 顺序遵循 MES 常规：工作台 → 日常作业（执行 / 在制报表 / 计划 / 仓储 / 设备 / 质量）
# → 主数据（工艺 / 卡控 / 产品物料 / 设备主数据 / 工厂 / 批次规则 / 基础数据）→ 系统。
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
    ("g-check", "Check Control|卡控管理|チェック管理", "ShieldAlert", 75),
    ("g-product", "Product & Material|产品与物料|製品・資材", "Package", 80),
    ("g-eqp-master", "Equipment Master|设备主数据|設備マスタ", "ServerCog", 85),
    ("g-factory", "Factory Modeling|工厂建模|工場モデリング", "Factory", 90),
    ("g-lot", "Lot Rules|批次规则|ロット規則", "Layers", 95),
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
        ("mes-hold-release", "Batch Hold Release|批量释放 Hold|ホールド一括解除"),
        ("mes-lot", "Lot List|批次列表|ロット一覧"),
        ("mes-wafer", "Wafer|晶圆|ウェーハ"),
    ],
    "g-wip": [
        ("mes-wip-dashboard", "WIP Dashboard|WIP 看板|WIP ダッシュボード"),
        ("mes-oee-report", "Equipment OEE|设备 OEE|設備 OEE"),
        ("mes-trace", "Traceability|追溯查询|トレーサビリティ"),
        ("mes-lot-trace", "Lot History|批次履历|ロット履歴"),
        ("mes-check_log", "Check Log|卡控记录|チェック記録"),
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
        ("mes-warehouse", "Warehouse|仓库|倉庫"),
        ("mes-storage_location", "Storage Location|库位|ロケーション"),
    ],
    "g-equipment": [
        ("mes-eqp-board", "Equipment Status Board|设备状态看板|設備状態ボード"),
        ("mes-pm_plan", "PM Plan|PM 计划|PM 計画"),
        ("mes-downtime", "Downtime|停机记录|停止記録"),
        ("mes-e10_history", "E10 History|E10 状态履历|E10 状態履歴"),
        ("mes-tool", "Tool Life|工具寿命|工具寿命"),
    ],
    "g-quality": [
        ("mes-dc_result", "DC Data|量测数据|測定データ"),
        ("mes-dc_plan", "DC Plan|数据收集计划|データ収集計画"),
        ("mes-measurement_item", "Measurement Item|量测项目|測定項目"),
        ("mes-sampling_rule", "Sampling Rule|抽样规则|サンプリング規則"),
        ("mes-defect_code", "Defect Code|缺陷代码|欠陥コード"),
    ],
    "g-process": [
        ("mes-route", "Route|工艺流程|ルート"),
        ("mes-operation", "Operation|工序|工程"),
        ("mes-product_route", "Product Route|产品流程|製品ルート"),
        ("mes-recipe", "Recipe|配方|レシピ"),
        ("mes-param_spec", "Parameter Spec|参数规格|パラメータ規格"),
        ("mes-qtime_rule", "Q-Time Rule|Q-Time 规则|Q タイムルール"),
    ],
    "g-check": [
        ("mes-check_binding", "Check Binding|卡控绑定|チェック割当"),
        ("mes-check_plan", "Check Plan|卡控方案|チェックプラン"),
        ("mes-check_rule", "Check Rule|卡控规则|チェックルール"),
    ],
    "g-product": [
        ("mes-product", "Product|产品|製品"),
        ("mes-product_family", "Product Family|产品族|製品ファミリー"),
        ("mes-tech_node", "Technology Node|工艺节点|テクノロジーノード"),
        ("mes-material", "Material|物料|資材"),
        ("mes-material_type", "Material Type|物料类型|資材タイプ"),
        ("mes-carrier", "Carrier|载具|キャリア"),
        ("mes-carrier_type", "Carrier Type|载具类型|キャリアタイプ"),
        ("mes-reticle", "Reticle|光罩|レチクル"),
        ("mes-fixture", "Fixture|治具|治具"),
    ],
    "g-eqp-master": [
        ("mes-equipment", "Equipment|设备|設備"),
        ("mes-equipment_type", "Equipment Type|设备类型|設備タイプ"),
        ("mes-equipment_group", "Equipment Group|设备组|設備グループ"),
        ("mes-equipment_capability", "Capability|设备能力|設備能力"),
        ("mes-e10_state", "E10 State Model|E10 状态模型|E10 状態モデル"),
        ("mes-e10_auto_rule", "E10 Auto Transition|E10 自动迁移|E10 自動遷移"),
    ],
    "g-factory": [
        ("mes-site", "Site|工厂|工場"),
        ("mes-area", "Area|区域|エリア"),
        ("mes-workcenter", "Work Center|工作中心|ワークセンター"),
        ("mes-shift", "Shift|班次|シフト"),
        ("mes-work_calendar", "Work Calendar|工作日历|稼働カレンダー"),
    ],
    "g-lot": [
        ("mes-lot_type", "Lot Type|批次类型|ロットタイプ"),
        ("mes-lot_priority", "Priority|优先级|優先度"),
        ("mes-split_merge_rule", "Split / Merge Rule|分批合批规则|分割・統合ルール"),
    ],
    "g-master": [
        ("mes-reason_code", "Reason Code|原因代码|理由コード"),
        ("mes-code_rule", "Code Rule|编码规则|採番ルール"),
        ("mes-uom", "UOM|计量单位|単位"),
        ("mes-dict_type", "Dictionary|数据字典|データ辞書"),
        ("mes-attr_def", "Custom Attribute|自定义属性|カスタム属性"),
    ],
    "g-system": [
        ("users", "Users|用户|ユーザー"),
        ("roles", "Roles|角色|ロール"),
        ("permissions", "Permissions|权限|権限"),
        ("tenants", "Tenants|租户|テナント"),
        ("members", "Members|成员|メンバー"),
        ("tenant-roles", "Tenant Roles|租户角色|テナントロール"),
        ("notify-subscriptions", "Notification Subscriptions|通知订阅|通知購読"),
        ("config", "Configuration|系统配置|システム設定"),
        ("menus", "Menus|菜单|メニュー"),
        ("mes-audit_log", "Audit Log|审计日志|監査ログ"),
    ],
}

# 已废弃系统分组的 key（同步时删除）
OBSOLETE_PREFIXES = ("mes-g-",)
OBSOLETE_KEYS = {"general", "tenant", "admin", "other"}


def titles(lang_index: int) -> dict[str, str]:
    """菜单 key → 标题。

    Args:
        lang_index: 0 = en，1 = zh-CN，2 = ja。
    """
    out = {k: lbl.split("|")[lang_index] for k, lbl, _, _ in GROUPS}
    for items in ITEMS.values():
        out.update({k: lbl.split("|")[lang_index] for k, lbl in items})
    return out
