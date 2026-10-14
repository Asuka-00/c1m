"""光罩状态机与动作（P3-B4，docs p3-reticle-model v0.8.2 + D64 补充 4/5、D66–D69 及补充）。

- 状态只经本模块改变：每次状态或 ``hold_reason`` 变化写 ``mes_reticle_status_log`` 一行
  （restore / scrap / hold 的 reason 写 ``reason`` 列，其余 comment 写 ``comment`` 列），同时写
  ``audit_log``（action=status，changes 含 status_code / hold_reason / reason）。
- 领域事件见 :mod:`app.mes.reticle.events`；调用方事务内写入，路由层提交。
- 409 一律 ``{code, message, status_code, hold_reason}``；422 列表格式带 code（D65）。
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.models import actor_name
from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, TABLES
from app.core.spec.errors import http_422
from app.core.spec.serialize import dec_str, serialize
from app.mes.common.query import one
from app.mes.common.rows import _ins, _upd
from app.mes.reticle.events import emit

Row = dict[str, Any]
CLOCK_SKEW = timedelta(minutes=5)
DEFAULT_WARN = Decimal("0.9")
# D64 补充 5 / D67 补充：系统 Hold 的严格度
SEVERITY = {"manual": 1, "incident": 2, "inspection_failed": 3}
# release 去向（D67 补充）：manual 回 status_before_hold
RELEASE_TO = {"incident": "inspecting", "inspection_failed": "pending_maintenance"}
# 四个流程动作：动作 -> (允许的原状态, 新状态, 置待检, 要求未挂载)
FLOW: dict[str, tuple[tuple[str, ...], str, bool]] = {
    "clean_start": (("available",), "dirty", False),
    "clean_complete": (("dirty",), "inspecting", True),
    "repair_complete": (("pending_maintenance",), "inspecting", True),
    "inspect_start": (("available",), "inspecting", False),
}
# D69 补充：仍有未关闭挂载记录时 409 still_mounted 的动作
NEED_UNMOUNTED = {
    "restore",
    "life_reset",
    "repair_complete",
    "inspect_start",
    "clean_start",
}
HOLDABLE = ("available", "in_use", "dirty", "inspecting", "pending_maintenance")


# ---------------- 基础 ----------------
def conflict(
    code: str, message: str, rt: Row | None = None, **extra: Any
) -> HTTPException:
    """409 业务冲突（对象格式，带当前状态）。"""
    d: Row = {"code": code, "message": message}
    if rt is not None:
        d.update(status_code=rt["status_code"], hold_reason=rt.get("hold_reason"))
    return HTTPException(status_code=409, detail={**d, **extra})


def _invalid(rt: Row, action: str) -> HTTPException:
    return conflict(
        "invalid_transition",
        f"reticle {rt['code']}: {action} not allowed from {rt['status_code']}",
        rt,
    )


def lock(s: Session, tid: uuid.UUID, rid: Any) -> Row:
    """加行锁读取光罩；不存在（含跨租户）404。"""
    t = TABLES["reticle"]
    r = (
        conn(s)
        .execute(
            sa.select(t).where(t.c.tenant_id == tid, t.c.id == rid).with_for_update()
        )
        .mappings()
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="reticle not found")
    return dict(r)


def get(s: Session, tid: uuid.UUID, rid: Any) -> Row:
    """读取光罩（不加锁）；不存在 404。"""
    r = one(s, tid, "reticle", rid)
    if not r:
        raise HTTPException(status_code=404, detail="reticle not found")
    return r


def _dec(v: Any) -> Decimal:
    return Decimal(str(v or 0))


def ser(s: Session, tid: uuid.UUID, ent: str, rows: list[Row]) -> list[Row]:
    """序列化：时间 UTC Z（D45），定点小数字段为十进制字符串（D50）。"""
    out = serialize(s, tid, ENTITIES[ent], rows)
    dec = [f.column for f in ENTITIES[ent].all_fields if f.type == "float" and f.scale]
    for o, r in zip(out, rows, strict=True):
        for k in dec:
            if k in r:
                o[k] = dec_str(r[k])
    return out


def life_state(rt: Row) -> str:
    """``ok`` / ``warning`` / ``reached``（D54-5）。"""
    mx = rt.get("max_shots")
    if mx is None:
        return "ok"
    used, mx = _dec(rt.get("shot_count")), _dec(mx)
    if used >= mx:
        return "reached"
    wr = _dec(rt["warn_ratio"]) if rt.get("warn_ratio") is not None else DEFAULT_WARN
    return "warning" if used >= mx * wr else "ok"


def brief(s: Session, tid: uuid.UUID, rid: Any) -> Row:
    """光罩当前行（序列化）+ ``life_state``。"""
    row = get(s, tid, rid)
    out = ser(s, tid, "reticle", [row])[0]
    out["life_state"] = life_state(row)
    return out


def event_time(v: datetime | None, field: str) -> datetime:
    """事件时间：缺省服务器时间；严格超前 5 分钟以上 422 value_error ctx.reason=future_time（D82-4；接口层请求体校验已先拦）。"""
    cur = now()
    if v is None:
        return cur
    if v.tzinfo is None:
        raise http_422([(field, f"{field}: timezone required", "timezone_required")])
    v = v.astimezone(UTC)
    if v > cur + CLOCK_SKEW:
        raise http_422(
            [
                (
                    field,
                    f"{field}: more than 5 minutes in the future",
                    "value_error",
                    {"reason": "future_time"},
                )
            ]
        )
    return v


def latest_event_at(
    s: Session, tid: uuid.UUID, rid: Any, *, usage: bool = False
) -> datetime | None:
    """光罩最近一次事件时间：状态履历时间与历次下机时间中最晚者（检查记录不算，D82-4）。

    ``usage``：事故补录另算最近一次计数时间（D82 补充）；上机 / 下机不算 usage。
    """
    log, mnt = TABLES["reticle_status_log"], TABLES["reticle_mount_log"]
    srcs = [(log, "at"), (mnt, "unmounted_at")]
    if usage:
        srcs.append((TABLES["reticle_usage"], "occurred_at"))
    vals = [
        conn(s)
        .execute(
            sa.select(sa.func.max(t.c[c])).where(
                t.c.tenant_id == tid, t.c.reticle_id == rid
            )
        )
        .scalar()
        for t, c in srcs
    ]
    got = [v for v in vals if v is not None]
    return max(got) if got else None


def check_order(
    s: Session,
    tid: uuid.UUID,
    rt: Row,
    given: datetime | None,
    field: str,
    *,
    usage: bool = False,
) -> None:
    """补录时间早于该光罩最近一次事件时间 → 409 ``time_out_of_order``（相等合法，D82-4）。"""
    if given is None:
        return
    last = latest_event_at(s, tid, rt["id"], usage=usage)
    if last is not None and given < last:
        raise conflict(
            "time_out_of_order",
            f"{field} is earlier than the latest event of reticle {rt['code']}",
            rt,
            field=field,
            latest_event_at=last.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        )


def _set(s: Session, tid: uuid.UUID, rt: Row, user: Any, **vals: Any) -> None:
    _upd(s, tid, "reticle", rt["id"], user, **vals)
    rt.update(vals)


def transition(
    s: Session,
    tid: uuid.UUID,
    rt: Row,
    user: Any,
    to: str,
    action: str,
    *,
    hold_reason: str | None = None,
    reason: str | None = None,
    comment: str | None = None,
    trigger: str = "manual",
    at: datetime | None = None,
    **vals: Any,
) -> Row:
    """改状态 / hold_reason 并写状态履历 + 审计；返回 ``{from, to}``。

    ``at``：状态履历时间，补录事件（上机 / 下机 / 事故）传事件时间，缺省服务器时间。
    """
    frm, hr0 = rt["status_code"], rt.get("hold_reason")
    _set(s, tid, rt, user, status_code=to, hold_reason=hold_reason, **vals)
    at = at or now()
    _ins(
        s,
        tid,
        "reticle_status_log",
        user,
        reticle_id=rt["id"],
        from_status=frm,
        to_status=to,
        action=action,
        hold_reason_from=hr0,
        hold_reason_to=hold_reason,
        reason=reason,
        comment=comment,
        trigger=trigger,
        username=actor_name(user),
        at=at,
    )
    ch: Row = {"status_code": (frm, to), "action": (None, action)}
    if hr0 != hold_reason:
        ch["hold_reason"] = (hr0, hold_reason)
    if reason:
        ch["reason"] = (None, reason)
    audit(s, tid, ENTITIES["reticle"], "status", rt, user, ch)
    return {"from": frm, "to": to}


# ---------------- 挂载 ----------------
def open_mount(s: Session, tid: uuid.UUID, rid: Any) -> Row | None:
    """未关闭的挂载记录（部分唯一索引保证至多一条）。"""
    t = TABLES["reticle_mount_log"]
    r = (
        conn(s)
        .execute(
            sa.select(t).where(
                t.c.tenant_id == tid, t.c.reticle_id == rid, t.c.unmounted_at.is_(None)
            )
        )
        .mappings()
        .first()
    )
    return dict(r) if r else None


def _close_mount(
    s: Session,
    tid: uuid.UUID,
    rt: Row,
    user: Any,
    reason: str,
    at: datetime | None = None,
    source: str = "manual",
    external_event_id: str | None = None,
) -> Row | None:
    """关闭挂载记录、清 equipment_id / mounted_at（不改状态、不发事件）。

    D80 G1：下机单独记一行（``event_type=unmount``，带 source / external_event_id，
    ``mount_log_id`` 指向上机行）；上机行只回填 unmounted_at / 原因 / 下机计数，不写事件号。
    """
    cur = open_mount(s, tid, rt["id"])
    if not cur:
        return None
    # 未传时间（hold / scrap 顺带卸载等）取服务器时间，但不早于上机时间
    at = at or max(now(), cur["mounted_at"])
    if at < cur["mounted_at"]:  # D82 补充：早于对应上机时间（相等合法）
        raise conflict(
            "time_out_of_order",
            f"unmounted_at is earlier than mounted_at of reticle {rt['code']}",
            rt,
            field="unmounted_at",
            latest_event_at=cur["mounted_at"]
            .astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
        )
    shots = _dec(rt.get("shot_count"))
    ev = _ins(
        s,
        tid,
        "reticle_mount_log",
        user,
        reticle_id=rt["id"],
        event_type="unmount",
        mount_log_id=cur["id"],
        equipment_id=cur["equipment_id"],
        sub_unit_id=cur.get("sub_unit_id"),
        slot_code=cur.get("slot_code"),
        mounted_at=cur["mounted_at"],
        unmounted_at=at,
        unmount_reason=reason,
        shots_at_mount=cur.get("shots_at_mount"),
        shots_at_unmount=shots,
        source=source,
        external_event_id=external_event_id,
        username=actor_name(user),
    )
    _upd(
        s,
        tid,
        "reticle_mount_log",
        cur["id"],
        user,
        unmounted_at=at,
        unmount_reason=reason,
        shots_at_unmount=shots,
    )
    _set(s, tid, rt, user, equipment_id=None, mounted_at=None)
    cur.update(
        unmounted_at=at,
        unmount_reason=reason,
        shots_at_unmount=shots,
        unmount_event_id=ev,
        unmount_source=source,
        unmount_external_event_id=external_event_id,
    )
    return cur


def _unmount_event(s: Session, tid: uuid.UUID, rt: Row, user: Any, m: Row) -> None:
    emit(
        s,
        tid,
        "reticle.unmounted",
        rt,
        user,
        {
            "mount_id": str(m["id"]),
            "unmount_event_id": str(m["unmount_event_id"]),
            "equipment_id": str(m["equipment_id"]),
            "unmount_reason": m["unmount_reason"],
            "shots_at_unmount": dec_str(m["shots_at_unmount"]),
            "source": m["unmount_source"],
            "external_event_id": m["unmount_external_event_id"],
        },
    )


def mount(s: Session, tid: uuid.UUID, rid: Any, body: Row, user: Any) -> Row:
    """挂载（D69 Q7 重复挂载 409 already_mounted；Q8 不限机台类型）。"""
    rt = lock(s, tid, rid)
    eq = one(s, tid, "equipment", body["equipment_id"])
    if not eq:
        raise http_422([("equipment_id", "equipment_id: not found", "ref_not_found")])
    if body.get("sub_unit_id") and not one(s, tid, "equipment", body["sub_unit_id"]):
        raise http_422([("sub_unit_id", "sub_unit_id: not found", "ref_not_found")])
    cur = open_mount(s, tid, rt["id"])
    if cur:
        raise conflict(
            "already_mounted",
            f"reticle {rt['code']} is already mounted",
            rt,
            mount_id=str(cur["id"]),
            equipment_id=str(cur["equipment_id"]),
        )
    if rt["status_code"] != "available":
        raise conflict(
            "reticle_unavailable", f"reticle {rt['code']} is {rt['status_code']}", rt
        )
    slot = (str(body.get("slot_code") or "").strip()) or None
    if slot:
        t = TABLES["reticle_mount_log"]
        busy = (
            conn(s)
            .execute(
                sa.select(t.c.id, t.c.reticle_id).where(
                    t.c.tenant_id == tid,
                    t.c.equipment_id == eq["id"],
                    t.c.slot_code == slot,
                    t.c.unmounted_at.is_(None),
                )
            )
            .first()
        )
        if busy:
            raise conflict(
                "slot_occupied",
                f"slot {slot} of {eq['code']} already holds a reticle",
                rt,
                mount_id=str(busy.id),
                reticle_id=str(busy.reticle_id),
            )
    check_order(s, tid, rt, body.get("mounted_at"), "mounted_at")
    at = event_time(body.get("mounted_at"), "mounted_at")
    mid = _ins(
        s,
        tid,
        "reticle_mount_log",
        user,
        reticle_id=rt["id"],
        equipment_id=eq["id"],
        sub_unit_id=body.get("sub_unit_id"),
        slot_code=slot,
        mounted_at=at,
        shots_at_mount=_dec(rt.get("shot_count")),
        comment=body.get("comment"),
        event_type="mount",
        source="manual",
        username=actor_name(user),
    )
    _set(
        s,
        tid,
        rt,
        user,
        mount_count=(rt.get("mount_count") or 0) + 1,
        first_used_at=rt.get("first_used_at") or at,
    )
    transition(
        s,
        tid,
        rt,
        user,
        "in_use",
        "mount",
        at=at,
        comment=body.get("comment"),
        equipment_id=eq["id"],
        mounted_at=at,
    )
    emit(
        s,
        tid,
        "reticle.mounted",
        rt,
        user,
        {
            "mount_id": str(mid),
            "equipment_id": str(eq["id"]),
            "slot_code": slot,
            "source": "manual",
            "external_event_id": None,
        },
    )
    row = one(s, tid, "reticle_mount_log", mid)
    assert row
    return {"data": ser(s, tid, "reticle_mount_log", [row])[0]}


def unmount(
    s: Session,
    tid: uuid.UUID,
    rid: Any,
    body: Row,
    user: Any,
    *,
    source: str = "manual",
    external_event_id: str | None = None,
) -> Row:
    """卸载：in_use → available；非 in_use 仍挂着只关挂载记录、不改状态；都发 unmounted（D69 补充）。

    D80 G1：下机单独记一行事件；带 ``external_event_id``（EAP / 模拟器）时按
    (tenant, source, external_event_id) 去重，重复上报返回首次记录且 ``duplicate=true``，
    不改状态、不发事件。手工接口不带事件号，响应不含 duplicate（幂等由 Idempotency-Key 负责）。
    """
    rt = lock(s, tid, rid)
    ext = (external_event_id or "").strip() or None
    if ext:
        t = TABLES["reticle_mount_log"]
        dup = (
            conn(s)
            .execute(
                sa.select(t).where(
                    t.c.tenant_id == tid,
                    t.c.source == source,
                    t.c.external_event_id == ext,
                )
            )
            .mappings()
            .first()
        )
        if dup:
            row = dict(dup)
            mount_row = one(s, tid, "reticle_mount_log", row.get("mount_log_id"))
            return {
                "data": ser(s, tid, "reticle_mount_log", [mount_row or row])[0],
                "unmount_event": ser(s, tid, "reticle_mount_log", [row])[0],
                "duplicate": True,
            }
    # 未挂载（含曾下机过）：先 invalid_transition，再做 time_out_of_order
    if open_mount(s, tid, rt["id"]) is None:
        raise conflict("invalid_transition", f"reticle {rt['code']} is not mounted", rt)
    check_order(s, tid, rt, body.get("unmounted_at"), "unmounted_at")
    at = event_time(body.get("unmounted_at"), "unmounted_at")
    m = _close_mount(s, tid, rt, user, "manual", at, source, ext)
    if not m:
        raise conflict("invalid_transition", f"reticle {rt['code']} is not mounted", rt)
    if rt["status_code"] == "in_use":
        transition(
            s,
            tid,
            rt,
            user,
            "available",
            "unmount",
            comment=body.get("comment"),
            at=at,
        )
    _unmount_event(s, tid, rt, user, m)
    ev = one(s, tid, "reticle_mount_log", m["unmount_event_id"])
    mount_row = one(s, tid, "reticle_mount_log", m["id"])
    out: Row = {
        "data": ser(s, tid, "reticle_mount_log", [mount_row or m])[0],
        "unmount_event": ser(s, tid, "reticle_mount_log", [ev])[0] if ev else None,
    }
    if ext:
        out["duplicate"] = False
    return out


# ---------------- Hold / release ----------------
def _enter_hold(
    s: Session,
    tid: uuid.UUID,
    rt: Row,
    user: Any,
    hold_reason: str,
    action: str,
    *,
    reason: str | None = None,
    trigger: str = "manual",
    event_at: datetime | None = None,
    **vals: Any,
) -> None:
    """进入 on_hold：仍挂着的同事务卸载（发 unmounted）；status_before_hold 记当时状态，in_use 记 available。

    ``event_at``：事故补录时间；顺带下机的 unmounted_at / 下机事件行与状态履历都记这个时间。
    """
    before = "available" if rt["status_code"] == "in_use" else rt["status_code"]
    m = _close_mount(
        s,
        tid,
        rt,
        user,
        "incident" if hold_reason == "incident" else "hold",
        event_at,
    )
    if m:
        _unmount_event(s, tid, rt, user, m)
    tr = transition(
        s,
        tid,
        rt,
        user,
        "on_hold",
        action,
        hold_reason=hold_reason,
        reason=reason,
        trigger=trigger,
        status_before_hold=before,
        at=event_at,
        **vals,
    )
    emit(
        s,
        tid,
        "reticle.held",
        rt,
        user,
        {
            **tr,
            "hold_reason": hold_reason,
            "status_before_hold": before,
            "reason": reason,
        },
    )


def system_hold(
    s: Session,
    tid: uuid.UUID,
    rt: Row,
    user: Any,
    hold_reason: str,
    action: str,
    event_at: datetime | None = None,
    **vals: Any,
) -> None:
    """系统 Hold（事故 / 检查不合格）：非 on_hold 进入；已 on_hold 时更严则升级（状态与 status_before_hold 不变）。"""
    if rt["status_code"] != "on_hold":
        _enter_hold(
            s,
            tid,
            rt,
            user,
            hold_reason,
            action,
            trigger="system",
            event_at=event_at,
            **vals,
        )
        return
    cur = rt.get("hold_reason") or "manual"
    if SEVERITY[hold_reason] <= SEVERITY[cur]:
        if vals:
            _set(s, tid, rt, user, **vals)
        return
    tr = transition(
        s,
        tid,
        rt,
        user,
        "on_hold",
        action,
        hold_reason=hold_reason,
        trigger="system",
        at=event_at,
        **vals,
    )
    emit(
        s,
        tid,
        "reticle.held",
        rt,
        user,
        {
            **tr,
            "hold_reason": hold_reason,
            "hold_reason_from": cur,
            "status_before_hold": rt.get("status_before_hold"),
            "escalated": True,
        },
    )


def hold(s: Session, tid: uuid.UUID, rid: Any, body: Row, user: Any) -> Row:
    """人工 Hold（不叠加：已 on_hold 409 invalid_transition，D67）。"""
    rt = lock(s, tid, rid)
    if rt["status_code"] not in HOLDABLE:
        raise _invalid(rt, "hold")
    _enter_hold(s, tid, rt, user, "manual", "hold", reason=body["reason"])
    return {"data": brief(s, tid, rid)}


def release(s: Session, tid: uuid.UUID, rid: Any, body: Row | None, user: Any) -> Row:
    """释放：去向按最终 hold_reason（incident→inspecting、inspection_failed→pending_maintenance、manual→status_before_hold）。"""
    rt = lock(s, tid, rid)
    if rt["status_code"] != "on_hold":
        raise _invalid(rt, "release")
    hr = rt.get("hold_reason") or "manual"
    to = RELEASE_TO.get(hr) or rt.get("status_before_hold") or "available"
    tr = transition(
        s,
        tid,
        rt,
        user,
        to,
        "release",
        comment=(body or {}).get("comment"),
        status_before_hold=None,
    )
    emit(s, tid, "reticle.released", rt, user, {**tr, "hold_reason": hr})
    return {"data": brief(s, tid, rid)}


# ---------------- 其他动作 ----------------
def _need_unmounted(s: Session, tid: uuid.UUID, rt: Row, action: str) -> None:
    if action in NEED_UNMOUNTED:
        m = open_mount(s, tid, rt["id"])
        if m:
            raise conflict(
                "still_mounted",
                f"reticle {rt['code']} is still mounted; unmount it first",
                rt,
                mount_id=str(m["id"]),
                equipment_id=str(m["equipment_id"]),
            )


def flow(
    s: Session, tid: uuid.UUID, rid: Any, action: str, body: Row | None, user: Any
) -> Row:
    """clean-start / clean-complete / repair-complete / inspect-start，发 reticle.status_changed。"""
    rt = lock(s, tid, rid)
    allowed, to, insp = FLOW[action]
    if rt["status_code"] not in allowed:
        raise _invalid(rt, action)
    _need_unmounted(s, tid, rt, action)  # D71-3：先 invalid_transition 再 still_mounted
    extra: Row = {"inspection_required": True} if insp else {}
    tr = transition(
        s, tid, rt, user, to, action, comment=(body or {}).get("comment"), **extra
    )
    emit(
        s,
        tid,
        "reticle.status_changed",
        rt,
        user,
        {**tr, "action": action.replace("_", "-")},
    )
    return {"data": brief(s, tid, rid)}


def restore(s: Session, tid: uuid.UUID, rid: Any, body: Row, user: Any) -> Row:
    """人工恢复 pending_maintenance → available（D66 Q14 / D67）；达上限 409 life_limit_reached。"""
    rt = lock(s, tid, rid)
    if rt["status_code"] != "pending_maintenance":
        raise _invalid(rt, "restore")
    _need_unmounted(s, tid, rt, "restore")
    if life_state(rt) == "reached":
        raise conflict(
            "life_limit_reached",
            f"reticle {rt['code']} is at its life limit; use life-reset",
            rt,
            shot_count=dec_str(rt.get("shot_count")),
            max_shots=dec_str(rt.get("max_shots")),
        )
    tr = transition(
        s,
        tid,
        rt,
        user,
        "available",
        "restore",
        reason=body["reason"],
        inspection_required=True,
    )
    emit(s, tid, "reticle.restored", rt, user, {**tr, "reason": body["reason"]})
    return {"data": brief(s, tid, rid)}


def life_reset(s: Session, tid: uuid.UUID, rid: Any, body: Row, user: Any) -> Row:
    """寿命复位：shot_count 清零、life_reset_count+1、kind=reset 计数记录（reason → comment，reason_id 空，D69 补充）。"""
    rt = lock(s, tid, rid)
    if rt["status_code"] != "pending_maintenance":
        raise _invalid(rt, "life-reset")
    _need_unmounted(s, tid, rt, "life_reset")
    used = _dec(rt.get("shot_count"))
    n = (rt.get("life_reset_count") or 0) + 1
    uid = _ins(
        s,
        tid,
        "reticle_usage",
        user,
        reticle_id=rt["id"],
        delta=-used,
        count_after=Decimal(0),
        kind="reset",
        occurred_at=now(),
        reason_id=None,
        comment=body["reason"],
        source="manual",
        username=actor_name(user),
        counted=True,
        estimated=False,
    )
    _set(s, tid, rt, user, shot_count=Decimal(0), life_reset_count=n)
    tr = transition(
        s, tid, rt, user, "available", "life_reset", inspection_required=True
    )
    emit(
        s,
        tid,
        "reticle.life_reset",
        rt,
        user,
        {
            **tr,
            "shots_before": dec_str(used),
            "life_reset_count": n,
            "reason": body["reason"],
        },
    )
    row = one(s, tid, "reticle_usage", uid)
    assert row
    return {"data": brief(s, tid, rid), "usage": ser(s, tid, "reticle_usage", [row])[0]}


def scrap(s: Session, tid: uuid.UUID, rid: Any, body: Row, user: Any) -> Row:
    """报废（终态）：挂着的同事务卸载但只发 reticle.scrapped（D69 补充）。"""
    rt = lock(s, tid, rid)
    if rt["status_code"] == "scrapped":
        raise _invalid(rt, "scrap")
    m = _close_mount(s, tid, rt, user, "scrap")
    tr = transition(
        s,
        tid,
        rt,
        user,
        "scrapped",
        "scrap",
        reason=body["reason"],
        status_before_hold=None,
    )
    payload: Row = {**tr, "reason": body["reason"]}
    if m:
        payload.update(
            equipment_id=str(m["equipment_id"]),
            shots_at_unmount=dec_str(m["shots_at_unmount"]),
        )
    emit(s, tid, "reticle.scrapped", rt, user, payload)
    return {"data": brief(s, tid, rid)}


# ---------------- 计数 ----------------
def _count(
    s: Session,
    tid: uuid.UUID,
    rt: Row,
    user: Any,
    delta: Decimal,
    kind: str,
    **vals: Any,
) -> uuid.UUID:
    """累加 shot 并写计数记录；跨过上限 → pending_maintenance（仅 available / in_use）+ life_reached。"""
    used = _dec(rt.get("shot_count"))
    after = used + delta
    if after < 0:
        raise http_422(
            [("delta", "delta: shot count cannot go below 0", "value_error")]
        )
    uid = _ins(
        s,
        tid,
        "reticle_usage",
        user,
        reticle_id=rt["id"],
        delta=delta,
        count_after=after,
        kind=kind,
        occurred_at=now(),
        username=actor_name(user),
        counted=True,
        estimated=False,
        **vals,
    )
    _set(s, tid, rt, user, shot_count=after)
    mx = rt.get("max_shots")
    if mx is not None and after >= _dec(mx) and used < _dec(mx):
        if rt["status_code"] in ("available", "in_use"):
            transition(
                s, tid, rt, user, "pending_maintenance", "system", trigger="system"
            )
        emit(
            s,
            tid,
            "reticle.life_reached",
            rt,
            user,
            {
                "shot_count": dec_str(after),
                "max_shots": dec_str(mx),
                "usage_id": str(uid),
                "source": vals.get("source"),
                "external_event_id": vals.get("external_event_id"),
            },
        )
    return uid


def usage(s: Session, tid: uuid.UUID, rid: Any, body: Row, user: Any) -> Row:
    """人工计数：delta>0 report，<0 adjust（必须 reason_id），source=manual（D66 Q16 / D68 Q22）。"""
    rt = lock(s, tid, rid)
    if rt["status_code"] == "scrapped":  # D72：报废后不计数、不发 life_reached
        raise _invalid(rt, "usage")
    delta = Decimal(str(body["delta"]))
    if delta == 0:
        raise http_422([("delta", "delta: must not be 0", "value_error")])
    kind = "report" if delta > 0 else "adjust"
    if kind == "adjust" and not body.get("reason_id"):
        raise http_422(
            [("reason_id", "reason_id: required for a negative adjustment", "missing")]
        )
    if body.get("reason_id") and not one(s, tid, "reason_code", body["reason_id"]):
        raise http_422([("reason_id", "reason_id: not found", "ref_not_found")])
    uid = _count(
        s,
        tid,
        rt,
        user,
        delta,
        kind,
        reason_id=body.get("reason_id"),
        comment=body.get("note"),
        source="manual",
        equipment_id=rt.get("equipment_id"),
    )
    row = one(s, tid, "reticle_usage", uid)
    assert row
    return {
        "data": ser(s, tid, "reticle_usage", [row])[0],
        "reticle": brief(s, tid, rid),
    }


# ---------------- 事故 / 检查 ----------------
def incident(s: Session, tid: uuid.UUID, rid: Any, body: Row, user: Any) -> Row:
    """事故录入（D68 Q20 + 补充）：非 scrapped 一律 on_hold(incident) + 待检；scrapped 409。"""
    rt = lock(s, tid, rid)
    if rt["status_code"] == "scrapped":
        raise _invalid(rt, "incident")
    errs = [
        (k, f"{k}: not found", "ref_not_found")
        for k, ent in (("equipment_id", "equipment"), ("lot_id", "lot"))
        if body.get(k) and not one(s, tid, ent, body[k])
    ]
    if errs:
        raise http_422(errs)
    at = event_time(body.get("occurred_at"), "occurred_at")
    cur = open_mount(s, tid, rt["id"])
    # 先判“早于本次上机”：上机本身就是最新事件之一，若先跑 check_order 这条分支永远走不到，
    # 返回的会是笼统的“早于最近事件”。未传 occurred_at（取服务器时间）不会早于上机。
    if body.get("occurred_at") and cur and at < cur["mounted_at"]:
        # D82 补充：顺带下机的时间早于本次上机 → 整体 409，什么都不写（事务不提交）
        raise conflict(
            "time_out_of_order",
            f"occurred_at is earlier than mounted_at of reticle {rt['code']}",
            rt,
            field="occurred_at",
            latest_event_at=cur["mounted_at"]
            .astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
        )
    check_order(s, tid, rt, body.get("occurred_at"), "occurred_at", usage=True)
    iid = _ins(
        s,
        tid,
        "reticle_incident",
        user,
        reticle_id=rt["id"],
        kind=body["kind"],
        occurred_at=at,
        equipment_id=body.get("equipment_id"),
        lot_id=body.get("lot_id"),
        description=body.get("description"),
        source="manual",
        username=actor_name(user),
    )
    system_hold(
        s,
        tid,
        rt,
        user,
        "incident",
        "incident",
        event_at=at,
        inspection_required=True,
    )
    emit(
        s,
        tid,
        "reticle.incident_recorded",
        rt,
        user,
        {
            "incident_id": str(iid),
            "kind": body["kind"],
            "hold_reason": rt.get("hold_reason"),
        },
    )
    row = one(s, tid, "reticle_incident", iid)
    assert row
    return {
        "data": ser(s, tid, "reticle_incident", [row])[0],
        "reticle": brief(s, tid, rid),
    }


def _exposed(
    s: Session, tid: uuid.UUID, rt: Row, start: datetime | None, end: datetime
) -> list[Row]:
    t, lot = TABLES["reticle_usage"], TABLES["lot"]
    q = (
        sa.select(
            t.c.lot_id,
            lot.c.code,
            t.c.operation_id,
            t.c.equipment_id,
            sa.func.min(t.c.occurred_at),
            sa.func.max(t.c.occurred_at),
            sa.func.sum(t.c.delta),
        )
        .join(lot, lot.c.id == t.c.lot_id)
        .where(
            t.c.tenant_id == tid,
            t.c.reticle_id == rt["id"],
            t.c.lot_id.is_not(None),
            t.c.occurred_at <= end,
        )
        .group_by(t.c.lot_id, lot.c.code, t.c.operation_id, t.c.equipment_id)
    )
    if start is not None:
        q = q.where(t.c.occurred_at >= start)
    from app.core.models import iso_utc

    return [
        {
            "lot_id": str(r[0]),
            "lot_code": r[1],
            "operation_id": r[2] and str(r[2]),
            "equipment_id": r[3] and str(r[3]),
            "first_exposed_at": iso_utc(r[4]),
            "last_exposed_at": iso_utc(r[5]),
            "wafer_qty": None,
            "shots": dec_str(r[6]),
        }
        for r in conn(s).execute(q)
    ]


def inspection(s: Session, tid: uuid.UUID, rid: Any, body: Row, user: Any) -> Row:
    """检查记录：pass inspecting→available；fail → on_hold(inspection_failed)（已 on_hold 按严格度升级）。"""
    rt = lock(s, tid, rid)
    if rt["status_code"] == "scrapped":  # D72
        raise _invalid(rt, "inspection")
    res = body["result"]
    ok_from = ("inspecting",) if res == "pass" else ("inspecting", "on_hold")
    if rt["status_code"] not in ok_from:
        raise _invalid(rt, f"inspection {res}")
    if body.get("equipment_id") and not one(s, tid, "equipment", body["equipment_id"]):
        raise http_422([("equipment_id", "equipment_id: not found", "ref_not_found")])
    check_order(s, tid, rt, body.get("inspected_at"), "inspected_at")
    at = event_time(body.get("inspected_at"), "inspected_at")
    # 时间窗起点：上次 pass → first_used_at → received_at（D64 C6）
    t = TABLES["reticle_inspection"]
    last_pass = (
        conn(s)
        .execute(
            sa.select(sa.func.max(t.c.inspected_at)).where(
                t.c.tenant_id == tid, t.c.reticle_id == rt["id"], t.c.result == "pass"
            )
        )
        .scalar()
    )
    iid = _ins(
        s,
        tid,
        "reticle_inspection",
        user,
        reticle_id=rt["id"],
        kind=body["kind"],
        result=res,
        defect_count=body.get("defect_count"),
        measured=body.get("measured"),
        equipment_id=body.get("equipment_id"),
        inspected_at=at,
        disposition=body.get("disposition") or "none",
        shots_at_inspection=_dec(rt.get("shot_count")),
        comment=body.get("comment"),
        username=actor_name(user),
    )
    from app.core.models import iso_utc

    if res == "pass":
        days = rt.get("inspection_interval_days")
        due = at + timedelta(days=days) if days else None
        tr = transition(
            s,
            tid,
            rt,
            user,
            "available",
            "inspection",
            comment=body.get("comment"),
            inspection_required=False,
            last_inspected_at=at,
            next_inspection_due_at=due,
        )
        emit(s, tid, "reticle.inspected", rt, user, {**tr, "inspection_id": str(iid)})
    else:
        system_hold(
            s,
            tid,
            rt,
            user,
            "inspection_failed",
            "inspection",
            inspection_required=True,
        )
        basis, start = "last_pass", last_pass
        if start is None:
            basis, start = "first_used_at", rt.get("first_used_at")
        if start is None:
            basis, start = "received_at", rt.get("received_at")
        emit(
            s,
            tid,
            "reticle.inspection_failed",
            rt,
            user,
            {
                "inspection_id": str(iid),
                "inspected_at": iso_utc(at),
                "window_start": start and iso_utc(start),
                "window_start_basis": basis,
                "exposed_lots": _exposed(s, tid, rt, start, at),
            },
        )
    row = one(s, tid, "reticle_inspection", iid)
    assert row
    return {
        "data": ser(s, tid, "reticle_inspection", [row])[0],
        "reticle": brief(s, tid, rid),
    }


# ---------------- 履历 ----------------
HISTORY = (
    ("reticle_mount_log", "mounted_at", "mount"),
    ("reticle_usage", "occurred_at", "usage"),
    ("reticle_inspection", "inspected_at", "inspection"),
    ("reticle_incident", "occurred_at", "incident"),
    ("reticle_status_log", "at", "status"),
)


def history(s: Session, tid: uuid.UUID, rid: Any, offset: int, limit: int) -> Row:
    """合并挂载 / 计数 / 检查 / 事故 / 状态履历，按时间倒序（RET-11）。"""
    get(s, tid, rid)
    items: list[tuple[datetime, datetime, Row]] = []
    for ent, key, typ in HISTORY:
        t = TABLES[ent]
        rows = [
            dict(r)
            for r in conn(s)
            .execute(sa.select(t).where(t.c.tenant_id == tid, t.c.reticle_id == rid))
            .mappings()
        ]
        for r, o in zip(rows, ser(s, tid, ent, rows), strict=True):
            k, ty = key, typ
            if ent == "reticle_mount_log" and r.get("event_type") == "unmount":
                k, ty = "unmounted_at", "unmount"
            items.append((r[k], r["created_at"] or r[k], {"type": ty, "at": o[k], **o}))
    items.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return {"data": [x[2] for x in items[offset : offset + limit]], "count": len(items)}
