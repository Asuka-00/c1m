"""芯片级芯片图：按晶圆导入 CP / AOI 结果（每颗芯片 ``[x, y, bin]``）与查看。"""

import uuid
from collections import Counter
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.models import actor_name
from app.core.spec.base import conn, now
from app.core.spec.engine import TABLES
from app.core.spec.errors import FieldError, coded, fe, http_422
from app.mes.common.query import find, jsonable, one
from app.mes.common.rows import _ins
from app.mes.lot.service import history, lock_lot, units

Row = dict[str, Any]
MAX_DIES = 200_000
#: 转换取良品时使用的芯片图类型（ink 为合并 / 打点后的图，优先）
PICK_KINDS = ("ink", "cp")


def _parse(
    i: int, dies: Any, bins: dict[str, Row], unknown: set[str]
) -> tuple[list[list[Any]], list[FieldError]]:
    """校验并规范化一张图的芯片列表，未知 Bin 收集到 ``unknown``。"""
    if not isinstance(dies, list) or not dies:
        return [], [fe(f"maps.{i}.dies", ec.DIE_MAP_DIES, "dies required", i=i)]
    if len(dies) > MAX_DIES:
        return [], [
            fe(f"maps.{i}.dies", ec.DIE_MAP_TOO_LARGE, "too many", i=i, max=MAX_DIES)
        ]
    out: list[list[Any]] = []
    seen: set[tuple[int, int]] = set()
    for d in dies:
        if (
            not isinstance(d, list | tuple)
            or len(d) != 3
            or not all(isinstance(v, int) and not isinstance(v, bool) for v in d[:2])
        ):
            return [], [fe(f"maps.{i}.dies", ec.DIE_MAP_DIES, "[x, y, bin]", i=i)]
        x, y, b = int(d[0]), int(d[1]), str(d[2]).strip()
        if (x, y) in seen:
            return [], [
                fe(
                    f"maps.{i}.dies",
                    ec.DIE_MAP_DUPLICATE,
                    f"die ({x}, {y}) twice",
                    i=i,
                    x=x,
                    y=y,
                )
            ]
        seen.add((x, y))
        if b not in bins:
            unknown.add(b)
        out.append([x, y, b])
    return out, []


def import_maps(
    s: Session, tid: uuid.UUID, lot_id: uuid.UUID, body: Row, user: Any
) -> Row:
    """导入批次内晶圆的芯片级芯片图。

    同一晶圆同一类型的旧图标记为非当前（重测覆盖）；Bin 码须为已启用的 Bin 代码。

    Args:
        s: 数据库会话。
        tid: 租户 id。
        lot_id: 批次 id。
        body: ``{test_kind, route_step_id?, source?, maps: [{unit_id | unit_code, dies}]}``。
        user: 操作人。

    Returns:
        ``{maps: [{id, unit, gross, good, yield_pct}]}``。

    Raises:
        HTTPException: 晶圆不在批次、芯片格式错误或 Bin 未知（422）。
    """
    lot = lock_lot(s, tid, lot_id)
    us = units(s, tid, lot["id"])
    by_id = {str(u["id"]): u for u in us}
    by_code = {u["code"]: u for u in us}
    bins = {b["code"]: b for b in find(s, tid, "bin_code") if b["is_active"]}
    errs: list[FieldError] = []
    unknown: set[str] = set()
    parsed: list[tuple[Row, list[list[Any]]]] = []
    for i, m in enumerate(body.get("maps") or [], 1):
        u = by_id.get(str(m.get("unit_id"))) or by_code.get(m.get("unit_code") or "")
        if not u:
            errs.append(fe(f"maps.{i}.unit", ec.DIE_MAP_UNIT, "unit not in lot", i=i))
            continue
        dies, e = _parse(i, m.get("dies"), bins, unknown)
        errs += e
        parsed.append((u, dies))
    if unknown:
        errs.append(
            fe(
                "maps",
                ec.DIE_MAP_BINS,
                "unknown bins",
                bins=", ".join(sorted(unknown)[:20]),
            )
        )
    if not parsed and not errs:
        errs.append(fe("maps", ec.DIE_MAP_DIES, "maps required", i=1))
    if errs:
        raise http_422(errs)
    kind = body.get("test_kind") or "cp"
    step_id = body.get("route_step_id") or lot["current_step_id"]
    good_bins = {c for c, b in bins.items() if b["is_good"]}
    t, at, out = TABLES["die_map"], now(), []
    for u, dies in parsed:
        conn(s).execute(
            sa.update(t)
            .where(
                t.c.tenant_id == tid,
                t.c.unit_id == u["id"],
                t.c.test_kind == kind,
                t.c.is_current.is_(True),
            )
            .values(is_current=False, updated_at=at)
        )
        xs, ys = [d[0] for d in dies], [d[1] for d in dies]
        good = sum(1 for d in dies if d[2] in good_bins)
        y = round(good * 100 / len(dies), 2)
        mid = _ins(
            s,
            tid,
            "die_map",
            user,
            unit_id=u["id"],
            lot_id=lot["id"],
            route_step_id=step_id,
            test_kind=kind,
            rows=max(ys) - min(ys) + 1,
            cols=max(xs) - min(xs) + 1,
            dies=dies,
            gross=len(dies),
            good=good,
            yield_pct=y,
            is_current=True,
            source=(body.get("source") or "")[:200] or None,
            username=actor_name(user),
            at=at,
        )
        out.append(
            {
                "id": str(mid),
                "unit": u["code"],
                "gross": len(dies),
                "good": good,
                "yield_pct": y,
            }
        )
    history(
        s,
        tid,
        lot,
        "die_map",
        user,
        details={"test_kind": kind, "source": body.get("source"), "maps": out},
    )
    s.commit()
    return {"maps": out}


