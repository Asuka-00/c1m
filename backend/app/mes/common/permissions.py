"""Permissions of the MES common module."""

# spec permission modules: code -> ("en|zh|ja" label, sort order)
PERM_MODULES: dict[str, tuple[str, int]] = {"common": ("Common|通用|共通", 0)}
# extra (non read/write) permission codes
PERMISSIONS: dict[str, str] = {}
