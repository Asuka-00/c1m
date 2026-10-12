"""Permissions of the MES factory module."""

# spec permission modules: code -> ("en|zh|ja" label, sort order)
PERM_MODULES: dict[str, tuple[str, int]] = {"org": ("Organization|组织|組織", 10)}
# extra (non read/write) permission codes
PERMISSIONS: dict[str, str] = {}
