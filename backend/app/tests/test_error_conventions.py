"""错误输出约定：对用户可见的错误必须是“错误码 + 参数”，不得再把英文原文当作唯一信息。

- ``HTTPException(detail=...)`` 的 detail 不得是字符串字面量 / f-string（改用 ``coded()``）；
- 字段错误不得是裸 ``(字段, 消息)`` 元组（改用 ``fe()``）；
- 注册表里的错误码唯一、落在所属分段内。
"""

import ast
from pathlib import Path

from app.core import error_codes as ec

APP = Path(__file__).resolve().parents[1]


def _sources() -> list[tuple[str, ast.AST]]:
    out = []
    for p in sorted(APP.rglob("*.py")):
        if {"tests", "testing", "alembic", "__pycache__"} & set(p.parts):
            continue
        out.append((str(p.relative_to(APP)), ast.parse(p.read_text(encoding="utf-8"))))
    return out


def _is_text(n: ast.AST | None) -> bool:
    return isinstance(n, ast.JoinedStr) or (
        isinstance(n, ast.Constant) and isinstance(n.value, str)
    )


def test_no_text_http_exception_detail() -> None:
    bad = []
    for rel, tree in _sources():
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "HTTPException":
                det = next((k.value for k in n.keywords if k.arg == "detail"), None)
                if det is None and len(n.args) >= 2:
                    det = n.args[1]
                if _is_text(det):
                    bad.append(f"{rel}:{n.lineno}")
    assert not bad, f"use coded(status, ec.X, 'english fallback'): {bad}"


def test_no_raw_field_error_tuples() -> None:
    bad = []
    for rel, tree in _sources():
        for n in ast.walk(tree):
            if isinstance(n, ast.Tuple) and len(n.elts) == 2:
                a, b = n.elts
                if not _is_text(b):
                    continue
                # 字段错误的英文消息形如 "字段: 说明"（首元素为字段名字面量 / f-string）
                head = (
                    a.value
                    if isinstance(a, ast.Constant) and isinstance(a.value, str)
                    else ast.unparse(a).strip("f'\"")
                    if isinstance(a, ast.JoinedStr)
                    else None
                )
                text = (
                    b.value
                    if isinstance(b, ast.Constant)
                    else ast.unparse(b).strip("f'\"")
                )
                if head and text.startswith(f"{head}: "):
                    bad.append(f"{rel}:{n.lineno}")
    assert not bad, f"use fe(field, ec.X, 'english fallback'): {bad}"


def test_error_codes_unique_and_in_range() -> None:
    values = [v for k, v in vars(ec).items() if k.isupper() and isinstance(v, int)]
    assert len(values) == len(set(values)), "duplicate error code values"
    assert all(100000 <= v < 800000 for v in values)
    assert len(ec.CODES) == len(values)
    assert set(ec.PYDANTIC_CODES.values()) <= set(values)
