"""坐标图模块权限。"""

# 规格权限模块：编码 -> ("en|zh|ja" 标签, 排序)
PERM_MODULES: dict[str, tuple[str, int]] = {
    "map": ("Substrate map & bin|坐标图与 bin|座標マップ・ビン", 25)
}
# 额外权限编码（read/write 以外）
PERMISSIONS: dict[str, str] = {
    "mes.map:import": "MES map: import substrate maps / bin definition sets",
}
