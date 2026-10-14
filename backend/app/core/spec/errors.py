"""规格服务错误及 HTTP 映射（422 字段错误、唯一约束冲突）。"""

from collections.abc import Sequence
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError


class MesError(Exception):
    """业务校验错误，携带字段级错误列表，由路由转换为 422。

    Attributes:
        errors: ``[(字段, 消息)]``。
    """

    def __init__(self, errors: list[tuple[str, str]]) -> None:
        """以字段错误列表构造。"""
        super().__init__("; ".join(m for _, m in errors))
        self.errors = errors


def _item(
    f: Any, m: str, code: str | None = None, *, where: str = "body"
) -> dict[str, Any]:
    d: dict[str, Any] = {
        "loc": [where, *f] if isinstance(f, tuple | list) else [where, f],
        "msg": m,
        "type": code or "value_error",
    }
    if code:
        d["code"] = code
    return d


def http_422(errors: Sequence[tuple[Any, ...]]) -> HTTPException:
    """把字段错误列表转换为 422 HTTPException（``detail`` 为字段错误数组）。

    字段可以是字符串（``loc = ["body", f]``），也可以是与 Pydantic 一致的路径元组
    （如 ``("lots", 0, "customer_id")`` → ``loc = ["body", "lots", 0, "customer_id"]``）。
    可带第三项错误码 ``(字段, 消息, code)``：该项 ``type`` 与 ``code`` 都为错误码。
    """
    return HTTPException(
        status_code=422,
        detail=[_item(*e) for e in errors],
    )


def query_422(errors: Sequence[tuple[Any, ...]]) -> HTTPException:
    """查询参数错误的 422（D65）：格式同 :func:`http_422`，但 ``loc`` 以 ``query`` 开头。"""
    return HTTPException(
        status_code=422,
        detail=[_item(*e, where="query") for e in errors],
    )


_NO_INPUT: Any = object()


def err_422(
    loc: Sequence[Any],
    msg: str,
    code: str,
    ctx: dict[str, Any] | None = None,
    *,
    input: Any = _NO_INPUT,
) -> HTTPException:
    """单项 422（D65 补充：detail 一律为列表）：``loc`` 原样给出，``type`` 与 ``code`` 为错误码。"""
    return HTTPException(
        status_code=422,
        detail=[
            {
                "loc": list(loc),
                "msg": msg,
                "type": code,
                "code": code,
                **({"ctx": ctx} if ctx else {}),
                **({} if input is _NO_INPUT else {"input": input}),
            }
        ],
    )


def integrity(ex: IntegrityError) -> HTTPException:
    """把数据库完整性错误（唯一 / 外键 / 其他约束）转换为 409 HTTPException。"""
    msg = str(ex.orig)
    if "unique" in msg.lower() or "duplicate" in msg.lower():
        return HTTPException(
            status_code=409, detail="A record with the same key already exists"
        )
    if "foreign key" in msg.lower():
        return HTTPException(
            status_code=409, detail="Record is referenced by other records"
        )
    return HTTPException(status_code=409, detail="Constraint violation")
