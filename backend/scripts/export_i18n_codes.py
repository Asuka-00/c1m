"""导出后端对外的全部显示 code，供前端校验语言包是否齐全（不含任何显示文案）。

    uv run python scripts/export_i18n_codes.py [--check]

输出 ../frontend/src/i18n/backend-codes.json：前端语言包必须提供译文的 i18n 键（排序后的数组），
包括实体 / 字段 / 枚举 / 菜单 / 权限 / 角色 / 通知、检查结果说明（``mes.checkMsg.*``）与业务错误码
（``mes.err.code.*``）。
显示文案只在前端语言包（``frontend/src/i18n/locales``）维护；前端 ``pnpm i18n:check``
校验每个键在三种语言中都有译文。``--check`` 在文件过期时返回 1（测试同样会检查）。
"""

import ast
import json
import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend/src"
OUT = FRONTEND / "i18n/backend-codes.json"
TS_OUT = FRONTEND / "lib/error-codes.ts"
APP = Path(__file__).resolve().parents[1] / "app"


def _literal(n: ast.AST | None) -> str | None:
    return n.value if isinstance(n, ast.Constant) and isinstance(n.value, str) else None


def note_keys() -> set[str]:
    """源码中的系统说明 key：``{"key": "...", "params": ...}`` 字典字面量。"""
    out: set[str] = set()
    for p in APP.rglob("*.py"):
        if "tests" in p.parts:
            continue
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Dict):
                keys = [k.value for k in n.keys if isinstance(k, ast.Constant)]
                if {"key", "params"} <= set(keys):
                    if note := _literal(n.values[keys.index("key")]):
                        out.add(note)
    return out


def codes() -> list[str]:
    """后端暴露给前端翻译的全部 i18n 键。"""
    import app.main  # noqa: F401  （导入全部模块：规格、路由与各服务的消息模板）
    from app.core import error_codes as ec
    from app.core import registry
    from app.core.spec.engine import ENTITIES, ENUMS, MODULES
    from app.mes.execution.checks.service import MESSAGES
    from app.mes.execution.seed import SYSTEM_REASONS
    from app.platform.config.service import DEFAULT_CONFIG
    from app.platform.menus.layout import (
        GROUPS,
        ITEMS,
        PLATFORM_GROUPS,
        PLATFORM_ITEMS,
        TAB_TITLES,
    )
    from app.platform.notification.channels import CHANNELS
    from app.platform.notification.events import EVENT_TYPES
    from app.platform.rbac.labels import (
        ROLE_DESCRIPTIONS,
        ROLE_LABELS,
        permission_label,
    )
    from app.platform.rbac.permissions import DEFAULT_PERMISSIONS

    registry.load()
    keys = {f"mes.module.{m}" for m in MODULES}
    for e in ENTITIES.values():
        if e.internal:
            continue
        keys.add(f"mes.entity.{e.code}")
        for f in e.all_fields:
            keys.add(f"mes.field.{e.code}.{f.name}")
            if f.help:
                keys.add(f"mes.help.{e.code}.{f.name}")
    for name, vals in ENUMS.items():
        if name != "entity_type":  # 实体类型用 mes.entity.*
            keys |= {f"mes.enum.{name}.{v}" for v, _ in vals}
    menus = [g for g, *_ in GROUPS] + [k for items in ITEMS.values() for k, _ in items]
    menus += [*TAB_TITLES, *(g for g, *_ in PLATFORM_GROUPS), *PLATFORM_ITEMS]
    keys |= {f"menu.{k}" for k in menus}
    for code in DEFAULT_PERMISSIONS:
        if permission_label(code):
            k = code.replace(".", "_").replace(":", "__")
            keys |= {f"permName.{k}", f"permDesc.{k}"}
    keys |= {f"roleName.{r}" for r in ROLE_LABELS}
    keys |= {f"roleDesc.{r.replace('.', '_')}" for r in ROLE_DESCRIPTIONS}
    keys |= {f"notify.event.{c}.label" for c in EVENT_TYPES}
    keys |= {f"notify.event.{c}.title" for c in EVENT_TYPES}
    keys |= {f"mes.reasonCode.{code}" for _, code, _ in SYSTEM_REASONS}
    for g, (_, _, _, _, items) in DEFAULT_CONFIG.items():
        keys |= {f"config.groups.{g}", f"config.groupDescs.{g}"}
        for it in items:
            keys.add(f"config.items.{g}.{it[0]}")
            if it[7]:
                keys.add(f"config.itemDescs.{g}.{it[0]}")
            if it[2] == "select":
                keys |= {
                    f"config.options.{g}.{it[0]}.{o['value']}" for o in it[5] or []
                }
    keys |= {f"notify.channel.{c}" for c in CHANNELS}
    keys |= {f"mes.checkMsg.{k}" for k in MESSAGES}
    keys |= {f"mes.sysNote.{k}" for k in note_keys()}
    keys |= {f"error.code_{c}" for c in ec.CODES}
    return sorted(keys)


def render() -> str:
    """清单文件内容。"""
    return json.dumps(codes(), ensure_ascii=False, indent=2) + "\n"


def render_ts() -> str:
    """前端错误码常量（对应后端 ``app/core/error_codes.py``）。"""
    from app.core import error_codes as ec

    body = "\n".join(f"  {name}: {code}," for code, name in sorted(ec.CODES.items()))
    return (
        "/** 后端错误码常量：由 backend/scripts/export_i18n_codes.py 从 app/core/error_codes.py 生成，勿手改。 */\n"
        f"export const ErrorCode = {{\n{body}\n}} as const\n"
    )


def main() -> None:
    outputs = {OUT: render(), TS_OUT: render_ts()}
    if "--check" in sys.argv:
        for path, text in outputs.items():
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                sys.exit(f"stale {path.name} (run scripts/export_i18n_codes.py)")
        return
    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.name} and {TS_OUT.name}")  # noqa: T201


if __name__ == "__main__":
    main()
