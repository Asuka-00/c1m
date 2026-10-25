"""执行模块权限（exec:read/write/override/hold/split/merge/bank、ncr:approve）。"""

# 规格权限模块：编码 -> ("en|zh|ja" 标签, 排序)
PERM_MODULES: dict[str, tuple[str, int]] = {
    "exec": ("Execution", 80),
    "ncr": ("NCR / MRB", 82),
    "inventory": ("Line-side material & tools", 85),
    "check": ("Checks", 90),
}
# 额外权限编码（read/write 以外）
PERMISSIONS: dict[str, str] = {
    "mes.exec:override": "MES execution: force-override blocking checks",
    "mes.exec:hold": "MES execution: hold / release lots",
    "mes.exec:split": "MES execution: split lots",
    "mes.exec:merge": "MES execution: merge lots",
    "mes.exec:jump": "MES execution: jump a lot to another step",
    "mes.exec:adjust": "MES execution: in-process scrap / bonus",
    "mes.exec:bank": "MES execution: bank in / issue lots from bank",
    "mes.ncr:approve": "MES NCR: approve / reject dispositions",
}
