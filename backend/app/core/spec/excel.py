"""按实体导出 / 导入 xlsx（openpyxl）。

工作表布局：第 1 行为列键（字段名，版本化数据加 ``version``/``status``，自定义属性为
``attr:<code>``）。引用以目标编码读写（``CODE`` = 激活或最新版本，``CODE@2`` = 指定版本），
无编码的目标使用 id。导入按业务唯一键新增或更新，全部成功或全部回滚。

时间（D46 P2）：datetime 字段写成 Excel 日期单元格，按租户时区换算（租户时区取第一个启用
厂区的 timezone，没有厂区时用 Asia/Taipei），列名带时区，如 ``created_at (Asia/Taipei)``；
date 字段写成日期单元格（无时区，列名不变）。导入时去掉列名里的时区后缀，无时区的
datetime 按同一租户时区理解。接口 JSON 仍输出 UTC Z（D45）。
"""

import io
import json
import re
import uuid
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import sqlalchemy as sa
from fastapi import HTTPException
from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter
from sqlmodel import Session

from app.core.spec.base import conn, table
from app.core.spec.engine import ENTITIES, Entity
from app.core.spec.errors import err_422
from app.core.spec.query import all_rows
from app.core.spec.serialize import TooManyDecimals, to_json
from app.core.spec.validate import attr_defs
from app.core.spec.write import create_row, update_row

MAX_ROWS = 5000
DEFAULT_TZ = "Asia/Taipei"
DT_FORMAT = "yyyy-mm-dd hh:mm:ss"
DATE_FORMAT = "yyyy-mm-dd"
_TZ_SUFFIX = re.compile(r"\s+\([^()]+\)$")


def tenant_tz(session: Session, tenant_id: uuid.UUID) -> ZoneInfo:
    """租户时区：第一个启用厂区（按编码）的 timezone；无厂区或时区无效时用 Asia/Taipei。"""
    t = table(ENTITIES["site"])
    name = (
        conn(session)
        .execute(
            sa.select(t.c.timezone)
            .where(t.c.tenant_id == tenant_id, t.c.is_active.is_not(False))
            .order_by(t.c.code)
            .limit(1)
        )
        .scalar()
    )
    try:
        return ZoneInfo(name or DEFAULT_TZ)
    except ZoneInfoNotFoundError, ValueError:
        return ZoneInfo(DEFAULT_TZ)


def _header(e: Entity, col: str, tz: ZoneInfo) -> str:
    f = e.field(col) if not col.startswith("attr:") else None
    return f"{col} ({tz.key})" if f and f.type == "datetime" else col


def _ref_code(
    session: Session, tenant_id: uuid.UUID, target: Entity, ids: set[Any]
) -> dict[Any, str]:
    if not ids:
        return {}
    t = table(target)
    if not target.has_code:
        return {i: str(i) for i in ids}
    cols = [t.c.id, t.c.code] + ([t.c.version] if target.versioned else [])
    out = {}
    for r in (
        conn(session)
        .execute(sa.select(*cols).where(t.c.tenant_id == tenant_id, t.c.id.in_(ids)))
        .mappings()
    ):
        out[r["id"]] = f"{r['code']}@{r['version']}" if target.versioned else r["code"]
    return out


def columns(session: Session, tenant_id: uuid.UUID, e: Entity) -> list[str]:
    """导出/导入的列键：字段名、版本化实体的 version/status、自定义属性 ``attr:<code>``。"""
    cols = [f.name for f in e.all_fields]
    if e.versioned:
        cols += ["version", "status"]
    cols += [f"attr:{d['code']}" for d in attr_defs(session, tenant_id, e)]
    return cols


