"""前端实体元数据与 i18n 包生成（唯一来源：规格中的三语标签）。"""

from typing import Any

from app.core.spec.engine import (
    ENTITIES,
    ENUMS,
    MODULES,
    Entity,
    label_of,
    perm,
    split_label,
)
from app.platform.menus.service import titles

LANGS = ("zh-CN", "ja", "en")


def field_meta(e: Entity) -> list[dict[str, Any]]:
    """字段元数据（类型、标签、必填、枚举、引用等）。"""
    out = []
    for f in e.all_fields:
        out.append(
            {
                "name": f.name,
                "column": f.column,
                "type": f.type,
                "required": f.required,
                "required_when": f.required_when,
                "default_from": f.default_from,
                "auto": f.auto,
                "system": f.system,
                "enum": f.enum,
                "ref": f.ref,
                "list": f.list,
                "filter": f.filterable,
                "search": f.search,
                "default": f.default,
                "max_length": f.max_length if f.type == "str" else None,
                "help": bool(f.help),
                "depends": f.depends,
                "ref_filter": f.ref_filter,
            }
        )
    return out


def entity_meta(e: Entity) -> dict[str, Any]:
    """实体元数据（字段、权限模块、树/版本标记、子表等）。"""
    return {
        "code": e.code,
        "module": e.module,
        "url": e.url,
        "has_code": e.has_code,
        "tree": e.tree,
        "versioned": e.versioned,
        "readonly": e.readonly,
        "parent": e.parent,
        "children": e.children,
        "label_field": e.label_field,
        "sort_default": e.sort_default,
        "natural_key": list(e.natural_key),
        "read": perm(e.pmod, "read"),
        "write": perm(e.pmod, "write"),
        "fields": field_meta(e),
    }


def all_meta() -> dict[str, Any]:
    """全部对外实体及枚举的元数据（``GET /mes/_meta``）。"""
    return {
        "modules": [
            {"code": m, "order": o}
            for m, (_, o) in sorted(MODULES.items(), key=lambda x: x[1][1])
        ],
        "entities": [entity_meta(e) for e in ENTITIES.values() if not e.internal],
        "enums": {k: [v for v, _ in vals] for k, vals in ENUMS.items()},
    }


def i18n_bundle(lang: str) -> dict[str, Any]:
    """生成某语言的 i18n 包。

    Args:
        lang: 语言代码（en / zh-CN / ja）。

    Returns:
        ``{"mes": {...}, "menu": {...}}``，合并进前端语言包。
    """

    def pick(s: str) -> str:
        return split_label(s)[lang]

    ents: dict[str, Any] = {}
    fields: dict[str, Any] = {}
    helps: dict[str, Any] = {}
    menu: dict[str, str] = {}
    for e in ENTITIES.values():
        if e.internal:
            continue
        ents[e.code] = pick(e.label)
        fields[e.code] = {f.name: pick(label_of(f)) for f in e.all_fields}
        hs = {f.name: pick(f.help) for f in e.all_fields if f.help}
        if hs:
            helps[e.code] = hs
    menu.update(titles(["en", "zh-CN", "ja"].index(lang)))
    return {
        "mes": {
            "module": {m: pick(lbl) for m, (lbl, _) in MODULES.items()},
            "entity": ents,
            "field": fields,
            "help": helps,
            "enum": {
                k: {v: pick(lbl) for v, lbl in vals}
                for k, vals in ENUMS.items()
                if k != "entity_type"
            },
        },
        "menu": menu,
    }
