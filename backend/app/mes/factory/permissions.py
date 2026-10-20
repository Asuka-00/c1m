"""工厂模块权限。"""

# 规格权限模块：编码 -> ("en|zh|ja" 标签, 排序)
PERM_MODULES: dict[str, tuple[str, int]] = {"org": ("Organization", 10)}
# 额外权限编码（read/write 以外）
PERMISSIONS: dict[str, str] = {}
