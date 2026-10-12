"""System configuration: default registry (seeded idempotently) + value validation.

Two layers: platform values (ConfigItem.value, falling back to default_value) and
per-tenant overrides (TenantConfigValue, RLS) for items with tenant_overridable.
Effective value = tenant override ?? platform value ?? default.
Settings are grouped into ConfigGroups. Add a group/item by extending
DEFAULT_CONFIG; `seed_config` only inserts what is missing and never overwrites
values an admin has changed (names/descriptions/options are refreshed).
"""

import json
import re
from typing import Any

from sqlmodel import Session, select

from app.platform.config.models import ConfigGroup, ConfigItem, ConfigValueType

T = ConfigValueType

# groups whose items tenants may override
TENANT_OVERRIDABLE_GROUPS = {"branding"}

# group code -> (name, name_key, description, order, items)
# item: (code, name, type, default, is_public, options, validation, description)
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
    pass


def validate_value(item: ConfigItem, value: Any) -> Any:
    """Coerce/validate a new value for `item`; None means 'reset to default'."""
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
        if isinstance(value, str):  # accept a JSON document as text too
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                raise ConfigValidationError(f"is not valid JSON ({e.msg})") from e
        return value
    raise ConfigValidationError("has an unsupported type")  # pragma: no cover
