"""设备模块权限。"""

# 规格权限模块：编码 -> ("en|zh|ja" 标签, 排序)
PERM_MODULES: dict[str, tuple[str, int]] = {"equipment": ("Equipment|设备|設備", 20)}
# 额外权限编码（read/write 以外）
PERMISSIONS: dict[str, str] = {
    "mes.equipment:e10": "MES equipment: change E10 state manually",
    "mes.equipment:pm": "MES equipment: record PM completion",
    "mes.equipment:mount": "MES equipment: mount / unmount material lots",
    "mes.equipment:qual": "MES equipment: record Qual results after PM",
}
