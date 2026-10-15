"""D65 补充 4：所有写接口的请求体模型（含嵌套、perm_body 依赖里的模型）都禁止多余字段。"""

import typing
from collections.abc import Iterator
from typing import Any

from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.core import registry


def _routes(rs: Any) -> Iterator[APIRoute]:
    for r in rs:
        if isinstance(r, APIRoute):
            yield r
        elif hasattr(r, "routes"):
            yield from _routes(r.routes)


def _models(tp: Any, acc: set[type[BaseModel]]) -> None:
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        if tp not in acc:
            acc.add(tp)
            for f in tp.model_fields.values():
                _models(f.annotation, acc)
        return
    for a in typing.get_args(tp):
        _models(a, acc)


def _deps(d: Any, acc: set[type[BaseModel]]) -> None:
    for b in d.body_params:
        _models(b.field_info.annotation, acc)
    for sub in d.dependencies:
        for cell in getattr(sub.call, "__closure__", None) or ():
            try:
                _models(cell.cell_contents, acc)
            except ValueError:
                pass
        _deps(sub, acc)


def test_every_body_model_forbids_extra() -> None:
    routes = [r for rt in registry.routers(dev=True) for r in _routes(rt.routes)]
    assert len(routes) > 100
    bad = set()
    seen: set[type[BaseModel]] = set()
    for r in routes:
        if not set(r.methods) & {"POST", "PUT", "PATCH", "DELETE"}:
            continue
        acc: set[type[BaseModel]] = set()
        _deps(r.dependant, acc)
        seen |= acc
        for m in acc:
            if m.model_config.get("extra") != "forbid":
                bad.add(f"{m.__module__}.{m.__qualname__}")
    assert len(seen) > 30
    assert not bad, sorted(bad)
