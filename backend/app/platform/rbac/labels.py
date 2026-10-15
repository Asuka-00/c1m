"""内置权限与角色的三语显示名称（"en|zh|ja"），用于种子数据与前端 i18n 包。"""

from app.core.spec.engine import MODULES, split_label
from app.platform.rbac.permissions import DEFAULT_PERMISSIONS

# 非 MES 权限的显示名称
FIXED: dict[str, str] = {
    "mes.eap:write": "EAP events (service account)|EAP 事件写入（服务账号）|EAP イベント書込（サービスアカウント）",
    "mes.eap:read_master": "EAP master data read (service account)|EAP 主数据只读（服务账号）|EAP マスタ参照（サービスアカウント）",
    "users:read": "View platform users|查看平台用户|プラットフォームユーザー閲覧",
    "users:write": "Edit platform users|编辑平台用户|プラットフォームユーザー編集",
    "users:delete": "Delete platform users|删除平台用户|プラットフォームユーザー削除",
    "roles:read": "View roles & permissions|查看角色与权限|ロール・権限閲覧",
    "roles:write": "Manage roles & permissions|管理角色与权限|ロール・権限管理",
    "tenants:read": "View tenants|查看租户|テナント閲覧",
    "tenants:write": "Manage tenants|管理租户|テナント管理",
    "platform.config:read": "View platform defaults|查看平台默认配置|既定設定閲覧",
    "platform.config:write": "Edit platform defaults|编辑平台默认配置|既定設定編集",
    "platform.notify:read": "View notification channels|查看通知渠道|通知チャネル閲覧",
    "platform.notify:write": "Configure notification channels|配置通知渠道|通知チャネル設定",
    "platform.audit:read": "View audit & logs|查看审计与日志|監査・ログ閲覧",
    "tenant:manage": "Manage system settings & admins|管理系统设置与管理员|システム設定・管理者の管理",
    "members:read": "View users|查看用户|ユーザー閲覧",
    "members:write": "Manage users|管理用户|ユーザー管理",
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
    "activate": "Activate / void|生效 / 作废|有効化 / 無効化",
    "mount": "Mount / unmount material|上料 / 卸料|資材装着 / 取外し",
    "qual": "Record Qual result|登记 Qual 结果|Qual 結果登録",
    "tool_mount": "Mount / unmount tools|工具装卸 / 更换|工具装着 / 取外し",
    "tool_count": "Report / reset tool usage|工具计数上报 / 重置|工具カウント報告 / リセット",
    "transform": "Unit transform|单位转换|単位変換",
    "import": "Import maps / bin sets|导入坐标图 / bin 定义|マップ・ビン定義インポート",
}
# 内置角色（平台 + 租户默认角色）的显示名称；工作区不出现“租户”字样，owner 显示为系统管理员
ROLE_LABELS: dict[str, str] = {
    "admin": "Administrator|管理员|管理者",
    "user": "User|普通用户|一般ユーザー",
    "owner": "System admin|系统管理员|システム管理者",
    "member": "Standard user|普通用户|一般ユーザー",
    "eap_service": "EAP service account|EAP 服务账号|EAP サービスアカウント",
}


# 内置角色说明（"en|zh|ja"）：平台角色键为 ``platform.<code>``，工作区默认角色键为 ``<code>``
ROLE_DESCRIPTIONS: dict[str, str] = {
    "platform.admin": "Platform administrator with all permissions|拥有全部权限的平台管理员|全権限を持つプラットフォーム管理者",
    "platform.user": "Regular user without platform permissions|无平台权限的普通用户|プラットフォーム権限のない一般ユーザー",
    "owner": "System administrator with all permissions|拥有全部权限的系统管理员|全権限を持つシステム管理者",
    "admin": "Manages users, settings and all business data|管理用户、系统设置与全部业务数据|ユーザー・設定・全業務データを管理",
    "member": "Read-only access to business data|只读访问业务数据|業務データの閲覧のみ",
    "eap_service": "Posts equipment events via /mes/eap/events; reads equipment, alarm codes and E10 states|调用 /mes/eap/events 写设备事件；只读设备、报警码、E10 状态|/mes/eap/events での設備イベント書込、設備・アラームコード・E10 状態の参照",
}
# 内置权限说明的模板（{label} 为该语言的权限名称）
PERM_DESC_TEMPLATE = "Allows: {label}|允许：{label}|許可：{label}"


def role_description_key(name: str, platform: bool) -> str:
    """内置角色说明的键（不存在时调用方应保留数据库中的说明）。"""
    return f"platform.{name}" if platform else name


def permission_description(code: str) -> str | None:
    """内置权限的三语说明（由权限名称生成）；未知编码返回 None。"""
    lbl = permission_label(code)
    if not lbl:
        return None
    tpl = PERM_DESC_TEMPLATE.split("|")
    return "|".join(t.format(label=x) for t, x in zip(tpl, lbl.split("|"), strict=True))


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
    """前端 i18n 包：``permName`` / ``roleName`` / ``permDesc`` / ``roleDesc``。"""
    perms = {}
    for code in DEFAULT_PERMISSIONS:
        lbl = permission_label(code)
        if lbl:
            perms[i18n_key(code)] = split_label(lbl)[lang]
    roles = {k: split_label(v)[lang] for k, v in ROLE_LABELS.items()}
    pdesc = {}
    for code in DEFAULT_PERMISSIONS:
        d = permission_description(code)
        if d:
            pdesc[i18n_key(code)] = split_label(d)[lang]
    rdesc = {
        k.replace(".", "_"): split_label(v)[lang] for k, v in ROLE_DESCRIPTIONS.items()
    }
    return {"permName": perms, "roleName": roles, "permDesc": pdesc, "roleDesc": rdesc}
