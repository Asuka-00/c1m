"""计划模块权限。"""

# 规格权限模块：编码 -> ("en|zh|ja" 标签, 排序)
PERM_MODULES: dict[str, tuple[str, int]] = {"wo": ("Work orders", 70)}
# 额外权限编码（read/write 以外）
PERMISSIONS: dict[str, str] = {
    "mes.wo:release": "MES work orders: release / hold / close / cancel",
    "mes.lot:start": "MES lots: start / undo start",
}
