"""机台上料记录（D28 / B3，bom.md v1.1 §9–10）。

- 上料口 = (equipment_id, port_code)；同一上料口同时只能有一条 unmounted_at 为空的记录
  （部分唯一索引 uq_mes_eqp_mount_port_open，服务层先校验）。
- 人工上料遇到在装批次 → 409 ``port_occupied``（写明当前批）；EAP 上报在同一事务里先卸
  旧批（卸下时间 = 新批装上时间）再装新批。
- 外部事件号按 (source, external_event_id) 去重：重复上报幂等返回已有记录；source=eap 时
  external_event_id 必填。EAP 将来调用同一个 :func:`mount`。
"""

import uuid
from datetime import datetime, timedelta
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.models import actor_name
from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, TABLES
from app.core.spec.errors import http_422
from app.core.spec.serialize import serialize
from app.mes.common.query import find, one

Row = dict[str, Any]
ENT = "equipment_material_mount"
SOURCES = ("manual", "eap")
# 人工录入允许的时钟偏差
CLOCK_SKEW = timedelta(minutes=5)


def _ser(s: Session, tid: uuid.UUID, rows: list[Row]) -> list[Row]:
    out = serialize(s, tid, ENTITIES[ENT], rows)
    for r, o in zip(rows, out, strict=True):
        ml = one(s, tid, "material_lot", r["material_lot_id"])
        o["material_lot_code"] = ml and ml["code"]
    return out


def _by_event(s: Session, tid: uuid.UUID, source: str, ext: str) -> Row | None:
    rows = find(s, tid, ENT, source=source, external_event_id=ext)
    return rows[0] if rows else None


def _open(
    s: Session, tid: uuid.UUID, eq_id: Any, port: str, lock: bool = False
) -> Row | None:
    t = TABLES[ENT]
    q = sa.select(t).where(
        t.c.tenant_id == tid,
        t.c.equipment_id == eq_id,
        t.c.port_code == port,
        t.c.unmounted_at.is_(None),
    )
    if lock:
        q = q.with_for_update()
    r = conn(s).execute(q).mappings().first()
    return dict(r) if r else None


def _material_lot(s: Session, tid: uuid.UUID, body: Row, at: datetime) -> Row:
    ml = None
    if body.get("material_lot_id"):
        ml = one(s, tid, "material_lot", body["material_lot_id"])
    elif body.get("material_lot_code"):
        t = TABLES["material_lot"]
        r = (
            conn(s)
            .execute(
                sa.select(t).where(
                    t.c.tenant_id == tid,
                    t.c.code == str(body["material_lot_code"]).strip(),
                )
            )
            .mappings()
            .first()
        )
        ml = dict(r) if r else None
    else:
        raise http_422([("material_lot", "material_lot: required")])
    if not ml:
        raise http_422([("material_lot", "material_lot: not found")])
    if ml["ml_status"] == "expired" or (
        ml["expiry_date"] and ml["expiry_date"] < at.date()
    ):
        raise http_422(
            [
                (
                    "material_lot",
                    f"material_lot: {ml['code']} expired ({ml['expiry_date']})",
                )
            ]
        )
    return ml


