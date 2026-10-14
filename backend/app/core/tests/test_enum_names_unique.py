"""各模块 specs.py 里 ENUMS.update 的枚举名不得重名（重名时后注册者静默覆盖）。"""

import ast
from collections import defaultdict
from pathlib import Path

APP = Path(__file__).resolve().parents[2]


def test_enum_names_unique_across_specs() -> None:
    seen: dict[str, list[str]] = defaultdict(list)
    for p in sorted(APP.rglob("specs.py")):
        for node in ast.walk(ast.parse(p.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "update"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "ENUMS"
                and node.args
                and isinstance(node.args[0], ast.Dict)
            ):
                for k in node.args[0].keys:
                    if isinstance(k, ast.Constant):
                        seen[k.value].append(str(p.relative_to(APP)))
    assert seen, "no ENUMS.update found"
    dup = {k: v for k, v in seen.items() if len(v) > 1}
    assert not dup, dup
