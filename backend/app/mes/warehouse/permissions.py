"""仓储模块权限。"""

# 规格权限模块：编码 -> ("en|zh|ja" 标签, 排序)
PERM_MODULES: dict[str, tuple[str, int]] = {
    "wh": ("Warehouse|仓储|倉庫", 75),
}
# 额外权限编码（read/write 以外）
PERMISSIONS: dict[str, str] = {
    "mes.wh:confirm": "MES warehouse: confirm / reject finished-goods receipts",
}
