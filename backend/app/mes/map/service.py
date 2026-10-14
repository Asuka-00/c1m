"""坐标图模块公开 API（B4）：导入（preview / commit）、按基板查询、数量守恒校验。"""

import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.core.models import actor_name
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, TABLES
from app.core.spec.errors import http_422
from app.core.spec.serialize import serialize
from app.mes.common.query import find, one
from app.mes.common.rows import _ins
from app.mes.map import importer
from app.mes.map.specs import EXCLUDED_BIN_TYPES, GOOD_BIN_TYPES

Row = dict[str, Any]


def _invalid(code: str, message: str, errors: list[Row]) -> HTTPException:
    return HTTPException(
        status_code=422, detail={"code": code, "message": message, "errors": errors}
    )


def _by_code(s: Session, tid: uuid.UUID, ent: str, code: str, **eq: Any) -> list[Row]:
    t = TABLES[ent]
    q = sa.select(t).where(t.c.tenant_id == tid, t.c.code == code)
    for k, v in eq.items():
        q = q.where(t.c[k] == v)
    return [dict(r) for r in conn(s).execute(q).mappings().all()]


def _bin_set(s: Session, tid: uuid.UUID, code: str, version: Any) -> Row | None:
    if not code or not str(version).isdigit():
        return None
    rows = _by_code(s, tid, "bin_set", code, version=int(version))
    return rows[0] if rows else None


def bin_types(s: Session, tid: uuid.UUID, bin_set_id: Any) -> dict[str, str]:
    """定义集的 ``{bin_code: bin_type}``。"""
    return {
        d["bin_code"]: d["bin_type"]
        for d in find(s, tid, "bin_definition", bin_set_id=bin_set_id)
    }


def _record(
    s: Session, tid: uuid.UUID, kind: str, body: Row, n: int, user: Any
) -> uuid.UUID:
    # 手工导入：source 固定 manual，external_event_id 为空（EAP 适配层以后写入）
    return _ins(
        s,
        tid,
        "map_import",
        user,
        import_kind=kind,
        source="manual",
        external_event_id=None,
        file_name=body.get("file_name"),
        row_count=n,
        imported_by=actor_name(user),
        imported_at=now(),
    )


# ---------------- bin 定义集 ----------------
def bin_set_preview(s: Session, tid: uuid.UUID, body: Row) -> Row:
    """校验 bin 定义 CSV（定义集与版本取自它自己的文件头），返回定义与逐行错误。"""
    head, defs, errs = importer.check_bin_set(body["content"])
    if (
        head["code"]
        and head["version"]
        and _bin_set(s, tid, head["code"], head["version"])
    ):
        errs.append(
            importer.err(
                "bin_set_exists",
                f"bin set {head['code']} v{head['version']} already exists",
                field_="version",
            )
        )
    return {
        "ok": not errs,
        "bin_set": head,
        "definitions": defs,
        "excluded_bin_codes": [
            d["bin_code"] for d in defs if d["bin_type"] in EXCLUDED_BIN_TYPES
        ],
        "errors": errs,
    }


def bin_set_import(s: Session, tid: uuid.UUID, body: Row, user: Any) -> Row:
    """导入 bin 定义集；有错误时 422 ``bin_set_invalid``（含逐行错误）。"""
    pv = bin_set_preview(s, tid, body)
    if not pv["ok"]:
        raise _invalid(
            "bin_set_invalid", "bin definition file has errors", pv["errors"]
        )
    imp = _record(s, tid, "bin_set", body, len(pv["definitions"]), user)
    sid = _ins(
        s,
        tid,
        "bin_set",
        user,
        code=pv["bin_set"]["code"],
        version=pv["bin_set"]["version"],
        map_import_id=imp,
    )
    for d in pv["definitions"]:
        _ins(s, tid, "bin_definition", user, bin_set_id=sid, **d)
    s.commit()
    row = one(s, tid, "bin_set", sid)
    assert row
    out = serialize(s, tid, ENTITIES["bin_set"], [row])[0]
    out["definitions"] = serialize(
        s,
        tid,
        ENTITIES["bin_definition"],
        find(s, tid, "bin_definition", bin_set_id=sid),
    )
    return out


# ---------------- 坐标图 ----------------
def _check_refs(s: Session, tid: uuid.UUID, body: Row) -> None:
    """D39：给了 lot_id / equipment_id / operation_id 但记录不存在 → 422（loc 指向字段）。"""
    errs = [
        ((f"{ent}_id",), f"{ent} not found")
        for ent in ("lot", "equipment", "operation")
        if body.get(f"{ent}_id") and not one(s, tid, ent, body[f"{ent}_id"])
    ]
    if errs:
        raise http_422(errs)


