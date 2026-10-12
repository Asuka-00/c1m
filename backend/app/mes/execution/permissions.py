"""执行模块权限（exec:read/write/override/hold/split/merge）。"""

# 规格权限模块：编码 -> ("en|zh|ja" 标签, 排序)
PERM_MODULES: dict[str, tuple[str, int]] = {
    "exec": ("Execution|生产执行|生産実行", 80),
    "inventory": ("Line-side material & tools|物料与工具|資材・工具", 85),
    "check": ("Checks|卡控|チェック", 90),
}
# 额外权限编码（read/write 以外）
PERMISSIONS: dict[str, str] = {
    "mes.exec:override": "MES execution: force-override blocking checks",
    "mes.exec:hold": "MES execution: hold / release lots",
    "mes.exec:split": "MES execution: split lots",
    "mes.exec:merge": "MES execution: merge lots",
    "mes.exec:jump": "MES execution: jump a lot to another step",
}
