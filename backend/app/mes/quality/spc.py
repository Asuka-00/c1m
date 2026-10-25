"""SPC 判异：控制限、Western Electric / Nelson 规则 1–8、子组序列与控制图数据。

子组 = 一个批次在一个工步上某量测项的全部测量值（取均值，即 X-bar 图）。
"""

import uuid
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core.spec.base import conn
from app.core.spec.engine import TABLES
from app.mes.common.query import jsonable, one

Row = dict[str, Any]
RULES = range(1, 9)
#: 判定需要的历史子组数（规则 7 需要连续 15 点）
WINDOW = 15
CHART_POINTS = 50


def parse_rules(text: str | None) -> list[int]:
    """解析规则编号文本（如 ``"1,2,5"``），忽略非法项。"""
    out = {int(x) for x in (text or "").replace(" ", "").split(",") if x.isdigit()}
    return sorted(out & set(RULES))


def limits(it: Row) -> Row | None:
    """计划项的控制限 ``{cl, ucl, lcl, su, sl}``；未配置任何控制限时为 None。

    中心线为空时取 UCL / LCL 中点；σ 按 (UCL − CL) / 3 与 (CL − LCL) / 3 分别计算，
    只配置了单侧控制限时另一侧按对称处理。
    """
    ucl, lcl, cl = it.get("ucl"), it.get("lcl"), it.get("cl")
    if ucl is None and lcl is None:
        return None
    if cl is None and ucl is not None and lcl is not None:
        cl = (ucl + lcl) / 2
    su = (ucl - cl) / 3 if cl is not None and ucl is not None else None
    sl = (cl - lcl) / 3 if cl is not None and lcl is not None else None
    su, sl = su or sl, sl or su
    return {"cl": cl, "ucl": ucl, "lcl": lcl, "su": su, "sl": sl}


def _z(x: float, lim: Row) -> float:
    """到中心线的带符号 σ 距离。"""
    s = lim["su"] if x >= lim["cl"] else lim["sl"]
    return (x - lim["cl"]) / s if s else 0.0


def violations(xs: list[float], lim: Row, rules: list[int]) -> list[int]:
    """序列最后一点触发的规则编号。

    Args:
        xs: 子组均值序列（时间正序，最后一点为待判定点）。
        lim: :func:`limits` 的结果。
        rules: 启用的规则编号。

    Returns:
        触发的规则编号（升序）。
    """
    if not xs:
        return []
    x = xs[-1]
    out: list[int] = []
    if 1 in rules and (
        (lim["ucl"] is not None and x > lim["ucl"])
        or (lim["lcl"] is not None and x < lim["lcl"])
    ):
        out.append(1)
    if lim["cl"] is None or not lim["su"]:
        return out  # 其余规则需要中心线与 σ
    z = [_z(v, lim) for v in xs]

    def last(n: int) -> list[float] | None:
        return z[-n:] if len(z) >= n else None

    def side(vs: list[float], k: float, need: int) -> bool:
        """最后一点所在一侧，超过 k σ 的点数 ≥ need（含最后一点）。"""
        sign = 1 if vs[-1] > 0 else -1
        return sign * vs[-1] > k and sum(1 for v in vs if sign * v > k) >= need

    if (
        2 in rules
        and (w := last(9))
        and (all(v > 0 for v in w) or all(v < 0 for v in w))
    ):
        out.append(2)
    if 3 in rules and (w := last(6)):
        d = [b - a for a, b in zip(w, w[1:], strict=False)]
        if all(v > 0 for v in d) or all(v < 0 for v in d):
            out.append(3)
    if 4 in rules and (w := last(14)):
        d = [b - a for a, b in zip(w, w[1:], strict=False)]
        if all(d[i] * d[i + 1] < 0 for i in range(len(d) - 1)):
            out.append(4)
    if 5 in rules and (w := last(3)) and side(w, 2, 2):
        out.append(5)
    if 6 in rules and (w := last(5)) and side(w, 1, 4):
        out.append(6)
    if 7 in rules and (w := last(15)) and all(abs(v) < 1 for v in w):
        out.append(7)
    if 8 in rules and (w := last(8)) and all(abs(v) > 1 for v in w):
        if any(v > 0 for v in w) and any(v < 0 for v in w):
            out.append(8)
    return sorted(out)


