"""规格行的（反）序列化：值转换、引用标签、JSON 输出。"""

import uuid
from datetime import date, datetime, time
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.base import Row, conn, table
from app.core.spec.engine import (
    ENTITIES,
    ENUMS,
    Entity,
    F,
)
from app.core.spec.errors import CoerceError


# ---------------- (de)serialization ----------------
def to_json(v: Any) -> Any:
    """把数据库值转换为 JSON 可序列化值（UUID / 日期 / Decimal）。"""
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, datetime | date | time):
        return v.isoformat()
    return v


def _num(fn: Any, v: Any, code: int, msg: str) -> Any:
    """转换数字，失败时抛带错误码的 :class:`CoerceError`。"""
    try:
        return fn(v)
    except (ValueError, TypeError) as ex:
        raise CoerceError(code, msg) from ex


def _parse(code: int, fn: Any, raw: str) -> Any:
    """解析日期 / 时间 / UUID，失败时抛带错误码的 :class:`CoerceError`。"""
    try:
        return fn(raw)
    except ValueError as ex:
        raise CoerceError(code, f"invalid value: {raw}") from ex


def coerce(f: F, v: Any) -> Any:
    """把原始 JSON / xlsx 值转换为字段对应的 Python 值。

    Raises:
        CoerceError: 值不符合字段类型（ValueError 子类，带错误码）。
    """
    if v is None or (isinstance(v, str) and v.strip() == "" and f.type != "json"):
        return None
    match f.type:
        case "str" | "text":
            s = str(v).strip() if f.type == "str" else str(v)
            if f.type == "str" and len(s) > f.max_length:
                raise CoerceError(
                    ec.STR_TOO_LONG,
                    f"at most {f.max_length} characters",
                    max=f.max_length,
                )
            return s
        case "int":
            if isinstance(v, bool) or (isinstance(v, float) and not v.is_integer()):
                raise CoerceError(ec.NOT_INTEGER, "must be an integer")
            return _num(int, v, ec.NOT_INTEGER, "must be an integer")
        case "float":
            if isinstance(v, bool):
                raise CoerceError(ec.NOT_NUMBER, "must be a number")
            return _num(float, v, ec.NOT_NUMBER, "must be a number")
        case "bool":
            if isinstance(v, bool):
                return v
            if str(v).lower() in ("true", "1", "yes", "y"):
                return True
            if str(v).lower() in ("false", "0", "no", "n"):
                return False
            raise CoerceError(ec.NOT_BOOL, "must be true/false")
        case "enum":
            allowed = [k for k, _ in ENUMS[f.enum or ""]]
            if str(v) not in allowed:
                raise CoerceError(
                    ec.NOT_IN_ENUM,
                    f"must be one of: {', '.join(allowed)}",
                    allowed=", ".join(allowed),
                )
            return str(v)
        case "date":
            if isinstance(v, datetime):
                return v.date()
            return (
                v
                if isinstance(v, date)
                else _parse(ec.INVALID_DATE, date.fromisoformat, str(v)[:10])
            )
        case "time":
            if isinstance(v, datetime):
                return v.time()
            return (
                v
                if isinstance(v, time)
                else _parse(ec.INVALID_TIME, time.fromisoformat, str(v))
            )
        case "datetime":
            return (
                v
                if isinstance(v, datetime)
                else _parse(ec.INVALID_DATETIME, datetime.fromisoformat, str(v))
            )
        case "ref":
            return (
                v
                if isinstance(v, uuid.UUID)
                else _parse(ec.INVALID_UUID, uuid.UUID, str(v))
            )
        case "json":
            return v
    return v


def ref_labels(
    session: Session, tenant_id: uuid.UUID, target: Entity, ids: set[Any]
) -> dict[Any, str]:
    """批量查询引用目标的显示标签 ``{id: 「CODE · 名称」}``。"""
    if not ids:
        return {}
    t = table(target)
    cols = [t.c.id, t.c[target.label_field if target.label_field in t.c else "id"]]
    named = target.has_code and target.has_name
    if named:
        cols.append(t.c.name)
    if target.versioned:
        cols.append(t.c.version)
    extra = target.field(target.label_ref) if target.label_ref else None
    if extra:
        cols.append(t.c[extra.column])
    rows = list(
        conn(session)
        .execute(sa.select(*cols).where(t.c.tenant_id == tenant_id, t.c.id.in_(ids)))
        .mappings()
    )
    extra_codes: dict[Any, str] = {}
    if extra:
        et = table(ENTITIES[extra.ref or ""])
        eids = {r[extra.column] for r in rows if r[extra.column]}
        if eids:
            extra_codes = {
                x["id"]: x["code"]
                for x in conn(session)
                .execute(sa.select(et.c.id, et.c.code).where(et.c.id.in_(eids)))
                .mappings()
            }
    out: dict[Any, str] = {}
    for r in rows:
        lbl = str(to_json(r[cols[1].name]))
        if extra and r[extra.column] in extra_codes:
            lbl += f" · {extra_codes[r[extra.column]]}"
        if target.versioned:
            lbl += f" v{r['version']}"
        if named and r["name"] and target.label_field == "code":
            lbl += f" · {r['name']}"
        out[r["id"]] = lbl
    return out


def serialize(
    session: Session, tenant_id: uuid.UUID, e: Entity, rows: list[Row]
) -> list[Row]:
    """序列化行：值转 JSON，并为引用字段附加 ``<name>`` 显示标签。"""
    out = [{k: to_json(v) for k, v in r.items() if k != "tenant_id"} for r in rows]
    for f in e.all_fields:
        if f.type != "ref":
            continue
        target = ENTITIES[f.ref or ""]
        labels = ref_labels(
            session, tenant_id, target, {r[f.column] for r in rows if r[f.column]}
        )
        for src, dst in zip(rows, out, strict=True):
            dst[f"{f.name}_label"] = labels.get(src[f.column])
    return out
