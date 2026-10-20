"""规格服务错误及 HTTP 映射（422 字段错误、业务错误、唯一约束冲突）。

所有对用户可见的错误都是 ``错误码 + 参数``（见 :mod:`app.core.error_codes`），英文 ``message``
只是兜底；各语言文案在前端 ``error.code_<错误码>``，字段规则类文案用 ``{{field}}`` 引用字段显示名。
"""

from collections.abc import Sequence
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.core import error_codes as ec

#: 字段错误：``(字段, 英文消息, 错误码, 参数)``
CodedError = tuple[str, str, int, dict[str, Any]]
FieldError = CodedError


def fe(field: str, code: int, msg: str, /, **params: Any) -> CodedError:
    """字段错误：错误码 + 参数（前端 ``error.code_<code>``，文案可用 ``{{field}}`` 引用字段显示名）。"""
    return (field, msg, code, params)


class CoerceError(ValueError):
    """字段值类型转换失败（带错误码与参数）。

    Attributes:
        code: 错误码。
        params: 插值参数。
    """

    def __init__(self, code: int, msg: str, **params: Any) -> None:
        """以错误码、英文消息与参数构造。"""
        super().__init__(msg)
        self.code = code
        self.params = params


class MesError(Exception):
    """业务校验错误，携带字段级错误列表，由路由转换为 422。

    Attributes:
        errors: :data:`FieldError` 列表。
    """

    def __init__(self, errors: Sequence[FieldError]) -> None:
        """以字段错误列表构造。"""
        super().__init__("; ".join(e[1] for e in errors))
        self.errors = list(errors)


def _item(e: FieldError) -> dict[str, Any]:
    return {
        "loc": ["body", e[0]],
        "msg": e[1],
        "type": "value_error",
        "code": e[2],
        "params": e[3],
    }


def http_422(errors: Sequence[FieldError]) -> HTTPException:
    """把字段错误列表转换为 422 HTTPException（``detail`` 为字段错误数组，每项带 code / params）。"""
    return HTTPException(status_code=422, detail=[_item(e) for e in errors])


def coded(status: int, code: int, message: str, /, **params: Any) -> HTTPException:
    """业务错误：``detail = {code, message, params?}``（对应参考项目的 ``Result.errorParams``）。"""
    detail: dict[str, Any] = {"code": code, "message": message}
    if params:
        detail["params"] = params
    return HTTPException(status_code=status, detail=detail)


def integrity(ex: IntegrityError) -> HTTPException:
    """把数据库完整性错误（唯一 / 外键 / 其他约束）转换为 409 HTTPException。"""
    msg = str(ex.orig)
    if "unique" in msg.lower() or "duplicate" in msg.lower():
        return coded(409, ec.DUPLICATE_KEY, "A record with the same key already exists")
    if "foreign key" in msg.lower():
        return coded(409, ec.RECORD_REFERENCED, "Record is referenced by other records")
    return coded(409, ec.CONSTRAINT_VIOLATION, "Constraint violation")
