"""单元转换：整批单元转成下一级单元（晶圆 → 芯片 / 条带 / 单颗），记录单元级谱系。

- 1 → N：每个来源单元产出 ``per_parent`` 个（如条带切单颗）；
- N → 1：每 ``per_child`` 个来源合成 1 个（如芯片固晶到条带，最后一个可不满）；
- 按晶圆图：来源为各晶圆当前晶圆图上的良品芯片（坐标写入谱系），坏品不产出。
来源单元标记为已转换（消耗），批次数量变为产出数，追踪级别变为序列化单元。
"""

import math
import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.models import actor_name
from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import TABLES
from app.core.spec.errors import FieldError, fe, http_422
from app.mes.common import coderule
from app.mes.common.query import one
from app.mes.common.rows import _sys, _upd
from app.mes.execution.carrier.ops import event
from app.mes.execution.split_merge.rules import _evaluate, _ser
from app.mes.execution.stage.common import _brief, _ov
from app.mes.execution.stage.stages import LOT
from app.mes.execution.units.die_map import current_maps, good_bins
from app.mes.lot.service import check_transition, history, lock_lot, units

Row = dict[str, Any]
KINDS = ("die", "strip", "package", "unit")
MAX_OUT = 50_000
_CHUNK = 5_000


def _codes(s: Session, tid: uuid.UUID, lot: Row, kind: str, n: int) -> list[str]:
    """产出单元编号：产品的序列号规则，未配置时为 ``<批次号>-<类型首字母><序号>``。"""
    prod = one(s, tid, "product", lot["product_id"])
    rule = prod and one(s, tid, "code_rule", prod["unit_code_rule_id"])
    if not rule:
        w = max(4, len(str(n)))
        return [f"{lot['code']}-{kind[0].upper()}{i:0{w}d}" for i in range(1, n + 1)]
    if "{SEQ" in rule["pattern"]:
        return coderule.generate(s, tid, rule, n, {"LOT": lot["code"]}, commit=False)
    at = now()
    return [
        coderule.render(rule, i, at, {"LOT": lot["code"], "SLOT": i})
        for i in range(1, n + 1)
    ]


def _taken(s: Session, tid: uuid.UUID, codes: list[str]) -> list[str]:
    t = TABLES["wafer"]
    out: list[str] = []
    for i in range(0, len(codes), _CHUNK):
        out += (
            conn(s)
            .execute(
                sa.select(t.c.code).where(
                    t.c.tenant_id == tid, t.c.code.in_(codes[i : i + _CHUNK])
                )
            )
            .scalars()
        )
    return out


def _sources(
    s: Session, tid: uuid.UUID, parents: list[Row], body: Row, errs: list[FieldError]
) -> tuple[list[tuple[Row, list[int] | None]], int]:
    """来源项 ``[(来源单元, 芯片坐标 | None)]`` 与坏品芯片数。"""
    if not body.get("use_map"):
        n = int(body.get("per_parent") or 1)
        return [(p, None) for p in parents for _ in range(n)], 0
    maps = current_maps(s, tid, [p["id"] for p in parents])
    good = good_bins(s, tid)
    items: list[tuple[Row, list[int] | None]] = []
    bad = 0
    for p in parents:
        m = maps.get(p["id"])
        if not m:
            errs.append(fe("use_map", ec.CONVERT_NO_MAP, "no die map", unit=p["code"]))
            continue
        for x, y, b in sorted(m["dies"] or [], key=lambda d: (d[1], d[0])):
            if str(b) in good:
                items.append((p, [x, y]))
            else:
                bad += 1
    if not errs and not items:
        errs.append(fe("use_map", ec.CONVERT_NO_GOOD_DIE, "no good die"))
    return items, bad


