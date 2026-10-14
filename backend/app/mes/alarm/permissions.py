"""报警模块权限（mes.alarm:read / mes.alarm:write）。"""

# 规格权限模块：编码 -> ("en|zh|ja" 标签, 排序)
PERM_MODULES: dict[str, tuple[str, int]] = {
    "alarm": ("Equipment alarms|设备报警|設備アラーム", 22)
}
# 额外权限编码（read/write 以外）
PERMISSIONS: dict[str, str] = {}
