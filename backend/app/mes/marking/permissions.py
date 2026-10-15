"""打标权限（D79-7）：``mes.marking:read`` 覆盖模板与作业的读；模板编辑 / 审批单列。

B2 再加 ``mes.marking:exec`` / ``mes.marking:void``。
"""

PERM_MODULES: dict[str, tuple[str, int]] = {
    "marking": ("Marking|打标|マーキング", 33),
    "marking_template": ("Marking template|打标模板|マーキングテンプレート", 34),
}
PERMISSIONS: dict[str, str] = {
    "mes.marking_template:approve": "MES marking template: approve versions",
}
