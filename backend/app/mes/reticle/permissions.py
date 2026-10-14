"""光罩权限（P3-B4，D64 / D67 / D68）：mes.reticle:read / write / override。

override：进站待检放行、restore、life-reset、scrap。P3 不给 eap_service 任何光罩写权限（D67）。
"""

# 规格权限模块：编码 -> ("en|zh|ja" 标签, 排序)
PERM_MODULES: dict[str, tuple[str, int]] = {"reticle": ("Reticle|光罩|レチクル", 32)}
# 额外权限编码（read/write 以外）；三语名称由 rbac.labels 按 模块 + 操作 生成
PERMISSIONS: dict[str, str] = {
    "mes.reticle:override": "MES reticle: restore / life reset / scrap / override inspection due",
}