def export_xlsx(
    session: Session,
    tenant_id: uuid.UUID,
    e: Entity,
    *,
    q: str | None = None,
    filters: dict[str, str] | None = None,
) -> bytes:
    """导出实体行为 xlsx（按当前关键字 / 筛选；无筛选时为全部行）。

    Returns:
        xlsx 文件字节。
    """
    rows = all_rows(session, e, tenant_id, MAX_ROWS, q=q, filters=filters)
    cols = columns(session, tenant_id, e)
    refs = {
        f.name: _ref_code(
            session,
            tenant_id,
            ENTITIES[f.ref or ""],
            {r[f.column] for r in rows if r[f.column]},
        )
        for f in e.all_fields
        if f.type == "ref"
    }
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = e.code[:31]
    tz = tenant_tz(session, tenant_id)
    ws.append([_header(e, c, tz) for c in cols])
    for r in rows:
        line: list[Any] = []
        for c in cols:
            if c.startswith("attr:"):
                line.append((r.get("attrs") or {}).get(c[5:]))
                continue
            f = e.field(c)
            if f and f.type == "ref":
                line.append(refs[f.name].get(r[f.column]))
            elif f and f.type == "json":
                line.append(
                    json.dumps(r[f.column]) if r[f.column] is not None else None
                )
            else:
                v = r[f.column if f else c]
                if f and f.type == "datetime" and isinstance(v, datetime):
                    # openpyxl 不接受带时区的 datetime：换算到租户时区后去掉 tzinfo
                    line.append(
                        v.astimezone(tz).replace(tzinfo=None) if v.tzinfo else v
                    )
                elif (
                    f
                    and f.type in ("date", "time", "datetime")
                    and not isinstance(v, date)
                ):
                    line.append(to_json(v))
                elif f and f.type == "time":
                    line.append(to_json(v))
                else:
                    line.append(v)
        ws.append(line)
        for cell, c in zip(ws[ws.max_row], cols, strict=True):
            f = e.field(c) if not c.startswith("attr:") else None
            if f and f.type == "datetime" and isinstance(cell.value, datetime):
                cell.number_format = DT_FORMAT
            elif f and f.type == "date" and isinstance(cell.value, date):
                cell.number_format = DATE_FORMAT
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _resolve(session: Session, tenant_id: uuid.UUID, target: Entity, raw: str) -> Any:
    t = table(target)
    c = conn(session)
    if not target.has_code:
        try:
            return uuid.UUID(raw)
        except ValueError:
            return None
    code, _, ver = raw.partition("@")
    stmt = sa.select(t.c.id).where(t.c.tenant_id == tenant_id, t.c.code == code.strip())
    if target.versioned:
        if ver:
            stmt = stmt.where(t.c.version == int(ver))
        else:
            stmt = stmt.order_by(
                sa.case((t.c.status == "active", 0), else_=1), t.c.version.desc()
            )
    return c.execute(stmt.limit(1)).scalar()


def _cell(e: Entity, header: list[str], n: int, key: Any) -> dict[str, Any]:
    """导入错误定位到单元格：``loc=["file", 行号, 列名]``，另给 ``column`` 与 ``cell``（如 ``C5``）。

    ``key`` 为字段名 / 列名（取自校验错误 loc 末项）；对不上表头时只给到行。
    """
    if not isinstance(key, str):
        return {}
    for i, h in enumerate(header):
        f = e.field(h) if h else None
        if h and (h == key or (f and key in (f.name, f.column))):
            return {
                "loc": ["file", n, h],
                "column": h,
                "cell": f"{get_column_letter(i + 1)}{n}",
            }
    return {}


