"""产品模块权限。"""

# 规格权限模块：编码 -> ("en|zh|ja" 标签, 排序)
PERM_MODULES: dict[str, tuple[str, int]] = {
    "product": ("Product & material|产品与物料|製品・資材", 30)
}
# 额外权限编码（read/write 以外）
PERMISSIONS: dict[str, str] = {}
