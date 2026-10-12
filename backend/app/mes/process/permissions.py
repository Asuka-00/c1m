"""Permissions of the MES process module."""

# spec permission modules: code -> ("en|zh|ja" label, sort order)
PERM_MODULES: dict[str, tuple[str, int]] = {"process": ("Process|工艺|プロセス", 40)}
# extra (non read/write) permission codes
PERMISSIONS: dict[str, str] = {}