def import_xlsx(
    session: Session, tenant_id: uuid.UUID, e: Entity, data: bytes, user: Any
) -> dict[str, int]:
    """从 xlsx 导入（按业务唯一键新增或更新）。

    Args:
        session: 数据库会话。
        tenant_id: 租户 id。
        e: 实体规格。
        data: xlsx 文件字节。
        user: 操作人。

    Returns:
        ``{"created": n, "updated": m}``。

    Raises:
        HTTPException: 任一行校验失败（422，消息带行号）。
    """
    if e.readonly:
        raise HTTPException(status_code=405, detail="Read-only entity")
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as ex:  # noqa: BLE001 - any parse error is a bad upload
        raise HTTPException(status_code=400, detail="Not a valid .xlsx file") from ex
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    header = [
        _TZ_SUFFIX.sub("", str(h).strip()) if h is not None else ""
        for h in next(it, ())
    ]
    tz = tenant_tz(session, tenant_id)
    if not header or not any(header):
        raise HTTPException(status_code=400, detail="Empty sheet")
    known = set(columns(session, tenant_id, e)) | {""}
    unknown = [h for h in header if h not in known]
    if unknown:
        raise err_422(
            ["body", "file"],
            f"Unknown columns: {', '.join(unknown)}",
            "unknown_columns",
            {"columns": unknown},
        )
    errors: list[dict[str, Any]] = []
    created = updated = 0
    t = table(e)
    nested = session.begin_nested()
    for n, values in enumerate(it, start=2):
        if n > MAX_ROWS + 1:
            errors.append(
                {
                    "row": n,
                    "msg": f"too many rows (max {MAX_ROWS})",
                    "loc": ["file", n],
                }
            )
            break
        raw = dict(zip(header, values, strict=False))
        if all(v in (None, "") for v in raw.values()):
            continue
        payload: dict[str, Any] = {}
        attrs: dict[str, Any] = {}
        try:
            for k, v in raw.items():
                if not k or k == "status":
                    continue
                if k.startswith("attr:"):
                    if v not in (None, ""):
                        attrs[k[5:]] = v
                    continue
                f = e.field(k)
                if f and f.type == "ref" and v not in (None, ""):
                    rid = _resolve(session, tenant_id, ENTITIES[f.ref or ""], str(v))
                    if rid is None:
                        miss = ValueError(f"{k}: '{v}' not found")
                        miss.field = k  # type: ignore[attr-defined]
                        raise miss
                    payload[f.column] = rid
                elif f and f.type == "json" and isinstance(v, str) and v.strip():
                    payload[k] = json.loads(v)
                elif f and f.type == "datetime" and isinstance(v, datetime):
                    payload[k] = v if v.tzinfo else v.replace(tzinfo=tz)
                elif f and f.type == "date" and isinstance(v, datetime):
                    payload[k] = v.date()
                else:
                    payload[k] = v
            if attrs:
                payload["attrs"] = attrs
            key_cols = [
                (fld.column if (fld := e.field(k)) else k) for k in e.natural_key
            ]
            key_vals = [
                payload.get(c, payload.get(c.removesuffix("_id"))) for c in key_cols
            ]
            existing = None
            if all(v not in (None, "") for v in key_vals):
                stmt = sa.select(t.c.id).where(t.c.tenant_id == tenant_id)
                for c, v in zip(key_cols, key_vals, strict=True):
                    column: Any = t.c[c]
                    stmt = stmt.where(column == (int(str(v)) if c == "version" else v))
                existing = conn(session).execute(stmt).scalar()
            if existing:
                update_row(
                    session,
                    tenant_id,
                    e,
                    existing,
                    payload,
                    user,
                    commit=False,
                    action="import",
                )
                updated += 1
            else:
                create_row(session, tenant_id, e, payload, user, commit=False)
                created += 1
        except HTTPException as ex:
            d = ex.detail
            msg = (
                "; ".join(x.get("msg", "") for x in d)
                if isinstance(d, list)
                else str(d)
            )
            err: dict[str, Any] = {"row": n, "msg": msg, "loc": ["file", n]}
            first = d[0] if isinstance(d, list) and d else None
            if isinstance(first, dict) and first.get("type"):
                # D76：导入错误同样带首条的 type / ctx（如 value_error max_places）
                err.update({k: first[k] for k in ("type", "ctx") if k in first})
                loc = first.get("loc") or []
                err.update(_cell(e, header, n, loc[-1] if loc else None))
            errors.append(err)
        except (ValueError, TypeError) as ex:
            err = {"row": n, "msg": str(ex), "loc": ["file", n]}
            if isinstance(ex, TooManyDecimals):
                err.update(type=ex.code, ctx=ex.ctx)
            err.update(_cell(e, header, n, getattr(ex, "field", None)))
            errors.append(err)
    if errors:
        nested.rollback()
        session.rollback()
        raise HTTPException(
            status_code=422, detail={"message": "Import failed", "errors": errors[:50]}
        )
    nested.commit()
    session.commit()
    return {"created": created, "updated": updated}
