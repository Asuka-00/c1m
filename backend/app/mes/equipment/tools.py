"""耗材 / 工装寿命（P2-B10，eap/p2/consumable-life-model.md 定稿 + D53 / D54）。

- 计数一律 Decimal（numeric(18,6)），到期判定 ``usage_count >= max_usage``；
- 每次计数写 ``tool_usage`` 履历（kind track_out / report / adjust / reset），跨过上限时置
  pending_maintenance（不新增状态，D53-5）并发 ``mes.tool_life_reached`` 通知（只在跨过时一次）；
- 装卸 / 更换写 ``tool_mount_log``；同一工具同时只有一条未卸下记录（部分唯一索引）；
- 外部事件号按 (source, external_event_id) 幂等（D30）；人工接口固定 source=manual。
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
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
from app.core.spec.serialize import dec_str, serialize
from app.mes.common.query import find, one
from app.mes.common.rows import _ins, _upd
from app.mes.equipment.events import TOOL_LIFE_REACHED, notify_eqp
from app.mes.equipment.status import tool_life, warn_ratio

Row = dict[str, Any]
CLOCK_SKEW = timedelta(minutes=5)
USABLE = ("available", "in_use")
DEC_FIELDS = {
    "tool_usage": ("delta", "count_after"),
    "tool_mount_log": ("usage_at_mount", "usage_at_unmount"),
}


def _conflict(code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(
        status_code=409, detail={"code": code, "message": message, **extra}
    )


def event_time(v: datetime | None, field: str) -> datetime:
    """事件时间：缺省为服务器时间；超前 5 分钟以上 422 ``time_in_future``（D55）。"""
    cur = now()
    if v is None:
        return cur
    if v.tzinfo is None:
        raise http_422([(field, f"{field}: timezone required")])
    v = v.astimezone(UTC)
    if v > cur + CLOCK_SKEW:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", field],
                    "msg": f"{field}: more than 5 minutes in the future",
                    "type": "time_in_future",
                    "code": "time_in_future",
                }
            ],
        )
    return v


def _lock_tool(s: Session, tid: uuid.UUID, tool_id: Any) -> Row:
    t = TABLES["tool"]
    r = (
        conn(s)
        .execute(
            sa.select(t)
            .where(t.c.tenant_id == tid, t.c.id == tool_id)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="tool not found")
    return dict(r)


def life_state(s: Session, tid: uuid.UUID, tool: Row) -> str:
    """``ok`` / ``warning``（max×warn_ratio <= 已用 < max）/ ``reached``（已用 >= max）。"""
    mx, used = tool_life(s, tid, tool)
    if not mx:
        return "ok"
    if used >= mx:
        return "reached"
    return "warning" if used >= mx * warn_ratio(s, tid, tool) else "ok"


def tool_brief(s: Session, tid: uuid.UUID, tool: Row) -> Row:
    """工具寿命摘要（D50：数值为十进制字符串）。"""
    mx, used = tool_life(s, tid, tool)
    return {
        "id": str(tool["id"]),
        "code": tool["code"],
        "tool_status": tool["tool_status"],
        "usage_count": dec_str(used),
        "max_usage": dec_str(mx),
        "warn_ratio": dec_str(warn_ratio(s, tid, tool)),
        "effective_max_usage": dec_str(mx),
        "effective_warn_ratio": dec_str(warn_ratio(s, tid, tool)),
        "life_state": life_state(s, tid, tool),
        "equipment_id": tool["equipment_id"] and str(tool["equipment_id"]),
        "mounted_at": tool.get("mounted_at"),
        "life_reset_count": tool.get("life_reset_count") or 0,
    }


def ser(s: Session, tid: uuid.UUID, ent: str, rows: list[Row]) -> list[Row]:
    """履历行序列化：时间 UTC Z（serialize），小数字段改为十进制字符串（D50）。"""
    out = serialize(s, tid, ENTITIES[ent], rows)
    for o, r in zip(out, rows, strict=True):
        for k in DEC_FIELDS[ent]:
            o[k] = dec_str(r[k])
    return out


def count(
    s: Session,
    tid: uuid.UUID,
    tool: Row,
    delta: Decimal,
    kind: str,
    user: Any,
    *,
    at: datetime | None = None,
    lot_id: Any = None,
    equipment_id: Any = None,
    operation_id: Any = None,
    reason_id: Any = None,
    comment: str | None = None,
    source: str = "manual",
    external_event_id: str | None = None,
) -> Row:
    """计数并写履历（调用方负责加锁与提交）；返回 ``{usage, tool, life_reached}``。"""
    at = at or now()
    mx, used = tool_life(s, tid, tool)
    after = used + delta
    if after < 0:
        raise http_422([("delta", "delta: usage cannot go below 0")])
    st = tool["tool_status"]
    reached = bool(mx and after >= mx and used < mx)
    if mx and after >= mx and st in USABLE:
        st = "pending_maintenance"
    _upd(s, tid, "tool", tool["id"], user, usage_count=after, tool_status=st)
    uid = _ins(
        s,
        tid,
        "tool_usage",
        user,
        tool_id=tool["id"],
        equipment_id=equipment_id or tool.get("equipment_id"),
        sub_unit_id=tool.get("sub_unit_id"),
        lot_id=lot_id,
        operation_id=operation_id,
        delta=delta,
        count_after=after,
        kind=kind,
        occurred_at=at,
        reason_id=reason_id,
        comment=comment,
        source=source,
        external_event_id=external_event_id,
        username=actor_name(user),
    )
    tool.update(usage_count=after, tool_status=st)
    if reached:
        eq = one(s, tid, "equipment", equipment_id or tool.get("equipment_id"))
        audit(
            s,
            tid,
            ENTITIES["tool"],
            "life_reached",
            tool,
            user,
            {"usage_count": (dec_str(used), dec_str(after))},
        )
        if eq:
            notify_eqp(
                s,
                tid,
                TOOL_LIFE_REACHED,
                eq,
                f"Tool {tool['code']} reached its life ({dec_str(after)}/{dec_str(mx)})",
                {
                    "tool": tool["code"],
                    "usage": dec_str(after),
                    "max": dec_str(mx),
                },
                dedupe_key=f"tool_life:{tool['id']}:{tool.get('life_reset_count') or 0}",
            )
    row = one(s, tid, "tool_usage", uid)
    assert row
    return {"usage": row, "tool": tool, "life_reached": reached}


def _by_event(s: Session, tid: uuid.UUID, source: str, ext: str | None) -> Row | None:
    rows = (
        find(s, tid, "tool_usage", source=source, external_event_id=ext) if ext else []
    )
    return rows[0] if rows else None


def report_usage(
    s: Session,
    tid: uuid.UUID,
    tool_id: uuid.UUID,
    body: Row,
    user: Any,
    source: str = "manual",
) -> Row:
    """计数上报 / 手工调整：delta > 0 为上报；delta < 0 为调整，必须给 reason_id。

    返回 ``{data, tool, duplicate, life_reached}``。
    """
    ext = (str(body.get("external_event_id") or "").strip()) or None
    tool = _lock_tool(s, tid, tool_id)
    dup = _by_event(s, tid, source, ext)
    if dup:
        s.commit()
        return {
            "data": ser(s, tid, "tool_usage", [dup])[0],
            "tool": tool_brief(s, tid, tool),
            "duplicate": True,
            "life_reached": False,
        }
    delta = Decimal(str(body["delta"]))
    if delta == 0:
        raise http_422([("delta", "delta: must not be 0")])
    kind = "report" if delta > 0 else "adjust"
    if kind == "adjust" and not body.get("reason_id"):
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "reason_id"],
                    "msg": "reason_id: required for a negative adjustment",
                    "type": "reason_required",
                    "code": "reason_required",
                }
            ],
        )
    if body.get("reason_id") and not one(s, tid, "reason_code", body["reason_id"]):
        raise http_422([("reason_id", "reason_id: not found")])
    errs = [
        ((k,), f"{k}: not found")
        for k, ent in (("lot_id", "lot"), ("equipment_id", "equipment"))
        if body.get(k) and not one(s, tid, ent, body[k])
    ]
    if errs:
        raise http_422(errs)
    at = event_time(body.get("occurred_at"), "occurred_at")
    try:
        with s.begin_nested():
            r = count(
                s,
                tid,
                tool,
                delta,
                kind,
                user,
                at=at,
                lot_id=body.get("lot_id"),
                equipment_id=body.get("equipment_id"),
                reason_id=body.get("reason_id"),
                comment=body.get("comment"),
                source=source,
                external_event_id=ext,
            )
    except IntegrityError:
        s.rollback()
        dup = _by_event(s, tid, source, ext)
        if not dup:
            raise
        return {
            "data": ser(s, tid, "tool_usage", [dup])[0],
            "tool": tool_brief(s, tid, _lock_tool(s, tid, tool_id)),
            "duplicate": True,
            "life_reached": False,
        }
    s.commit()
    return {
        "data": ser(s, tid, "tool_usage", [r["usage"]])[0],
        "tool": tool_brief(s, tid, r["tool"]),
        "duplicate": False,
        "life_reached": r["life_reached"],
    }


def reset(s: Session, tid: uuid.UUID, tool_id: uuid.UUID, body: Row, user: Any) -> Row:
    """修磨 / 翻新：计数清零、life_reset_count + 1、pending_maintenance → available。"""
    tool = _lock_tool(s, tid, tool_id)
    if not one(s, tid, "reason_code", body["reason_id"]):
        raise http_422([("reason_id", "reason_id: not found")])
    _mx, used = tool_life(s, tid, tool)
    n = (tool.get("life_reset_count") or 0) + 1
    st = (
        "available"
        if tool["tool_status"] == "pending_maintenance"
        else tool["tool_status"]
    )
    _upd(s, tid, "tool", tool["id"], user, life_reset_count=n, tool_status=st)
    tool.update(life_reset_count=n, tool_status=st)
    r = count(
        s,
        tid,
        tool,
        -used,
        "reset",
        user,
        reason_id=body["reason_id"],
        comment=body.get("comment"),
    )
    audit(
        s,
        tid,
        ENTITIES["tool"],
        "reset",
        tool,
        user,
        {"usage_count": (dec_str(used), "0")},
    )
    s.commit()
    return {
        "data": ser(s, tid, "tool_usage", [r["usage"]])[0],
        "tool": tool_brief(s, tid, r["tool"]),
    }


def _open_mount(s: Session, tid: uuid.UUID, tool_id: Any) -> Row | None:
    rows = [
        r
        for r in find(s, tid, "tool_mount_log", tool_id=tool_id)
        if not r["unmounted_at"]
    ]
    return rows[0] if rows else None


def _mount(
    s: Session, tid: uuid.UUID, tool: Row, eq: Row, body: Row, user: Any, at: datetime
) -> Row:
    if tool["tool_status"] not in USABLE:
        raise _conflict(
            "tool_not_usable",
            f"tool {tool['code']} is {tool['tool_status']}",
            tool_status=tool["tool_status"],
        )
    cur = _open_mount(s, tid, tool["id"])
    if cur:
        raise _conflict(
            "tool_already_mounted",
            f"tool {tool['code']} is already mounted",
            mount_id=str(cur["id"]),
            equipment_id=str(cur["equipment_id"]),
        )
    port = (str(body.get("port_code") or "").strip()) or None
    if port:
        t = TABLES["tool_mount_log"]
        busy = (
            conn(s)
            .execute(
                sa.select(t.c.id, t.c.tool_id).where(
                    t.c.tenant_id == tid,
                    t.c.equipment_id == eq["id"],
                    t.c.port_code == port,
                    t.c.unmounted_at.is_(None),
                )
            )
            .first()
        )
        if busy:
            raise _conflict(
                "tool_position_occupied",
                f"position {port} of {eq['code']} already holds a tool",
                mount_id=str(busy.id),
                tool_id=str(busy.tool_id),
            )
    _mx, used = tool_life(s, tid, tool)
    mid = _ins(
        s,
        tid,
        "tool_mount_log",
        user,
        tool_id=tool["id"],
        equipment_id=eq["id"],
        sub_unit_id=body.get("sub_unit_id"),
        port_code=port,
        mounted_at=at,
        usage_at_mount=used,
        comment=body.get("comment"),
        source="manual",
        username=actor_name(user),
    )
    _upd(
        s,
        tid,
        "tool",
        tool["id"],
        user,
        equipment_id=eq["id"],
        sub_unit_id=body.get("sub_unit_id"),
        mounted_at=at,
    )
    tool.update(equipment_id=eq["id"], mounted_at=at)
    audit(
        s, tid, ENTITIES["tool"], "mount", tool, user, {"equipment": (None, eq["code"])}
    )
    row = one(s, tid, "tool_mount_log", mid)
    assert row
    return row


def _unmount(
    s: Session,
    tid: uuid.UUID,
    tool: Row,
    reason: str,
    user: Any,
    at: datetime,
    replaced_by: Any = None,
    comment: str | None = None,
) -> Row:
    cur = _open_mount(s, tid, tool["id"])
    if not cur:
        raise _conflict("tool_not_mounted", f"tool {tool['code']} is not mounted")
    if at < cur["mounted_at"]:
        raise http_422([("unmounted_at", "unmounted_at: earlier than mounted_at")])
    _mx, used = tool_life(s, tid, tool)
    _upd(
        s,
        tid,
        "tool_mount_log",
        cur["id"],
        user,
        unmounted_at=at,
        unmount_reason=reason,
        replaced_by_tool_id=replaced_by,
        usage_at_unmount=used,
        comment=comment or cur.get("comment"),
    )
    st = "available" if tool["tool_status"] == "in_use" else tool["tool_status"]
    _upd(
        s,
        tid,
        "tool",
        tool["id"],
        user,
        equipment_id=None,
        sub_unit_id=None,
        mounted_at=None,
        tool_status=st,
    )
    tool.update(equipment_id=None, mounted_at=None, tool_status=st)
    audit(s, tid, ENTITIES["tool"], "unmount", tool, user, {"reason": (None, reason)})
    row = one(s, tid, "tool_mount_log", cur["id"])
    assert row
    return row


def mount(s: Session, tid: uuid.UUID, tool_id: uuid.UUID, body: Row, user: Any) -> Row:
    """安装工具到设备，返回 ``{data, tool}``。"""
    tool = _lock_tool(s, tid, tool_id)
    eq = one(s, tid, "equipment", body["equipment_id"])
    if not eq:
        raise http_422([("equipment_id", "equipment_id: not found")])
    if body.get("sub_unit_id") and not one(s, tid, "equipment", body["sub_unit_id"]):
        raise http_422([("sub_unit_id", "sub_unit_id: not found")])
    at = event_time(body.get("mounted_at"), "mounted_at")
    row = _mount(s, tid, tool, eq, body, user, at)
    s.commit()
    return {
        "data": ser(s, tid, "tool_mount_log", [row])[0],
        "tool": tool_brief(s, tid, tool),
    }


def unmount(
    s: Session, tid: uuid.UUID, tool_id: uuid.UUID, body: Row, user: Any
) -> Row:
    """卸下工具，返回 ``{data, tool}``。"""
    tool = _lock_tool(s, tid, tool_id)
    at = event_time(body.get("unmounted_at"), "unmounted_at")
    row = _unmount(s, tid, tool, body["reason"], user, at, comment=body.get("comment"))
    s.commit()
    return {
        "data": ser(s, tid, "tool_mount_log", [row])[0],
        "tool": tool_brief(s, tid, tool),
    }


def replace(
    s: Session, tid: uuid.UUID, tool_id: uuid.UUID, body: Row, user: Any
) -> Row:
    """一次事务卸旧装新（同设备、同位置、同子单元），返回 ``{unmounted, mounted, tool, new_tool}``。"""
    if body["new_tool_id"] == tool_id:
        raise http_422([("new_tool_id", "new_tool_id: must differ from the old tool")])
    old = _lock_tool(s, tid, tool_id)
    new = _lock_tool(s, tid, body["new_tool_id"])
    if new["fixture_id"] != old["fixture_id"]:
        raise http_422([("new_tool_id", "new_tool_id: must be the same tool type")])
    cur = _open_mount(s, tid, old["id"])
    if not cur:
        raise _conflict("tool_not_mounted", f"tool {old['code']} is not mounted")
    eq = one(s, tid, "equipment", cur["equipment_id"])
    assert eq
    at = now()
    gone = _unmount(
        s,
        tid,
        old,
        body["reason"],
        user,
        at,
        replaced_by=new["id"],
        comment=body.get("comment"),
    )
    put = _mount(
        s,
        tid,
        new,
        eq,
        {"port_code": cur["port_code"], "sub_unit_id": cur["sub_unit_id"]},
        user,
        at,
    )
    s.commit()
    return {
        "unmounted": ser(s, tid, "tool_mount_log", [gone])[0],
        "mounted": ser(s, tid, "tool_mount_log", [put])[0],
        "tool": tool_brief(s, tid, old),
        "new_tool": tool_brief(s, tid, new),
    }


def history(
    s: Session, tid: uuid.UUID, ent: str, tool_id: uuid.UUID, offset: int, limit: int
) -> Row:
    """工具的计数 / 装卸履历，按时间倒序分页。"""
    if not one(s, tid, "tool", tool_id):
        raise HTTPException(status_code=404, detail="tool not found")
    t = TABLES[ent]
    key = t.c.occurred_at if ent == "tool_usage" else t.c.mounted_at
    q = sa.select(t).where(t.c.tenant_id == tid, t.c.tool_id == tool_id)
    c = conn(s)
    n = c.execute(sa.select(sa.func.count()).select_from(q.subquery())).scalar()
    rows = [
        dict(r)
        for r in c.execute(
            q.order_by(key.desc(), t.c.created_at.desc(), t.c.id)
            .offset(offset)
            .limit(limit)
        ).mappings()
    ]
    return {"data": ser(s, tid, ent, rows), "count": int(n or 0)}


def tool_delta(s: Session, tid: uuid.UUID, tool: Row, lot: Row) -> Decimal:
    """Track Out 自动计数增量（按工具类型 count_basis）。

    per_track_out +1；per_wafer / per_unit 取本工步进站数量（良品 + 报废，D31 Decimal；
    touchdown 按每颗计 1，D53）；reported 只接受上报，返回 0。
    """
    fx = one(s, tid, "fixture", tool["fixture_id"]) if tool.get("fixture_id") else None
    basis = (fx or {}).get("count_basis") or "per_track_out"
    if basis == "reported":
        return Decimal(0)
    if basis == "per_track_out":
        return Decimal(1)
    return Decimal(str(lot.get("qty") or 0))


def num(v: Decimal | None) -> int | float | None:
    """出站响应老字段保持 JSON 数字（整数仍为 int），新接口用 ``dec_str``。"""
    if v is None:
        return None
    return int(v) if v == v.to_integral_value() else float(v)


tool_count = count
