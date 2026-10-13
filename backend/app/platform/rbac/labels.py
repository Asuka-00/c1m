"""内置权限与角色的三语显示名称（"en|zh|ja"），用于种子数据与前端 i18n 包。"""

from app.core.spec.engine import MODULES, split_label
from app.platform.rbac.permissions import DEFAULT_PERMISSIONS

# 非 MES 权限的显示名称
FIXED: dict[str, str] = {
    "users:read": "View users|查看用户|ユーザー閲覧",
    "users:write": "Edit users|编辑用户|ユーザー編集",
    "users:delete": "Delete users|删除用户|ユーザー削除",
    "roles:read": "View roles & permissions|查看角色与权限|ロール・権限閲覧",
    "roles:write": "Manage roles & permissions|管理角色与权限|ロール・権限管理",
    "tenants:read": "View tenants|查看租户|テナント閲覧",
    "tenants:write": "Manage tenants|管理租户|テナント管理",
    "platform.config:read": "View platform defaults|查看平台默认配置|既定設定閲覧",
    "platform.config:write": "Edit platform defaults|编辑平台默认配置|既定設定編集",
    "platform.notify:read": "View notification channels|查看通知渠道|通知チャネル閲覧",
    "platform.notify:write": "Configure notification channels|配置通知渠道|通知チャネル設定",
    "platform.audit:read": "View audit & logs|查看审计与日志|監査・ログ閲覧",
    "tenant:manage": "Manage tenant|管理租户设置|テナント設定管理",
    "members:read": "View members|查看成员|メンバー閲覧",
    "members:write": "Manage members|管理成员|メンバー管理",
    "config:read": "View configuration|查看系统配置|システム設定閲覧",
    "config:write": "Edit configuration|编辑系统配置|システム設定編集",
    "notify:config": "Configure subscriptions|配置通知订阅|通知購読設定",
}
# MES 操作名称（模块名 + 操作）
ACTIONS: dict[str, str] = {
    "read": "View|查看|閲覧",
    "write": "Edit|编辑|編集",
    "e10": "Change E10 state|变更 E10 状态|E10 状態変更",
    "pm": "Record PM|记录保养|PM 記録",
    "override": "Override checks|强制放行|強制解除",
    "hold": "Hold / release|暂停 / 释放|保留 / 解除",
    "split": "Split lots|分批|ロット分割",
    "merge": "Merge lots|合批|ロット統合",
    "jump": "Jump step|跳站|工程ジャンプ",
    "adjust": "Scrap / bonus|报废 / 补数|廃棄 / 追加",
    "release": "Release / close|下达 / 关闭|発行 / クローズ",
    "start": "Start lots|投产|投入",
    "confirm": "Confirm receipts|确认入库|入庫確認",
}
# 内置角色（平台 + 租户默认角色）的显示名称
ROLE_LABELS: dict[str, str] = {
    "admin": "Administrator|管理员|管理者",
    "user": "User|普通用户|一般ユーザー",
    "owner": "Owner|所有者|オーナー",
    "member": "Member|成员|メンバー",
}


def permission_label(code: str) -> str | None:
    """内置权限的三语名称；未知编码返回 None。"""
    if code in FIXED:
        return FIXED[code]
    res, _, act = code.rpartition(":")
    if res.startswith("mes.") and res[4:] in MODULES and act in ACTIONS:
        m = split_label(MODULES[res[4:]][0])
        a = split_label(ACTIONS[act])
        return "|".join(f"{m[lg]}·{a[lg]}" for lg in ("en", "zh-CN", "ja"))
    return None


def i18n_key(code: str) -> str:
    """权限编码 -> 前端 i18n 键（避开 i18next 的 . 与 : 分隔符）。"""
    return code.replace(".", "_").replace(":", "__")


def labels_bundle(lang: str) -> dict[str, dict[str, str]]:
    """前端 i18n 包：``permName.<key>`` 与 ``roleName.<code>``。"""
    perms = {}
    for code in DEFAULT_PERMISSIONS:
        lbl = permission_label(code)
        if lbl:
            perms[i18n_key(code)] = split_label(lbl)[lang]
    roles = {k: split_label(v)[lang] for k, v in ROLE_LABELS.items()}
    return {"permName": perms, "roleName": roles}