def wafer_lot(s: Session, tid: uuid.UUID, code: str) -> Any:
    """D39：按基板编号找晶圆记录，返回其当前所在批次（不匹配批次号）。

    找不到，或多条晶圆记录分属不同批次（无法唯一确定）时返回 None。
    """
    w = TABLES["wafer"]
    lots = {
        r[0]
        for r in conn(s).execute(
            sa.select(w.c.lot_id).where(w.c.tenant_id == tid, w.c.code == code)
        )
    }
    return lots.pop() if len(lots) == 1 else None


def map_preview(s: Session, tid: uuid.UUID, body: Row) -> Row:
    """解析并校验坐标图；定义集不存在时 422 ``bin_set_not_found``。"""
    _check_refs(s, tid, body)
    p = importer.parse(body["content"], importer.MAP_COLS)
    hset = p.header.get("bin_definition_set", "")
    hver = p.header.get("bin_definition_version", "")
    bs = _bin_set(s, tid, hset, hver)
    if hset and str(hver).isdigit() and not bs:
        raise _invalid(
            "bin_set_not_found",
            f"bin definition set {hset} v{hver} not found",
            [
                importer.err(
                    "bin_set_not_found",
                    f"bin set {hset} v{hver} not found",
                    field_="bin_definition_set",
                )
            ],
        )
    head, subs, errs = importer.check_map(
        body["content"], bin_types(s, tid, bs["id"]) if bs else None
    )
    for x in subs:
        # 坐标图层守恒：坐标总数 = 各 bin 数量之和（含排除类 bin）
        if sum(x["bin_counts"].values()) != x["total_qty"]:  # pragma: no cover - 不变式
            errs.append(
                importer.err("qty_mismatch", f"{x['code']}: bin counts != total")
            )
    for x in subs:
        x["map_version"] = next_version(s, tid, x["code"])
    return {
        "ok": not errs,
        "header": head,
        "bin_set_id": bs and str(bs["id"]),
        "substrates": [{k: v for k, v in x.items() if k != "cells"} for x in subs],
        "errors": errs,
        "_subs": subs,
        "_bin_set": bs,
    }


def next_version(s: Session, tid: uuid.UUID, code: str) -> int:
    """基板的下一个坐标图版本号（当前最大版本 + 1）。"""
    t = TABLES["substrate_map"]
    cur = (
        conn(s)
        .execute(
            sa.select(sa.func.max(t.c.map_version)).where(
                t.c.tenant_id == tid, t.c.code == code
            )
        )
        .scalar()
    )
    return int(cur or 0) + 1


def _lock_substrate(s: Session, tid: uuid.UUID, code: str) -> None:
    """事务级 advisory lock：同一租户同一基板的并发导入串行取版本号。"""
    conn(s).execute(
        sa.select(
            sa.func.pg_advisory_xact_lock(
                sa.func.hashtextextended(f"mes_substrate_map:{tid}:{code}", 0)
            )
        )
    )


def _conflict(ex: IntegrityError) -> bool:
    return "uq_mes_substrate_map_0" in str(ex.orig)


def map_import(s: Session, tid: uuid.UUID, body: Row, user: Any) -> Row:
    """导入坐标图并提交（失败时 422 / 409，见 :func:`_map_import`）。

    并发：按基板加 advisory lock 后再取版本号；万一仍撞上
    ``uq_mes_substrate_map_0``，回滚并返回 409 ``map_version_conflict``（不返回 500）。
    """
    try:
        return _map_import(s, tid, body, user)
    except IntegrityError as ex:
        s.rollback()
        if not _conflict(ex):
            raise
        raise HTTPException(
            status_code=409,
            detail={
                "code": "map_version_conflict",
                "message": "another import created the same substrate map version; retry",
            },
        ) from None


