from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError


class MesError(Exception):
    def __init__(self, errors: list[tuple[str, str]]) -> None:
        super().__init__("; ".join(m for _, m in errors))
        self.errors = errors


def http_422(errors: list[tuple[str, str]]) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=[
            {"loc": ["body", f], "msg": m, "type": "value_error"} for f, m in errors
        ],
    )


def integrity(ex: IntegrityError) -> HTTPException:
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