def mount(
    s: Session,
    tid: uuid.UUID,
    eq_id: uuid.UUID,
    body: Row,
    user: Any,
    source: str = "manual",
) -> Row:
    """上料（人工 / EAP 共用）。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        eq_id: 设备 id。
        body: ``{port_code, material_lot_id | material_lot_code, mounted_at?,
            external_event_id?, comment?}``。
        user: 操作人（EAP 为系统用户）。
        source: ``manual`` / ``eap``。

    Returns:
        ``{data, duplicate, unmounted}``：新记录（或幂等返回的已有记录）、是否重复事件、
        EAP 自动卸下的旧记录。

    Raises:
        HTTPException: 设备不存在（404）；上料口已有料（409 port_occupied，仅人工）；
            时间与历史重叠（409 mount_overlap）；参数 / 物料批不合法（422）。
    """
    if source not in SOURCES:
        raise http_422([("source", f"source: must be one of {', '.join(SOURCES)}")])
    ext = (str(body.get("external_event_id") or "").strip()) or None
    if source == "eap" and not ext:
        raise http_422([("external_event_id", "external_event_id: required for eap")])
    port = str(body.get("port_code") or "").strip()
    if not port:
        raise http_422([("port_code", "port_code: required")])
    if len(port) > 64 or (ext and len(ext) > 128):
        raise http_422([("port_code", "port_code / external_event_id: too long")])
    # 设备行加锁：同一机台的上料 / 卸料串行，空上料口的并发上料也不会撞索引
    et = TABLES["equipment"]
    eq = (
        conn(s)
        .execute(
            sa.select(et)
            .where(et.c.tenant_id == tid, et.c.id == eq_id)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not eq:
        raise HTTPException(status_code=404, detail="equipment not found")
    if ext:
        dup = _by_event(s, tid, source, ext)
        if dup:
            s.commit()
            return {
                "data": _ser(s, tid, [dup])[0],
                "duplicate": True,
                "unmounted": None,
            }
    cur_t = now()
    at = body.get("mounted_at") or cur_t
    if isinstance(at, str):
        try:
            at = datetime.fromisoformat(at)
        except ValueError as ex:
            raise http_422([("mounted_at", "mounted_at: invalid datetime")]) from ex
    if at.tzinfo is None:
        raise http_422([("mounted_at", "mounted_at: timezone required")])
    if at > cur_t + CLOCK_SKEW:
        raise http_422([("mounted_at", "mounted_at: cannot be in the future")])
    ml = _material_lot(s, tid, body, at)
    t = TABLES[ENT]
    c = conn(s)
    prev = _open(s, tid, eq_id, port, lock=True)
    unmounted: Row | None = None
    if prev:
        if source == "manual":
            pml = one(s, tid, "material_lot", prev["material_lot_id"])
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "port_occupied",
                    "message": f"port {port} of {eq['code']} already holds material "
                    f"lot {pml and pml['code']}; unmount it first",
                    "equipment_id": str(eq_id),
                    "equipment_code": eq["code"],
                    "port_code": port,
                    "current_mount_id": str(prev["id"]),
                    "current_material_lot_id": str(prev["material_lot_id"]),
                    "current_material_lot_code": pml and pml["code"],
                    "current_mounted_at": prev["mounted_at"].isoformat(),
                },
            )
        if at < prev["mounted_at"]:
            raise http_422(
                [("mounted_at", "mounted_at: earlier than the lot currently mounted")]
            )
        c.execute(
            sa.update(t)
            .where(t.c.id == prev["id"])
            .values(
                unmounted_at=at,
                unmounted_by=actor_name(user),
                updated_at=cur_t,
                updated_by=getattr(user, "id", None),
            )
        )
        unmounted = {**prev, "unmounted_at": at}
        audit(
            s,
            tid,
            ENTITIES[ENT],
            "unmount",
            unmounted,
            user,
            {"unmounted_at": (None, at)},
        )
    # 回填的装上时间不能落在该上料口已关闭记录的区间里
    overlap = c.execute(
        sa.select(t.c.id).where(
            t.c.tenant_id == tid,
            t.c.equipment_id == eq_id,
            t.c.port_code == port,
            t.c.unmounted_at.is_not(None),
            t.c.unmounted_at > at,
            *([t.c.id != prev["id"]] if prev else []),
        )
    ).first()
    if overlap:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "mount_overlap",
                "message": f"mounted_at overlaps an earlier mount on port {port}",
                "mount_id": str(overlap[0]),
            },
        )
    rid = uuid.uuid4()
    vals = {
        "id": rid,
        "tenant_id": tid,
        "equipment_id": eq_id,
        "port_code": port,
        "material_lot_id": ml["id"],
        "material_id": ml["material_id"],
        "mounted_at": at,
        "source": source,
        "external_event_id": ext,
        "mounted_by": actor_name(user),
        "comment": (str(body.get("comment") or "").strip() or None),
        "created_at": cur_t,
        "updated_at": cur_t,
        "created_by": getattr(user, "id", None),
        "updated_by": getattr(user, "id", None),
    }
    try:
        with s.begin_nested():
            c.execute(sa.insert(t).values(**vals))
    except IntegrityError as ex:
        s.rollback()
        dup = ext and _by_event(s, tid, source, ext)
        if dup:  # 并发重复事件：幂等
            return {
                "data": _ser(s, tid, [dup])[0],
                "duplicate": True,
                "unmounted": None,
            }
        raise HTTPException(
            status_code=409,
            detail={
                "code": "port_occupied",
                "message": "port is occupied concurrently",
            },
        ) from ex
    row = one(s, tid, ENT, rid)
    assert row
    audit(
        s,
        tid,
        ENTITIES[ENT],
        "mount",
        row,
        user,
        {"material_lot": (None, ml["code"]), "port_code": (None, port)},
    )
    s.commit()
    return {
        "data": _ser(s, tid, [row])[0],
        "duplicate": False,
        "unmounted": unmounted and _ser(s, tid, [unmounted])[0],
    }