def _map_import(s: Session, tid: uuid.UUID, body: Row, user: Any) -> Row:
    """导入坐标图；有错误时 422 ``map_invalid``；同一基板重复导入生成新版本。"""
    pv = map_preview(s, tid, body)
    if not pv["ok"]:
        raise _invalid("map_invalid", "map file has errors", pv["errors"])
    h, bs = pv["header"], pv["_bin_set"]
    n = sum(x["total_qty"] for x in pv["_subs"])
    imp = _record(s, tid, "map", body, n, user)
    ids = []
    ct = TABLES["map_cell"]
    at = now()
    for x in sorted(pv["_subs"], key=lambda r: r["code"]):  # 固定加锁顺序，避免死锁
        _lock_substrate(s, tid, x["code"])
        x["map_version"] = next_version(s, tid, x["code"])
    for x in pv["_subs"]:
        mid = _ins(
            s,
            tid,
            "substrate_map",
            user,
            code=x["code"],
            substrate_type=h["substrate_type"],
            map_version=x["map_version"],
            rows=x["rows"],
            cols=x["cols"],
            origin_location=h["origin_location"],
            x_axis=h["x_axis"],
            y_axis=h["y_axis"],
            bin_set_id=bs["id"],
            map_import_id=imp,
            total_qty=x["total_qty"],
            good_qty=x["good_qty"],
            excluded_qty=x["excluded_qty"],
            bin_counts=x["bin_counts"],
            lot_id=body.get("lot_id") or wafer_lot(s, tid, x["code"]),
            equipment_id=body.get("equipment_id"),
            operation_id=body.get("operation_id"),
        )
        conn(s).execute(
            sa.insert(ct),
            [
                {
                    "id": uuid.uuid4(),
                    "tenant_id": tid,
                    "substrate_map_id": mid,
                    "row": r,
                    "col": c,
                    "bin_code": bc,
                    "created_at": at,
                    "updated_at": at,
                    "created_by": getattr(user, "id", None),
                    "updated_by": getattr(user, "id", None),
                }
                for r, c, bc in x["cells"]
            ],
        )
        ids.append(mid)
    s.commit()
    rows = [r for i in ids if (r := one(s, tid, "substrate_map", i))]
    return {
        "import_id": str(imp),
        "data": serialize(s, tid, ENTITIES["substrate_map"], rows),
    }


def map_detail(s: Session, tid: uuid.UUID, m: Row, cells: bool = True) -> Row:
    """坐标图详情：含定义集编码 / 版本，可选附带全部坐标格。"""
    out = serialize(s, tid, ENTITIES["substrate_map"], [m])[0]
    bs = one(s, tid, "bin_set", m["bin_set_id"])
    out["bin_set_code"] = bs and bs["code"]
    out["bin_set_version"] = bs and bs["version"]
    if cells:
        c = TABLES["map_cell"]
        rs = (
            conn(s)
            .execute(
                sa.select(c.c.row, c.c.col, c.c.bin_code)
                .where(c.c.tenant_id == tid, c.c.substrate_map_id == m["id"])
                .order_by(c.c.row, c.c.col)
            )
            .all()
        )
        out["cells"] = [{"row": r, "col": cc, "bin_code": b} for r, cc, b in rs]
    return out


def by_substrate(
    s: Session, tid: uuid.UUID, substrate_id: str, version: int | None
) -> Row:
    """按基板（晶圆）ID 查坐标图：默认最新版本，可指定版本；附带全部版本号。"""
    rows = _by_code(s, tid, "substrate_map", substrate_id)
    if not rows:
        raise HTTPException(status_code=404, detail=f"map for {substrate_id} not found")
    rows.sort(key=lambda r: r["map_version"])
    m = (
        rows[-1]
        if version is None
        else next((r for r in rows if r["map_version"] == version), None)
    )
    if not m:
        raise HTTPException(
            status_code=404, detail=f"map {substrate_id} v{version} not found"
        )
    return {**map_detail(s, tid, m), "versions": [r["map_version"] for r in rows]}


def check_split(m: Row, children_qty: int) -> None:
    """拆批层守恒（供 B8 / B5 复用）：子批数量合计 + 排除数量 = 坐标图总数，否则 422。"""
    ex = int(m.get("excluded_qty") or 0)
    tot = int(m["total_qty"])
    if children_qty + ex != tot:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "map_qty_mismatch",
                "message": f"children {children_qty} + excluded {ex} != map total {tot}",
                "children_qty": children_qty,
                "excluded_qty": ex,
                "total_qty": tot,
            },
        )


def latest_map(s: Session, tid: uuid.UUID, substrate_id: str) -> Row | None:
    """基板（晶圆 ID）的最新版本坐标图，没有时为 None（供 B5 单位转换使用）。"""
    rows = _by_code(s, tid, "substrate_map", substrate_id)
    return max(rows, key=lambda r: r["map_version"]) if rows else None


def good_cells(s: Session, tid: uuid.UUID, m: Row) -> list[tuple[int, int]]:
    """坐标图里良品 bin（bin_type=good）的坐标，按 (row, col) 排序。"""
    types = bin_types(s, tid, m["bin_set_id"])
    c = TABLES["map_cell"]
    rs = conn(s).execute(
        sa.select(c.c.row, c.c.col, c.c.bin_code)
        .where(c.c.tenant_id == tid, c.c.substrate_map_id == m["id"])
        .order_by(c.c.row, c.c.col)
    )
    return [(r, cc) for r, cc, b in rs if types.get(b) in GOOD_BIN_TYPES]