def subgroups(
    s: Session,
    tid: uuid.UUID,
    measurement_item_id: Any,
    dc_plan_id: Any,
    limit: int = WINDOW,
) -> list[Row]:
    """最近的子组（时间正序）：``[{lot_id, route_step_id, mean, n, at}]``。"""
    d = TABLES["dc_result"]
    at = sa.func.max(d.c.created_at).label("at")
    rows = (
        conn(s)
        .execute(
            sa.select(
                d.c.lot_id,
                d.c.route_step_id,
                sa.func.avg(d.c.value).label("mean"),
                sa.func.count().label("n"),
                at,
            )
            .where(
                d.c.tenant_id == tid,
                d.c.measurement_item_id == measurement_item_id,
                d.c.dc_plan_id == dc_plan_id,
                d.c.value.is_not(None),
            )
            .group_by(d.c.lot_id, d.c.route_step_id)
            .order_by(at.desc())
            .limit(limit)
        )
        .mappings()
        .all()
    )
    return [dict(r) | {"mean": float(r["mean"])} for r in reversed(rows)]


def ooc_check(
    s: Session, tid: uuid.UUID, it: Row, dc_plan_id: Any, mean: float
) -> list[int]:
    """待写入子组（均值 ``mean``）连同历史子组判异，返回触发的规则编号。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        it: 抽样结果中的计划项（含 measurement_item_id、控制限与 ooc_rules）。
        dc_plan_id: DC 计划 id。
        mean: 本次子组均值。
    """
    rules = parse_rules(it.get("ooc_rules"))
    lim = limits(it)
    if not rules or not lim:
        return []
    hist = subgroups(s, tid, it["measurement_item_id"], dc_plan_id, WINDOW - 1)
    return violations([h["mean"] for h in hist] + [mean], lim, rules)


def spc_chart(s: Session, tid: uuid.UUID, dc_plan_item_id: Any) -> Row | None:
    """控制图数据：计划项的规格 / 控制限与最近子组（每点按当前控制限重新判异）。

    Returns:
        ``{item, plan, limits, rules, points: [{lot, step_seq, mean, n, at, rules}]}``；
        计划项不存在时为 None。
    """
    pi = one(s, tid, "dc_plan_item", dc_plan_item_id)
    if not pi:
        return None
    mi = one(s, tid, "measurement_item", pi["measurement_item_id"])
    plan = one(s, tid, "dc_plan", pi["dc_plan_id"])
    rules = parse_rules(pi["ooc_rules"])
    lim = limits(pi)
    hist = subgroups(s, tid, pi["measurement_item_id"], pi["dc_plan_id"], CHART_POINTS)
    xs = [h["mean"] for h in hist]
    points = []
    for i, h in enumerate(hist):
        lot = one(s, tid, "lot", h["lot_id"])
        st = one(s, tid, "route_step", h["route_step_id"])
        points.append(
            {
                "lot": lot and lot["code"],
                "lot_id": h["lot_id"],
                "step_seq": st and st["seq"],
                "mean": h["mean"],
                "n": h["n"],
                "at": h["at"],
                "rules": violations(xs[: i + 1], lim, rules) if lim else [],
            }
        )
    return jsonable(  # type: ignore[no-any-return]
        {
            "item": mi and {"id": mi["id"], "code": mi["code"], "name": mi["name"]},
            "plan": plan and {"id": plan["id"], "code": plan["code"]},
            "limits": {
                "usl": pi["usl"],
                "lsl": pi["lsl"],
                "target": pi["target"],
                "ucl": lim and lim["ucl"],
                "cl": lim and lim["cl"],
                "lcl": lim and lim["lcl"],
            },
            "rules": rules,
            "points": points,
        }
    )
