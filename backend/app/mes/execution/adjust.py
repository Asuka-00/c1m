"""在制报废 / 补数（任意时点的数量调整，需原因代码）。"""

import uuid
from typing import Any

from sqlmodel import Session

from app.core.spec.audit import audit
from app.core.spec.base import now
from app.core.spec.engine import ENTITIES
from app.core.spec.errors import http_422
from app.mes.common.query import one
from app.mes.common.rows import _upd
from app.mes.execution.checks import service as ck
from app.mes.execution.context import build_ctx
from app.mes.execution.stage_common import _brief, _ov, _result
from app.mes.lot.service import check_transition, history, lock_lot, units

Row = dict[str, Any]
LOT = ENTITIES["lot"]
#: 单次调整数量上限的默认比例（%），可由 qty_adjust_limit 规则参数 max_pct 覆盖
DEFAULT_MAX_PCT = 10.0


def limit_result(ctx: ck.Ctx, n: int) -> Row | None:
    """「报废 / 补数数量上限」内置检查（开关关闭时为 None）。超限为可放行的阻断。"""
    rule = ck.control_rule(ctx, "qty_adjust_limit")
    if rule and rule["severity"] == "off":
        return None
    pct = float(((rule or {}).get("params") or {}).get("max_pct") or DEFAULT_MAX_PCT)
    base = max(int(ctx.lot["qty"] or 0), 1)
    mx = base * pct / 100
    data = {"qty": n, "max_pct": pct, "max_qty": round(mx, 2)}
    if n > mx:
        return ck.result(
            "qty_adjust_limit",
            "fail",
            f"adjust qty {n} exceeds {pct:g}% of lot qty {base}",
            severity=(rule or {}).get("severity") or "block",
            rule=rule,
            data=data,
        )
    return ck.result("qty_adjust_limit", "pass", f"within {pct:g}%", data=data)


def adjust(s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any) -> Row:
    """在制报废 / 补数。

    - 报废：晶圆 / 单元级按 ``unit_ids``，数量级按 ``qty``；批次数量减少，全部报废则批次终止。
    - 补数：仅数量级批次，按 ``qty`` 增加数量（记入 bonus_qty）。
    原因代码类型须与动作一致（scrap / bonus），执行触发时机 ``adjust`` 的卡控与数量上限检查。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        lot_id: 批次 id。
        body: ``{kind, qty, unit_ids, reason_id, comment, override, override_reason}``。
        user: 操作人。

    Returns:
        执行结果（批次、检查结果）。

    Raises:
        HTTPException: 参数不合法（422），卡控阻断（409）。
    """
    lot = lock_lot(s, tid, lot_id)
    kind = str(body.get("kind") or "")
    check_transition(lot, "adjust")
    level = lot["tracking_level"] or "wafer"
    errs: list[tuple[str, str]] = []
    reason = one(s, tid, "reason_code", body.get("reason_id"))
    if kind not in ("scrap", "bonus"):
        errs.append(("kind", "kind: must be scrap or bonus"))
    elif not reason or reason["reason_type"] != kind:
        errs.append(("reason_id", f"reason_id: a {kind} reason code is required"))
    elif reason.get("comment_required") and not (body.get("comment") or "").strip():
        errs.append(("comment", "comment: required by this reason code"))
    picked: list[Row] = []
    n = 0
    if kind == "bonus" and level != "quantity":
        errs.append(("kind", "kind: bonus is only for quantity-tracked lots"))
    elif kind == "scrap" and level != "quantity":
        active = {str(u["id"]): u for u in units(s, tid, lot["id"])}
        ids = [str(x) for x in body.get("unit_ids") or []]
        picked = [active[i] for i in dict.fromkeys(ids) if i in active]
        if not ids or len(picked) != len(set(ids)):
            errs.append(("unit_ids", "unit_ids: select active units of this lot"))
        n = len(picked)
    else:
        n = int(body.get("qty") or 0)
        if n < 1:
            errs.append(("qty", "qty: must be >= 1"))
        elif kind == "scrap" and n > lot["qty"]:
            errs.append(("qty", f"qty: exceeds lot qty {lot['qty']}"))
    if errs:
        raise http_422(errs)
    if kind == "scrap" and n >= lot["qty"]:  # 报废到 0：加工中批次不能被报废
        check_transition(lot, "scrap")
    assert reason
    ctx = build_ctx(s, tid, lot, "adjust", body)
    lim = limit_result(ctx, n)
    results = ck.evaluate(
        ctx,
        user,
        extra=[lim] if lim else None,
        override=body.get("override", False),
        reason=body.get("override_reason"),
    )
    at = now()
    before = lot["qty"]
    if kind == "scrap":
        for u in picked:
            _upd(
                s,
                tid,
                "wafer",
                u["id"],
                user,
                wafer_status="scrapped",
                scrap_reason_id=reason["id"],
            )
        qty = before - n
        vals: Row = {
            "qty": qty,
            "scrapped_qty": (lot["scrapped_qty"] or 0) + n,
            "stage_at": at,
        }
        if qty == 0:
            vals["lot_status"] = "scrapped"
    else:
        qty = before + n
        vals = {
            "qty": qty,
            "bonus_qty": (lot.get("bonus_qty") or 0) + n,
            "stage_at": at,
        }
    _upd(s, tid, "lot", lot["id"], user, **vals)
    old_status = lot["lot_status"]
    lot.update(vals)
    history(
        s,
        tid,
        lot,
        kind,
        user,
        qty=n,
        from_status=old_status,
        reason_id=reason["id"],
        comment=(body.get("comment") or None),
        details={
            "source": "in_process",
            "qty_before": before,
            "qty_after": qty,
            "units": [u["code"] for u in picked],
            "checks": _brief(results),
            **_ov(body, results),
        },
    )
    audit(s, tid, LOT, kind, lot, user, {"qty": (before, qty)})
    s.commit()
    return _result(s, tid, lot_id, results)
