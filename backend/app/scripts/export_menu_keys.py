"""导出菜单 key 清单（FE-02 / F2），不连数据库。

    uv run python -m app.scripts.export_menu_keys [--out [PATH]] [--check [PATH]]

默认写到 stdout；``--out`` 写文件；``--check`` 与已有文件比较，不一致退出 1。
不带 PATH 时用仓库内提交的 ``app/platform/menus/menu_keys.json``（前端据此对齐，测试校验它是最新的）。
格式见 :func:`app.platform.menus.service.menu_keys`。
"""

import argparse
import json
import sys
from pathlib import Path

from app.platform.menus.service import menu_keys

COMMITTED = (
    Path(__file__).resolve().parents[1] / "platform" / "menus" / "menu_keys.json"
)


def render() -> str:
    """规范化 JSON（UTF-8、缩进 2、末尾换行）。"""
    return json.dumps(menu_keys(), ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    """命令行入口。"""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, nargs="?", const=COMMITTED)
    ap.add_argument("--check", type=Path, nargs="?", const=COMMITTED)
    a = ap.parse_args(argv)
    text = render()
    if a.check:
        if not a.check.exists() or a.check.read_text() != text:
            sys.stderr.write(f"stale menu key list: {a.check}\n")
            return 1
        return 0
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
