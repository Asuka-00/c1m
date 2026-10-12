"""Permissions of the MES quality module."""

# spec permission modules: code -> ("en|zh|ja" label, sort order)
PERM_MODULES: dict[str, tuple[str, int]] = {"quality": ("Quality|质量|品質", 50)}
# extra (non read/write) permission codes
PERMISSIONS: dict[str, str] = {}