def current_maps(
    s: Session, tid: uuid.UUID, unit_ids: list[Any], *, with_dies: bool = True
) -> dict[Any, Row]:
    """单元当前用于取片的芯片图（ink 优先于 cp，同类取最新）。"""
    if not unit_ids:
        return {}
    t = TABLES["die_map"]
    cols = list(t.c) if with_dies else [c for c in t.c if c.name != "dies"]
    rows = (
        conn(s)
        .execute(
            sa.select(*cols).where(
                t.c.tenant_id == tid,
                t.c.unit_id.in_(unit_ids),
                t.c.is_current.is_(True),
                t.c.test_kind.in_(PICK_KINDS),
            )
        )
        .mappings()
        .all()
    )
    out: dict[Any, Row] = {}
    # 低优先级在前、同类按时间正序，后写入的覆盖前者
    for r in sorted(rows, key=lambda r: (-PICK_KINDS.index(r["test_kind"]), r["at"])):
        out[r["unit_id"]] = dict(r)
    return out


def good_bins(s: Session, tid: uuid.UUID) -> set[str]:
    """良品 Bin 代码。"""
    return {b["code"] for b in find(s, tid, "bin_code") if b["is_good"]}


def _legend(s: Session, tid: uuid.UUID, dies: list[list[Any]]) -> list[Row]:
    counts = Counter(str(d[2]) for d in dies)
    bins = {b["code"]: b for b in find(s, tid, "bin_code")}
    return [
        {
            "bin": c,
            "name": (bins.get(c) or {}).get("name"),
            "color": (bins.get(c) or {}).get("color"),
            "is_good": bool((bins.get(c) or {}).get("is_good")),
            "count": n,
        }
        for c, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def get_map(s: Session, tid: uuid.UUID, map_id: uuid.UUID) -> Row:
    """芯片图详情：芯片列表与按 Bin 汇总的图例。

    Raises:
        HTTPException: 不存在（404）。
    """
    m = one(s, tid, "die_map", map_id)
    if not m:
        raise coded(404, ec.RECORD_NOT_FOUND, "Record not found")
    u = one(s, tid, "wafer", m["unit_id"])
    lot = one(s, tid, "lot", m["lot_id"])
    return jsonable(  # type: ignore[no-any-return]
        {
            **{k: m[k] for k in ("id", "test_kind", "rows", "cols", "gross", "good")},
            "yield_pct": m["yield_pct"],
            "is_current": m["is_current"],
            "source": m["source"],
            "at": m["at"],
            "unit": u and u["code"],
            "unit_id": m["unit_id"],
            "lot": lot and lot["code"],
            "dies": m["dies"] or [],
            "legend": _legend(s, tid, m["dies"] or []),
        }
    )


def unit_maps(s: Session, tid: uuid.UUID, unit_id: uuid.UUID) -> list[Row]:
    """某晶圆的全部芯片图（不含芯片明细），最新在前。"""
    t = TABLES["die_map"]
    cols = [c for c in t.c if c.name != "dies"]
    rows = (
        conn(s)
        .execute(
            sa.select(*cols)
            .where(t.c.tenant_id == tid, t.c.unit_id == unit_id)
            .order_by(t.c.at.desc())
        )
        .mappings()
        .all()
    )
    return jsonable(  # type: ignore[no-any-return]
        [
            {
                k: r[k]
                for k in (
                    "id",
                    "test_kind",
                    "gross",
                    "good",
                    "yield_pct",
                    "is_current",
                    "source",
                    "at",
                )
            }
            for r in rows
        ]
    )
