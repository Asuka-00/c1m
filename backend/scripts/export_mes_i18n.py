"""Write the MES i18n bundles (generated from the entity specs) for the frontend.

    uv run python scripts/export_mes_i18n.py [--check]

Output: ../frontend/src/i18n/locales/mes/<lang>.json. --check exits 1 when the
files are stale (also enforced by tests/mes/test_i18n_bundle.py).
"""

import json
import sys
from pathlib import Path

from app.mes.common.meta import LANGS, i18n_bundle
from app.platform.rbac.labels import labels_bundle

OUT = Path(__file__).resolve().parents[2] / "frontend/src/i18n/locales/mes"


def render(lang: str) -> str:
    """MES 标签 + 内置权限 / 角色显示名称（permName.* / roleName.*）。"""
    bundle = {**i18n_bundle(lang), **labels_bundle(lang)}
    return json.dumps(bundle, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    check = "--check" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    stale = []
    for lang in LANGS:
        p = OUT / f"{lang}.json"
        if check:
            if not p.exists() or p.read_text() != render(lang):
                stale.append(p.name)
        else:
            p.write_text(render(lang))
    if stale:
        sys.exit(
            f"stale MES i18n bundles: {', '.join(stale)} (run scripts/export_mes_i18n.py)"
        )


if __name__ == "__main__":
    import app.models  # noqa: F401  (registers specs)

    main()
