"""Permissions of the MES lot module."""

# spec permission modules: code -> ("en|zh|ja" label, sort order)
PERM_MODULES: dict[str, tuple[str, int]] = {
    "lot": ("Lot & wafer rules|批次与晶圆规则|ロット・ウェーハ規則", 60)
}
# extra (non read/write) permission codes
PERMISSIONS: dict[str, str] = {}
