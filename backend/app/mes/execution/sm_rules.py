"""拆合批规则与共享工具：批次类型规则、载具、子批编码、谱系、优先级。"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES
from app.core.spec.errors import http_422
from app.core.spec.serialize import serialize
from app.mes.common import coderule
from app.mes.common.query import find, one
from app.mes.common.rows import _ins
from app.mes.execution.checks import service as ck
from app.mes.execution.context import build_ctx
from app.mes.execution.stages import LOT

Row = dict[str, Any]
SPLIT_STATES = ("waiting", "moved_in")
COPY = (
    "work_order_id",
    "product_id",
    "route_id",
    "lot_type_id",
    "priority_id",
    "tracking_level",
    "site_id",
    "current_step_id",
    "lot_status",
    "equipment_id",
    "recipe_id",
    "step_in_at",
    "stage_at",
    "pending_rework",
    "route_stack",
    "exec_ctx",
    "source_ref",
    "started_at",
    "started_by",
    "attrs",
)


def rule_for(s: Session, tid: uuid.UUID, lot: Row) -> Row | None:
    """批次所属批次类型的拆合批规则，未配置时为 None。"""
    rows = [
        r
        for r in find(s, tid, "split_merge_rule", lot_type_id=lot["lot_type_id"])
        if r.get("is_active", True) is not False
    ]
    return rows[0] if rows else None


def _rule_result(errs: list[str], ok: str) -> Row:
    return ck.result(
        "split_merge_rule",
        "fail" if errs else "pass",
        "; ".join(errs) if errs else ok,
        overridable=False,
    )


def _children(s: Session, tid: uuid.UUID, lot_id: Any) -> list[Row]:
    return find(s, tid, "lot_genealogy", parent_lot_id=lot_id, relation="split")


def _carrier_cap(s: Session, tid: uuid.UUID, carrier_id: Any) -> tuple[Row, int | None]:
    car = one(s, tid, "carrier", carrier_id)
    if not car:
        raise http_422([("carrier_id", "carrier_id: not found")])
    ct = one(s, tid, "carrier_type", car["carrier_type_id"])
    cap = ct.get("capacity") if ct else None
    return car, int(cap) if cap else None


def _carrier_busy(s: Session, tid: uuid.UUID, carrier_id: Any, but: Any = None) -> bool:
    t = TABLES["lot"]
    q = sa.select(t.c.id).where(
        t.c.tenant_id == tid,
        t.c.carrier_id == carrier_id,
        t.c.lot_status.notin_(["completed", "stored", "scrapped", "merged"]),
    )
    if but is not None:
        q = q.where(t.c.id != but)
    return conn(s).execute(q).first() is not None


def _child_codes(s: Session, tid: uuid.UUID, lot: Row, rule: Row, n: int) -> list[str]:
    if rule.get("child_id_mode") == "code_rule":
        lt = one(s, tid, "lot_type", lot["lot_type_id"])
        cr = lt and one(s, tid, "code_rule", lt["lot_id_rule_id"])
        if not cr:
            raise http_422([("lot_type", "lot_type: no lot ID rule")])
        return coderule.generate(s, tid, cr, n, commit=False)
    t = TABLES["lot"]
    taken = {
        c
        for (c,) in conn(s).execute(
            sa.select(t.c.code).where(
                t.c.tenant_id == tid, t.c.code.like(f"{lot['code']}.%")
            )
        )
    }
    out: list[str] = []
    k = 1
    while len(out) < n:
        c = f"{lot['code']}.{k:02d}"
        if c not in taken:
            out.append(c)
        k += 1
    return out


def _genealogy(
    s: Session,
    tid: uuid.UUID,
    parent: Row,
    child: Row,
    relation: str,
    qty: int,
    unit_codes: list[str],
    user: Any,
    at: Any,
) -> None:
    _ins(
        s,
        tid,
        "lot_genealogy",
        user,
        parent_lot_id=parent["id"],
        child_lot_id=child["id"],
        relation=relation,
        qty=qty,
        units=unit_codes,
        route_step_id=parent["current_step_id"],
        user_email=getattr(user, "email", None),
        at=at,
    )


def _evaluate(
    s: Session,
    tid: uuid.UUID,
    lot: Row,
    trigger: str,
    extra: list[Row],
    body: Row,
    user: Any,
) -> list[Row]:
    ctx = build_ctx(s, tid, lot, trigger, {})
    return ck.evaluate(
        ctx,
        user,
        extra=extra,
        override=bool(body.get("override")),
        reason=body.get("override_reason"),
        preview=bool(body.get("preview")),
    )


def _ser(s: Session, tid: uuid.UUID, lot_id: Any) -> Row | None:
    lot = one(s, tid, "lot", lot_id)
    return serialize(s, tid, LOT, [lot])[0] if lot else None


def _prio(s: Session, tid: uuid.UUID, pid: Any) -> Row | None:
    return one(s, tid, "lot_priority", pid)


def _prio_json(p: Row | None) -> Row | None:
    return p and {
        "id": str(p["id"]),
        "code": p["code"],
        "name": p["name"],
        "level": p["level"],
        "color": p.get("color"),
    }


def highest_priority(s: Session, tid: uuid.UUID, lots: list[Row]) -> Row | None:
    """多个批次中最高的优先级（level 越小越高；相同时保留第一个，即目标批次）。"""
    ps = [p for p in (_prio(s, tid, x["priority_id"]) for x in lots) if p]
    return min(ps, key=lambda p: p["level"]) if ps else None
