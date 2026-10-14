"""设备报警联动（P2-B9，eap/p2/alarm-code-model.md 定稿 + D53）。

- set：写 ``alarm_log`` + ``alarm_lot``（发生时在该设备上 moved_in / running 的批次，加上报文
  里带的 ``lot_ids``），再按报警码 ``action`` 联动：
  * hold_lot / hold_both：逐批 ``hold_lot(source="equipment")``，原因码取报警码配置，否则系统
    原因码 ``equipment_alarm``；D17 终态批次跳过；
  * hold_equipment / hold_both：设备切到 ``target_e10_state``，E10 履历 ``source=equipment``
    （D53-3）；不在迁移表里的迁移跳过并记在 ``e10_change.skipped``；
  * 未登记 ALID（``unregistered=true``）或报警码停用：只记录，不联动（D53-2）。
- 幂等：同 (source, external_event_id) 或同设备同 ALID 已有 active 报警 → 返回已有记录，
  ``duplicate=true``，不重复 Hold；已清除后再报同 ALID 是新的一次发生（新记录、正常联动）。
- 未登记 ALID 也写 ``alarm_lot``（D55 OQ-3），但不 Hold、不切 E10。
- clear：写清除时间，不自动解除 Hold、不恢复 E10（人工确认），``cleared=true``；
  报警已不是 active（D55 OQ-5）→ 200、不改数据、``cleared=false``；同一清除事件号重放
  返回原记录（``duplicate=true``）。
- 事件时间超前服务器 5 分钟以上 → 422 ``time_in_future``（D55 OQ-2）。
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.models import actor_name
from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, TABLES
from app.core.spec.errors import http_422
from app.core.spec.serialize import serialize
from app.mes.common.query import find, one
from app.mes.common.rows import _ins, _upd
from app.mes.equipment.service import e10_current, e10_log
from app.mes.execution.hold import default_reason, hold_lot

Row = dict[str, Any]
CLOCK_SKEW = timedelta(minutes=5)  # set_at / cleared_at 允许超前服务器时间的上限
EQUIPMENT_ALARM = "equipment_alarm"
RAW_MAX = 65_536  # raw JSON 序列化后的上限（字节）
LOG = "alarm_log"


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"code": "alarm_not_found", "message": "alarm not found"},
    )


def _time(v: datetime | None, field: str) -> datetime:
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


def lookup_code(s: Session, tid: uuid.UUID, eq: Row, alid: str) -> Row | None:
    """报警码：单台设备覆盖优先，其次设备类型级。"""
    t = TABLES["alarm_code"]
    rows = [
        dict(r)
        for r in conn(s)
        .execute(sa.select(t).where(t.c.tenant_id == tid, t.c.alid == alid))
        .mappings()
    ]
    own = [r for r in rows if r["equipment_id"] == eq["id"]]
    typ = [
        r
        for r in rows
        if r["equipment_id"] is None
        and r["equipment_type_id"] == eq.get("equipment_type_id")
    ]
    pick = own or typ
    return pick[0] if pick else None


def _alarm_reason(s: Session, tid: uuid.UUID, code: Row) -> Row:
    rr = one(s, tid, "reason_code", code.get("hold_reason_id"))
    if rr and rr["reason_type"] == "hold":
        return rr
    rs = [
        r
        for r in find(s, tid, "reason_code", reason_type="hold")
        if r["code"] == EQUIPMENT_ALARM and r["is_active"]
    ]
    return rs[0] if rs else default_reason(s, tid, "hold")


def _lots_on(s: Session, tid: uuid.UUID, eq_id: Any) -> list[Row]:
    t = TABLES["lot"]
    return [
        dict(r)
        for r in conn(s)
        .execute(
            sa.select(t)
            .where(
                t.c.tenant_id == tid,
                t.c.equipment_id == eq_id,
                t.c.lot_status.in_(("moved_in", "running")),
            )
            .order_by(t.c.code)
        )
        .mappings()
    ]


def _e10(s: Session, tid: uuid.UUID, eq: Row, code: Row, user: Any) -> Row:
    to = one(s, tid, "e10_state", code.get("target_e10_state_id"))
    if not to:
        return {"skipped": "no target E10 state"}
    cur = e10_current(s, tid, eq)
    if cur and cur["id"] == to["id"]:
        return {"skipped": f"already {to['code']}", "to": to["code"]}
    if cur and not find(
        s, tid, "e10_transition", from_state_id=cur["id"], to_state_id=to["id"]
    ):
        return {
            "skipped": f"{cur['code']} -> {to['code']} not allowed",
            "from": cur["code"],
            "to": to["code"],
        }
    _upd(s, tid, "equipment", eq["id"], user, e10_state_id=to["id"])
    e10_log(s, tid, eq, cur, to, "equipment", user, None, f"alarm {code['alid']}")
    audit(
        s,
        tid,
        ENTITIES["equipment"],
        "e10",
        eq,
        user,
        {
            "e10_state": (cur and cur["code"], to["code"]),
            "trigger": (None, "equipment"),
        },
    )
    return {"from": cur and cur["code"], "to": to["code"]}


def detail(s: Session, tid: uuid.UUID, row: Row) -> Row:
    """报警详情：履历行 + 设备编码 + 关联批次。"""
    out = serialize(s, tid, ENTITIES[LOG], [row])[0]
    eq = one(s, tid, "equipment", row["equipment_id"])
    out["equipment_code"] = eq and eq["code"]
    lt, al = TABLES["lot"], TABLES["alarm_lot"]
    out["lots"] = [
        {"lot_id": str(r.id), "lot_code": r.code}
        for r in conn(s).execute(
            sa.select(lt.c.id, lt.c.code)
            .join(al, al.c.lot_id == lt.c.id)
            .where(al.c.tenant_id == tid, al.c.alarm_log_id == row["id"])
            .order_by(lt.c.code)
        )
    ]
    return out


def _by_event(s: Session, tid: uuid.UUID, source: str, ext: str | None) -> Row | None:
    rows = find(s, tid, LOG, source=source, external_event_id=ext) if ext else []
    return rows[0] if rows else None


def set_alarm(
    s: Session,
    tid: uuid.UUID,
    eq_id: uuid.UUID,
    body: Row,
    user: Any,
    source: str = "manual",
) -> Row:
    """登记报警（人工 / EAP / 模拟器共用），返回 ``{data, duplicate}``。"""
    et = TABLES["equipment"]
    eqr = (
        conn(s)
        .execute(
            sa.select(et)
            .where(et.c.tenant_id == tid, et.c.id == eq_id)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not eqr:
        raise HTTPException(status_code=404, detail="equipment not found")
    eq = dict(eqr)
    alid = str(body["alid"]).strip()
    if not alid:
        raise http_422([("alid", "alid: required")])
    ext = (str(body.get("external_event_id") or "").strip()) or None
    dup = _by_event(s, tid, source, ext)
    if not dup:
        act = find(s, tid, LOG, equipment_id=eq["id"], alid=alid, alarm_status="active")
        dup = act[0] if act else None
    if dup:
        s.commit()
        return {"data": detail(s, tid, dup), "duplicate": True}
    at = _time(body.get("set_at"), "set_at")
    lots: list[Row] = []
    seen: set[Any] = set()
    errs = []
    for i, lid in enumerate(body.get("lot_ids") or []):
        lot = one(s, tid, "lot", lid)
        if not lot:
            errs.append((("lot_ids", i), "lot not found"))
        elif lot["id"] not in seen:
            seen.add(lot["id"])
            lots.append(lot)
    if errs:
        raise http_422(errs)
    for lot in _lots_on(s, tid, eq["id"]):
        if lot["id"] not in seen:
            seen.add(lot["id"])
            lots.append(lot)
    code = lookup_code(s, tid, eq, alid)
    linked = bool(code and code["is_active"])
    action = code["action"] if linked and code else "none"
    aid = _ins(
        s,
        tid,
        LOG,
        user,
        equipment_id=eq["id"],
        alarm_code_id=code and code["id"],
        unregistered=code is None,
        alid=alid,
        alcd_raw=body.get("alcd_raw"),
        alarm_text=(body.get("alarm_text") or (code and code.get("text_en")) or None),
        severity=code and code["severity"],
        action=action,
        alarm_status="active",
        set_at=at,
        raw=body.get("raw"),
        comment=body.get("comment"),
        source=source,
        external_event_id=ext,
        username=actor_name(user),
    )
    for lot in lots:
        _ins(s, tid, "alarm_lot", user, alarm_log_id=aid, lot_id=lot["id"])
    hold_ids: list[str] = []
    skipped: list[str] = []
    e10: Row | None = None
    if code and action in ("hold_lot", "hold_both"):
        reason = _alarm_reason(s, tid, code)
        for lot in lots:
            hid = hold_lot(
                s,
                tid,
                lot,
                user,
                reason,
                hold_type="auto",
                source="equipment",
                comment=f"alarm {alid} on {eq['code']}",
                details={"alarm_log_id": str(aid), "alid": alid},
            )
            if hid:
                hold_ids.append(str(hid))
            else:
                skipped.append(lot["code"])
    if code and action in ("hold_equipment", "hold_both"):
        e10 = _e10(s, tid, eq, code, user)
    _upd(
        s,
        tid,
        LOG,
        aid,
        user,
        hold_ids={"holds": hold_ids, "skipped_lots": skipped}
        if hold_ids or skipped
        else None,
        e10_change=e10,
    )
    row = one(s, tid, LOG, aid)
    assert row
    audit(s, tid, ENTITIES[LOG], "alarm_set", row, user, {"alid": (None, alid)})
    s.commit()
    row = one(s, tid, LOG, aid)
    assert row
    return {"data": detail(s, tid, row), "duplicate": False}


def clear_alarm(
    s: Session,
    tid: uuid.UUID,
    alarm_id: uuid.UUID,
    body: Row,
    user: Any,
    source: str = "manual",
) -> Row:
    """清除报警（不自动解除 Hold / 恢复 E10），返回 ``{data, duplicate}``。"""
    t = TABLES[LOG]
    r = (
        conn(s)
        .execute(
            sa.select(t)
            .where(t.c.tenant_id == tid, t.c.id == alarm_id)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    if not r:
        raise _not_found()
    row = dict(r)
    ext = (str(body.get("external_event_id") or "").strip()) or None
    if row["alarm_status"] == "cleared":
        # D55（OQ-5）：没有对应的 active 报警 → 200、不改任何数据；同一清除事件重放返回原记录
        replay = bool(
            ext
            and row.get("clear_event_id") == ext
            and row.get("clear_source") == source
        )
        s.commit()
        return {"data": detail(s, tid, row), "duplicate": replay, "cleared": False}
    at = _time(body.get("cleared_at"), "cleared_at")
    if at < row["set_at"]:
        raise http_422([("cleared_at", "cleared_at: earlier than set_at")])
    _upd(
        s,
        tid,
        LOG,
        row["id"],
        user,
        alarm_status="cleared",
        cleared_at=at,
        cleared_by=actor_name(user),
        clear_source=source,
        clear_event_id=ext,
        comment=body.get("comment") or row.get("comment"),
    )
    audit(
        s,
        tid,
        ENTITIES[LOG],
        "alarm_clear",
        row,
        user,
        {"alarm_status": ("active", "cleared")},
    )
    s.commit()
    new = one(s, tid, LOG, row["id"])
    assert new
    return {"data": detail(s, tid, new), "duplicate": False, "cleared": True}


def clear_by_alid(
    s: Session,
    tid: uuid.UUID,
    eq_id: uuid.UUID,
    alid: str,
    body: Row,
    user: Any,
    source: str = "manual",
) -> Row:
    """按 (设备, ALID) 清除（EAP 上报只带 ALID）。

    同一清除事件号重放 → 原记录、``duplicate=true``、``cleared=false``；该设备该 ALID 没有
    active 报警 → 200、``data=null``、``cleared=false``，不建记录（D55 OQ-5）；否则同按 id 清除。
    """
    if not one(s, tid, "equipment", eq_id):
        raise HTTPException(status_code=404, detail="equipment not found")
    alid = str(alid).strip()
    if not alid:
        raise http_422([("alid", "alid: required")])
    ext = (str(body.get("external_event_id") or "").strip()) or None
    if ext:
        done = find(
            s,
            tid,
            LOG,
            equipment_id=eq_id,
            clear_source=source,
            clear_event_id=ext,
        )
        if done:
            s.commit()
            return {
                "data": detail(s, tid, done[0]),
                "duplicate": True,
                "cleared": False,
            }
    _time(body.get("cleared_at"), "cleared_at")
    act = find(s, tid, LOG, equipment_id=eq_id, alid=alid, alarm_status="active")
    if not act:
        s.commit()
        return {"data": None, "duplicate": False, "cleared": False}
    return clear_alarm(s, tid, act[0]["id"], body, user, source)


def get_alarm(s: Session, tid: uuid.UUID, alarm_id: uuid.UUID) -> Row:
    """报警详情；不存在 404 ``alarm_not_found``。"""
    row = one(s, tid, LOG, alarm_id)
    if not row:
        raise _not_found()
    return detail(s, tid, row)


def list_alarms(
    s: Session,
    tid: uuid.UUID,
    *,
    offset: int,
    limit: int,
    equipment_id: uuid.UUID | None = None,
    status: str | None = None,
    alid: str | None = None,
    unregistered: bool | None = None,
    lot_id: uuid.UUID | None = None,
    set_from: datetime | None = None,
    set_to: datetime | None = None,
) -> Row:
    """报警履历分页（按发生时间倒序）；``lot_id`` 经 ``alarm_lot`` 反查。"""
    t, al = TABLES[LOG], TABLES["alarm_lot"]
    q = sa.select(t).where(t.c.tenant_id == tid)
    if equipment_id:
        q = q.where(t.c.equipment_id == equipment_id)
    if status:
        q = q.where(t.c.alarm_status == status)
    if alid:
        q = q.where(t.c.alid == alid.strip())
    if unregistered is not None:
        q = q.where(t.c.unregistered.is_(unregistered))
    if lot_id:
        q = q.where(
            t.c.id.in_(
                sa.select(al.c.alarm_log_id).where(
                    al.c.tenant_id == tid, al.c.lot_id == lot_id
                )
            )
        )
    if set_from:
        q = q.where(t.c.set_at >= set_from)
    if set_to:
        q = q.where(t.c.set_at < set_to)
    c = conn(s)
    count = c.execute(sa.select(sa.func.count()).select_from(q.subquery())).scalar()
    rows = [
        dict(r)
        for r in c.execute(
            q.order_by(t.c.set_at.desc(), t.c.id).offset(offset).limit(limit)
        ).mappings()
    ]
    return {"data": [detail(s, tid, r) for r in rows], "count": int(count or 0)}
