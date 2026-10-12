"""Permissions of the MES equipment module."""

# spec permission modules: code -> ("en|zh|ja" label, sort order)
PERM_MODULES: dict[str, tuple[str, int]] = {"equipment": ("Equipment|设备|設備", 20)}
# extra (non read/write) permission codes
PERMISSIONS: dict[str, str] = {}