def unmount(
    s: Session, tid: uuid.UUID, mount_id: uuid.UUID, body: Row, user: Any
) -> Row:
    """卸料：写卸下时间（默认现在）。

    Raises:
        HTTPException: 记录不存在（404）；已卸下（409 already_unmounted）；时间不合法（422）。
    """
    t = TABLES[ENT]
    r = (
        conn(s)
        .execute(
            sa.select(t)
            .where(t.c.tenant_id == tid, t.c.id == mount_id)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="mount record not found")
    row = dict(r)
    if row["unmounted_at"] is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "already_unmounted",
                "message": f"already unmounted at {row['unmounted_at'].isoformat()}",
                "mount_id": str(row["id"]),
            },
        )
    cur_t = now()
    at = body.get("unmounted_at") or cur_t
    if isinstance(at, str):
        try:
            at = datetime.fromisoformat(at)
        except ValueError as ex:
            raise http_422([("unmounted_at", "unmounted_at: invalid datetime")]) from ex
    if at.tzinfo is None:
        raise http_422([("unmounted_at", "unmounted_at: timezone required")])
    if at < row["mounted_at"] or at > cur_t + CLOCK_SKEW:
        raise http_422(
            [("unmounted_at", "unmounted_at: must be between mounted_at and now")]
        )
    conn(s).execute(
        sa.update(t)
        .where(t.c.id == mount_id)
        .values(
            unmounted_at=at,
            unmounted_by=actor_name(user),
            updated_at=cur_t,
            updated_by=getattr(user, "id", None),
        )
    )
    new = one(s, tid, ENT, mount_id)
    assert new
    audit(s, tid, ENTITIES[ENT], "unmount", new, user, {"unmounted_at": (None, at)})
    s.commit()
    return _ser(s, tid, [new])[0]


def mounted_at(
    s: Session, tid: uuid.UUID, eq_id: uuid.UUID, at: datetime, port: str | None = None
) -> list[Row]:
    """某时间点机台各上料口装着的料（mounted_at ≤ at < unmounted_at 或未卸）。"""
    if not one(s, tid, "equipment", eq_id):
        raise HTTPException(status_code=404, detail="equipment not found")
    t = TABLES[ENT]
    q = sa.select(t).where(
        t.c.tenant_id == tid,
        t.c.equipment_id == eq_id,
        t.c.mounted_at <= at,
        sa.or_(t.c.unmounted_at.is_(None), t.c.unmounted_at > at),
    )
    if port:
        q = q.where(t.c.port_code == port)
    rows = [dict(r) for r in conn(s).execute(q.order_by(t.c.port_code)).mappings()]
    return _ser(s, tid, rows)
