"""工作区（租户空间）的菜单、权限与角色名称不得出现“租户 / tenant / テナント”。"""

import re

from app.platform.menus import layout
from app.platform.rbac.labels import ROLE_LABELS, permission_label
from app.platform.rbac.permissions import TENANT_PERMISSIONS

TENANT = re.compile(r"租户|tenant|テナント", re.I)


def test_workspace_menu_titles_neutral() -> None:
    platform = {k for k, *_ in layout.PLATFORM_GROUPS} | set(layout.PLATFORM_ITEMS)
    for lang in range(3):
        bad = {
            k: v
            for k, v in layout.titles(lang).items()
            if k not in platform and TENANT.search(v)
        }
        assert bad == {}


def test_workspace_permission_and_role_labels_neutral() -> None:
    for code in TENANT_PERMISSIONS:
        assert not TENANT.search(permission_label(code) or ""), code
    for name in ("owner", "member"):
        assert not TENANT.search(ROLE_LABELS[name]), name
