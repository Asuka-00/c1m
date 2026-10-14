"""报警模块权限（mes.alarm:read / mes.alarm:write）。"""

# 规格权限模块：编码 -> ("en|zh|ja" 标签, 排序)
PERM_MODULES: dict[str, tuple[str, int]] = {
    "alarm": ("Equipment alarms|设备报警|設備アラーム", 22)
}
# 额外权限编码（read/write 以外）
PERMISSIONS: dict[str, str] = {
    # D54-1：EAP 写入入口，只给服务账号（租户角色 eap_service），不进 owner / admin
    "mes.eap:write": "MES EAP: post equipment events (service accounts only)",
    # D65：EAP 服务账号只读设备 / 报警码 / E10 状态（列表 + 详情），不放开其他主数据
    "mes.eap:read_master": "MES EAP: read equipment, alarm codes and E10 states (service accounts only)",
}
