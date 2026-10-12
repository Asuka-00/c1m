"""Permissions of the MES product module."""

# spec permission modules: code -> ("en|zh|ja" label, sort order)
PERM_MODULES: dict[str, tuple[str, int]] = {
    "product": ("Product & material|产品与物料|製品・資材", 30)
}
# extra (non read/write) permission codes
PERMISSIONS: dict[str, str] = {}
