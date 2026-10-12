"""Permissions of the MES planning module."""

# spec permission modules: code -> ("en|zh|ja" label, sort order)
PERM_MODULES: dict[str, tuple[str, int]] = {"wo": ("Work orders|工单|作業指示", 70)}
# extra (non read/write) permission codes
PERMISSIONS: dict[str, str] = {
    "mes.wo:release": "MES work orders: release / hold / close / cancel",
    "mes.lot:start": "MES lots: start / undo start",
}
