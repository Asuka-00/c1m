"""规格服务错误及 HTTP 映射（422 字段错误、唯一约束冲突）。"""

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


def http_422(errors: list[tuple[str, str]]) -> HTTPException:
    """把字段错误列表转换为 422 HTTPException（``detail`` 为字段错误数组）。"""
    return HTTPException(
        status_code=422,
        detail=[
            {"loc": ["body", f], "msg": m, "type": "value_error"} for f, m in errors
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
