"""Permissions of the MES execution module."""

# spec permission modules: code -> ("en|zh|ja" label, sort order)
PERM_MODULES: dict[str, tuple[str, int]] = {
    "exec": ("Execution|生产执行|生産実行", 80),
    "inventory": ("Line-side material & tools|物料与工具|資材・工具", 85),
    "check": ("Checks|卡控|チェック", 90),
}
# extra (non read/write) permission codes
PERMISSIONS: dict[str, str] = {
    "mes.exec:override": "MES execution: force-override blocking checks",
    "mes.exec:hold": "MES execution: hold / release lots",
    "mes.exec:split": "MES execution: split lots",
    "mes.exec:merge": "MES execution: merge lots",
}