def convert(s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any) -> Row:
    """单元转换（整批）。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        lot_id: 批次 id。
        body: ``{to_kind, per_parent?, per_child?, use_map?, comment, override,
            override_reason, preview}``。
        user: 操作人。

    Returns:
        ``{results, count, bad_dies, codes, lot}``（预览时只有 results / count / bad_dies）。

    Raises:
        HTTPException: 状态不允许或参数不合法（422），产出编号冲突（422）。
        CheckBlocked: 卡控阻断。
    """
    lot = lock_lot(s, tid, lot_id)
    check_transition(lot, "convert")
    kind = str(body.get("to_kind") or "")
    per_parent = int(body.get("per_parent") or 1)
    per_child = int(body.get("per_child") or 1)
    errs: list[FieldError] = []
    if kind not in KINDS:
        errs.append(fe("to_kind", ec.CONVERT_KIND, "invalid unit kind"))
    if (lot["tracking_level"] or "wafer") == "quantity":
        errs.append(fe("to_kind", ec.CONVERT_QUANTITY_LOT, "quantity-tracked lot"))
    if (
        per_parent < 1
        or per_child < 1
        or (per_parent > 1 and per_child > 1)
        or (body.get("use_map") and per_parent > 1)
    ):
        errs.append(fe("per_child", ec.CONVERT_RATIO, "invalid ratio"))
    parents = units(s, tid, lot["id"])
    if not parents:
        errs.append(fe("to_kind", ec.CONVERT_NO_UNITS, "no active units"))
    if errs:
        raise http_422(errs)
    items, bad = _sources(s, tid, parents, body, errs)
    n_out = math.ceil(len(items) / per_child)
    if n_out > MAX_OUT:
        errs.append(
            fe("per_child", ec.CONVERT_TOO_MANY, "too many", count=n_out, max=MAX_OUT)
        )
    if errs:
        raise http_422(errs)
    results = _evaluate(s, tid, lot, "convert", [], body, user)
    if body.get("preview"):
        s.commit()
        return {"results": results, "count": n_out, "bad_dies": bad}
    codes = _codes(s, tid, lot, kind, n_out)
    if dup := _taken(s, tid, codes):
        raise http_422(
            [
                fe(
                    "to_kind",
                    ec.CONVERT_CODES_EXIST,
                    "unit IDs exist",
                    codes=", ".join(dup[:5]),
                )
            ]
        )
    at, who = now(), actor_name(user)
    relation = "assemble" if per_child > 1 else "convert"
    step_id = lot["current_step_id"]
    new_units: list[Row] = []
    links: list[Row] = []
    for k, code in enumerate(codes):
        chunk = items[k * per_child : (k + 1) * per_child]
        uid = uuid.uuid4()
        by: dict[Any, tuple[Row, list[list[int]]]] = {}
        for p, xy in chunk:
            by.setdefault(p["id"], (p, []))[1].append(xy or [])
        die = chunk[0][1] if per_child == 1 else None
        new_units.append(
            {
                "id": uid,
                "code": code,
                "lot_id": lot["id"],
                "unit_kind": kind,
                "slot": None,
                "wafer_status": "waiting",
                "source_ref": ",".join(p["code"] for p, _ in by.values())[:100],
                "rework_count": 0,
                "attrs": {"x": die[0], "y": die[1]} if die else {},
            }
        )
        for p, xys in by.values():
            links.append(
                {
                    "id": uuid.uuid4(),
                    "parent_unit_id": p["id"],
                    "child_unit_id": uid,
                    "lot_id": lot["id"],
                    "relation": relation,
                    "qty": len(xys),
                    "dies": [xy for xy in xys if xy] or None,
                    "route_step_id": step_id,
                    "username": who,
                    "at": at,
                }
            )
    sysv = {"tenant_id": tid, **_sys(user, at)}
    for table, rows in (("wafer", new_units), ("unit_genealogy", links)):
        for i in range(0, len(rows), _CHUNK):
            conn(s).execute(
                sa.insert(TABLES[table]), [r | sysv for r in rows[i : i + _CHUNK]]
            )
    w = TABLES["wafer"]
    conn(s).execute(
        sa.update(w)
        .where(w.c.tenant_id == tid, w.c.id.in_([p["id"] for p in parents]))
        .values(wafer_status="converted", updated_at=at)
    )
    before = lot["qty"]
    car = one(s, tid, "carrier", lot["carrier_id"]) if lot["carrier_id"] else None
    if car:  # 来源单元已消耗，载具随之释放
        event(s, tid, car, "unload", user, lot=lot, qty=len(parents))
    _upd(
        s,
        tid,
        "lot",
        lot["id"],
        user,
        qty=n_out,
        tracking_level="unit",
        carrier_id=None,
        stage_at=at,
    )
    lot.update(qty=n_out, tracking_level="unit", carrier_id=None)
    summary = {
        "from_kind": parents[0]["unit_kind"],
        "to_kind": kind,
        "relation": relation,
        "sources": len(parents),
        "outputs": n_out,
        "per_parent": per_parent,
        "per_child": per_child,
        "use_map": bool(body.get("use_map")),
        "bad_dies": bad,
    }
    history(
        s,
        tid,
        lot,
        "convert",
        user,
        comment=body.get("comment"),
        details={**summary, "checks": _brief(results), **_ov(body, results)},
    )
    audit(
        s,
        tid,
        LOT,
        "convert",
        lot,
        user,
        {"qty": (before, n_out), "unit_kind": (summary["from_kind"], kind)},
    )
    s.commit()
    return {
        "results": results,
        "count": n_out,
        "bad_dies": bad,
        "codes": codes[:20],
        "lot": _ser(s, tid, lot_id),
    }
