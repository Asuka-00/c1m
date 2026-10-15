"""系统配置：默认配置注册表（幂等同步）与值校验。

两层：平台值（ConfigItem.value，回退 default_value）与租户覆盖值（TenantConfigValue，受 RLS
保护，仅 tenant_overridable 的配置项）。有效值 = 租户覆盖 ?? 平台值 ?? 默认值。
新增分组 / 配置项时扩展 DEFAULT_CONFIG；``seed_config`` 只补缺失项，不覆盖管理员修改过的值
（名称 / 描述 / 选项会刷新）。
"""

import json
import re
from typing import Any

from sqlmodel import Session, select

from app.platform.config.models import ConfigGroup, ConfigItem, ConfigValueType

T = ConfigValueType

# 租户可覆盖其配置项的分组
TENANT_OVERRIDABLE_GROUPS = {"branding"}

# 分组编码 -> (名称, name_key, 描述, 排序, 配置项)
# 配置项：(编码, 名称, 类型, 默认值, 是否公开, 选项, 校验, 描述)
DEFAULT_CONFIG: dict[str, tuple[str, str, str, int, list[tuple[Any, ...]]]] = {
    "branding": (
        "产品品牌",
        "config.groups.branding",
        "Product name, logo and footer shown on the login page, sidebar and browser tab.",
        0,
        [
            (
                "app_name",
                "App name",
                T.string,
                "FastAPI Admin",
                True,
                None,
                {"required": True, "max_length": 60},
                "Shown on the login page, sidebar and browser title.",
            ),
            (
                "app_subtitle",
                "Subtitle",
                T.string,
                "",
                True,
                None,
                {"max_length": 120},
                "Optional tagline under the name.",
            ),
            (
                "logo",
                "Logo",
                T.image,
                None,
                True,
                None,
                None,
                "Square image (PNG/SVG/WebP), shown in the sidebar and on the login page.",
            ),
            (
                "favicon",
                "Favicon",
                T.image,
                None,
                True,
                None,
                None,
                "Browser tab icon (ICO/PNG/SVG).",
            ),
            (
                "login_background",
                "Login background",
                T.image,
                None,
                True,
                None,
                None,
                "Optional background image for the login page.",
            ),
            (
                "primary_color",
                "Accent color",
                T.color,
                "",
                True,
                None,
                None,
                "Brand accent color applied to the theme (empty = default theme).",
            ),
            (
                "footer_copyright",
                "Footer copyright",
                T.text,
                "© FastAPI Admin",
                True,
                None,
                {"max_length": 300},
                "Shown in the footer of the login page and the app.",
            ),
            (
                "support_url",
                "Support URL",
                T.url,
                "",
                True,
                None,
                None,
                "Optional help / support link in the footer.",
            ),
        ],
    ),
    "security": (
        "安全",
        "config.groups.security",
        "Platform sign-in policies (stored settings; platform admins only).",
        10,
        [
            (
                "session_minutes",
                "Session length (minutes)",
                T.number,
                11520,
                False,
                None,
                {"min": 5, "max": 525600},
                "Access token lifetime for new sign-ins.",
            ),
            (
                "allow_signup",
                "Allow self sign-up",
                T.boolean,
                True,
                False,
                None,
                None,
                "Allow new users to register themselves.",
            ),
            (
                "password_policy",
                "Password policy",
                T.select,
                "standard",
                False,
                [
                    {"value": "basic", "label": "Basic (8+)"},
                    {"value": "standard", "label": "Standard (8+, letters & digits)"},
                    {"value": "strict", "label": "Strict (12+, mixed)"},
                ],
                None,
                None,
            ),
            (
                "extra",
                "Advanced (JSON)",
                T.json,
                {},
                False,
                None,
                None,
                "Free-form JSON options.",
            ),
        ],
    ),
}


def seed_config(session: Session) -> None:
    """幂等同步默认配置分组与配置项（保留已设置的值）。"""
    groups = {g.code: g for g in session.exec(select(ConfigGroup)).all()}
    for gcode, (name, name_key, desc, order, items) in DEFAULT_CONFIG.items():
        g = groups.get(gcode)
        if not g:
            g = ConfigGroup(
                code=gcode,
                name=name,
                name_key=name_key,
                description=desc,
                sort_order=order,
            )
            session.add(g)
            session.flush()
        g.name, g.name_key, g.description, g.sort_order = name, name_key, desc, order
        have = {i.code: i for i in g.items}
        for idx, (
            code,
            iname,
            vtype,
            default,
            public,
            options,
            validation,
            idesc,
        ) in enumerate(items):
            it = have.get(code)
            if not it:
                it = ConfigItem(group_id=g.id, code=code, name=iname, value=default)
                session.add(it)
            it.name, it.value_type, it.default_value = iname, vtype, default
            it.is_public, it.options, it.validation, it.description = (
                public,
                options,
                validation,
                idesc,
            )
            it.sort_order = idx * 10
            it.tenant_overridable = gcode in TENANT_OVERRIDABLE_GROUPS
    session.commit()


_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")
_URL = re.compile(r"^(https?://[^\s]+|/[^\s]*)$")


class ConfigValidationError(ValueError):
    """配置值校验失败。"""

    pass


def validate_value(item: ConfigItem, value: Any) -> Any:
    """校验并转换配置项的新值。

    Args:
        item: 配置项。
        value: 新值；None 表示恢复默认。

    Returns:
        规范化后的值。

    Raises:
        ConfigValidationError: 类型、范围、选项或格式不符。
    """
    rules = item.validation or {}
    t = item.value_type
    if value is None:
        if rules.get("required") and item.default_value in (None, ""):
            raise ConfigValidationError("is required")
        return item.default_value
    if t in (T.string, T.text, T.color, T.url, T.image, T.file, T.select):
        if not isinstance(value, str):
            raise ConfigValidationError("must be a string")
        value = value.strip() if t != T.text else value
        if rules.get("required") and not value:
            raise ConfigValidationError("is required")
        if (mx := rules.get("max_length")) and len(value) > mx:
            raise ConfigValidationError(f"must be at most {mx} characters")
        if value and t == T.color and not _COLOR.match(value):
            raise ConfigValidationError("must be a hex color like #1e40af")
        if value and t in (T.url, T.image, T.file) and not _URL.match(value):
            raise ConfigValidationError("must be an http(s) URL or an absolute path")
        if t == T.select and value not in {o["value"] for o in item.options or []}:
            raise ConfigValidationError("is not one of the allowed options")
        return value
    if t == T.number:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ConfigValidationError("must be a number")
        if (mn := rules.get("min")) is not None and value < mn:
            raise ConfigValidationError(f"must be >= {mn}")
        if (mx := rules.get("max")) is not None and value > mx:
            raise ConfigValidationError(f"must be <= {mx}")
        return value
    if t == T.boolean:
        if not isinstance(value, bool):
            raise ConfigValidationError("must be true or false")
        return value
    if t == T.json:
        if isinstance(value, str):  # 也接受文本形式的 JSON 文档
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                raise ConfigValidationError(f"is not valid JSON ({e.msg})") from e
        return value
    raise ConfigValidationError("has an unsupported type")  # pragma: no cover
