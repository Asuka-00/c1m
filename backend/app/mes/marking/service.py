"""打标模板服务（P3-B1，D79-1/2、D79 补充七、D89）。

状态（D89 补充一）：draft → approved → retired，无 pending / 提交接口。草稿可编辑；approved/retired
编辑 409 ``template_readonly``；已有草稿再建新版本 409 ``draft_exists``；起草人自批 422
``self_approval``（404 之后、409 之前）；新版本批准后同模板旧 approved 自动 retired。
lines 为字符串数组（D79-1）。
"""

import re
import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.models import actor_name, iso_utc
from app.core.spec.base import conn, now
from app.core.spec.engine import TABLES
from app.core.spec.errors import http_422
from app.mes.common.query import find, one
from app.mes.common.rows import _ins, _upd
from app.mes.marking.events import emit_approved

Row = dict[str, Any]
TPL, VER = "marking_template", "marking_template_version"
#: D79-1 占位符白名单
PLACEHOLDERS = ("trace_code", "date_code", "lot_id", "product_code", "customer_code")
_PH = re.compile(r"\{([^{}]*)\}")
OPEN = ("draft",)


def conflict(code: str, message: str, **extra: Any) -> HTTPException:
    """409 对象格式 {code, message}（D82 补充三）。"""
    return HTTPException(
        status_code=409, detail={"code": code, "message": message, **extra}
    )


def not_found() -> HTTPException:
    """404 模板不存在（含跨租户）。"""
    return HTTPException(
        status_code=404,
        detail={
            "code": "marking_template_not_found",
            "message": "marking template not found",
        },
    )


# ---------------- 占位符 ----------------
def unknown_placeholders(lines: list[str]) -> list[tuple[int, str]]:
    """(行下标, 未知占位符)；同一行同名只算一次，按出现顺序。"""
    out: list[tuple[int, str]] = []
    for i, ln in enumerate(lines):
        seen: list[str] = []
        for name in _PH.findall(ln):
            if name not in PLACEHOLDERS and name not in seen:
                seen.append(name)
                out.append((i, name))
    return out


def check_placeholders(lines: list[str]) -> None:
    """D89-2 / 补充一：每个未知占位符一条 422 value_error，loc ["body","lines",i]。"""
    bad = unknown_placeholders(lines)
    if bad:
        raise http_422(
            [
                (
                    ("lines", i),
                    f"unknown placeholder {{{name}}}",
                    "value_error",
                    {"reason": "unknown_placeholder", "placeholder": name},
                )
                for i, name in bad
            ]
        )


# ---------------- 读 ----------------
def _t(v: Any) -> Any:
    return iso_utc(v) if v is not None else None


def ser_version(v: Row) -> Row:
    """版本行输出（时间 UTC Z）。"""
    return {
        "id": str(v["id"]),
        "version": v["version"],
        "status": v["status"],
        "lines": v.get("lines") or [],
        "created_by": v.get("drafter"),
        "created_at": _t(v.get("created_at")),
        "updated_at": _t(v.get("updated_at")),
        "approved_by": v.get("approved_by"),
        "approved_at": _t(v.get("approved_at")),
        "retired_at": _t(v.get("retired_at")),
    }


def versions(s: Session, tid: uuid.UUID, template_id: Any) -> list[Row]:
    """模板的全部版本，新版本在前。"""
    rows = find(s, tid, VER, template_id=template_id)
    return sorted(rows, key=lambda r: r["version"], reverse=True)


def ser(s: Session, tid: uuid.UUID, t: Row, with_versions: bool = True) -> Row:
    """模板输出：最新版本的 version/status/lines + approved_version (+ versions[])。"""
    vs = versions(s, tid, t["id"])
    latest = vs[0] if vs else None
    appr = next((v for v in vs if v["status"] == "approved"), None)
    p = one(s, tid, "product", t["product_id"])
    c = one(s, tid, "customer", t["customer_id"])
    out: Row = {
        "id": str(t["id"]),
        "code": t["code"],
        "description": t.get("description"),
        "product_id": str(t["product_id"]),
        "product_code": p["code"] if p else None,
        "product_name": p["name"] if p else None,
        "customer_id": str(t["customer_id"]),
        "customer_code": c["code"] if c else None,
        "customer_name": c["name"] if c else None,
        "created_by": t.get("creator"),
        "created_at": _t(t.get("created_at")),
        "updated_at": _t(t.get("updated_at")),
        "version": latest["version"] if latest else None,
        "status": latest["status"] if latest else None,
        "lines": (latest.get("lines") or []) if latest else [],
        "approved_version": appr["version"] if appr else None,
    }
    if with_versions:
        out["versions"] = [ser_version(v) for v in vs]
    return out


def get(s: Session, tid: uuid.UUID, rid: Any) -> Row:
    """读模板，不存在 404。"""
    t = one(s, tid, TPL, rid)
    if not t:
        raise not_found()
    return t


def list_templates(
    s: Session, tid: uuid.UUID, q: str | None, offset: int, limit: int
) -> Row:
    """分页列表（按 code）。"""
    t = TABLES[TPL]
    stmt = sa.select(t).where(t.c.tenant_id == tid)
    if q:
        esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(
            sa.or_(
                t.c.code.ilike(f"%{esc}%", escape="\\"),
                t.c.name.ilike(f"%{esc}%", escape="\\"),
            )
        )
    count = (
        conn(s)
        .execute(sa.select(sa.func.count()).select_from(stmt.subquery()))
        .scalar()
    )
    rows = (
        conn(s).execute(stmt.order_by(t.c.code).offset(offset).limit(limit)).mappings()
    )
    return {
        "data": [ser(s, tid, dict(r), with_versions=False) for r in rows],
        "count": int(count or 0),
    }


# ---------------- 写 ----------------
def _code_taken(s: Session, tid: uuid.UUID, code: str, not_id: Any = None) -> bool:
    t = TABLES[TPL]
    stmt = sa.select(t.c.id).where(
        t.c.tenant_id == tid, sa.func.upper(t.c.code) == code.upper()
    )
    if not_id is not None:
        stmt = stmt.where(t.c.id != not_id)
    return conn(s).execute(stmt.limit(1)).first() is not None


def _pair_taken(
    s: Session, tid: uuid.UUID, pid: Any, cid: Any, not_id: Any = None
) -> bool:
    t = TABLES[TPL]
    stmt = sa.select(t.c.id).where(
        t.c.tenant_id == tid,
        t.c.product_id == uuid.UUID(str(pid)),
        t.c.customer_id == uuid.UUID(str(cid)),
    )
    if not_id is not None:
        stmt = stmt.where(t.c.id != not_id)
    return conn(s).execute(stmt.limit(1)).first() is not None


def _dup(_key: Any = None) -> HTTPException:
    """D89 补充二：code 重复 / 产品+客户重复都按通用重复键错误返回（同 spec.errors.integrity）。"""
    return HTTPException(
        status_code=409, detail="A record with the same key already exists"
    )


def _refs(s: Session, tid: uuid.UUID, d: Row) -> None:
    """product_id / customer_id 不存在（含跨租户）→ 404 ``<实体>_not_found``。

    TODO(B1)：引用不存在按 404（同 ct-move 的 _opt_ref）还是 422 未定。
    """
    for code in ("product", "customer"):
        rid = d.get(f"{code}_id")
        if rid is not None and one(s, tid, code, uuid.UUID(str(rid))) is None:
            raise HTTPException(
                status_code=404,
                detail={"code": f"{code}_not_found", "message": f"{code} not found"},
            )


def create(s: Session, tid: uuid.UUID, d: Row, user: Any) -> Row:
    """建模板 + v1 草稿。"""
    _refs(s, tid, d)
    if _code_taken(s, tid, d["code"]) or _pair_taken(
        s, tid, d["product_id"], d["customer_id"]
    ):
        raise _dup()
    me = actor_name(user)
    rid = _ins(
        s,
        tid,
        TPL,
        user,
        code=d["code"],
        # D89 第1条撤回：请求体无 name/description；表上 spec 隐式 name 列 NOT NULL，内部存 code
        name=d["code"],
        description=d.get("description"),
        product_id=uuid.UUID(str(d["product_id"])),
        customer_id=uuid.UUID(str(d["customer_id"])),
        creator=me,
    )
    _ins(
        s,
        tid,
        VER,
        user,
        template_id=rid,
        version=1,
        status="draft",
        lines=list(d["lines"]),
        drafter=me,
    )
    return ser(s, tid, get(s, tid, rid))


def _open(s: Session, tid: uuid.UUID, rid: Any) -> Row | None:
    return next((v for v in versions(s, tid, rid) if v["status"] in OPEN), None)


def update(s: Session, tid: uuid.UUID, rid: Any, d: Row, user: Any) -> Row:
    """编辑草稿；最新版本不是 draft → 409 template_readonly。"""
    t = get(s, tid, rid)  # 404
    # D90-3：product_id / customer_id 建好后不可改；同值视为没改
    bad = [
        k
        for k in ("product_id", "customer_id")
        if k in d and uuid.UUID(str(d[k])) != t[k]
    ]
    if bad:
        raise http_422(
            [
                ((k,), f"{k} cannot be changed", "value_error", {"reason": "immutable"})
                for k in bad
            ]
        )
    vs = versions(s, tid, rid)
    latest = vs[0] if vs else None
    if not latest or latest["status"] != "draft":
        st = latest["status"] if latest else None
        raise conflict(
            "template_readonly",
            f"marking template {t['code']} v{latest['version'] if latest else '-'} is {st}; "
            "only a draft can be edited",
        )
    if "code" in d and _code_taken(s, tid, d["code"], not_id=rid):
        raise _dup()
    tv: dict[str, Any] = {"code": d["code"], "name": d["code"]} if "code" in d else {}
    if "description" in d:
        tv["description"] = d["description"]
    if tv:
        _upd(s, tid, TPL, rid, user, **tv)
    if "lines" in d:
        _upd(s, tid, VER, latest["id"], user, lines=list(d["lines"]))
    return ser(s, tid, get(s, tid, rid))


def new_version(s: Session, tid: uuid.UUID, rid: Any, user: Any) -> Row:
    """复制最新版本为新草稿；已有 draft → 409 draft_exists。"""
    t = get(s, tid, rid)  # 404
    op = _open(s, tid, rid)
    if op:
        raise conflict(
            "draft_exists",
            f"marking template {t['code']} already has v{op['version']} ({op['status']})",
        )
    vs = versions(s, tid, rid)
    latest = vs[0] if vs else None
    _ins(
        s,
        tid,
        VER,
        user,
        template_id=rid,
        version=(latest["version"] if latest else 0) + 1,
        status="draft",
        lines=(latest.get("lines") or []) if latest else [],
        drafter=actor_name(user),
    )
    return ser(s, tid, t)


def approve(s: Session, tid: uuid.UUID, rid: Any, user: Any) -> Row:
    """批准 draft 版本，旧 approved 自动 retired，发 marking_template.approved。"""
    t = get(s, tid, rid)  # 404
    op = _open(s, tid, rid)
    me = actor_name(user)
    # D79 补充七：起草人自批 422 先于 409 invalid_transition
    if op and me and (op.get("drafter") or "").lower() == me.lower():
        raise http_422(
            [
                (
                    "approved_by",
                    "the drafter cannot approve their own template version",
                    "value_error",
                    {"reason": "self_approval"},
                )
            ]
        )
    if not op:
        raise conflict(
            "invalid_transition",
            f"marking template {t['code']} has no draft version to approve",
        )
    at = now()
    retired = None
    for v in versions(s, tid, rid):
        if v["status"] == "approved":
            _upd(s, tid, VER, v["id"], user, status="retired", retired_at=at)
            retired = v["version"]
    _upd(s, tid, VER, op["id"], user, status="approved", approved_by=me, approved_at=at)
    out = ser(s, tid, t)
    emit_approved(
        s,
        tid,
        t,
        op,
        user,
        {
            "template_id": str(t["id"]),
            "tenant_id": str(tid),
            "code": t["code"],
            "version": op["version"],
            "retired_version": retired,
            "approved_by": me,
            "occurred_at": iso_utc(at),
            "actor": me or "system",
        },
    )
    return out


# ---------------- 预览 / 校验（只读） ----------------
def _lines_of(s: Session, tid: uuid.UUID, template_id: Any) -> list[str]:
    get(s, tid, template_id)  # 404
    vs = versions(s, tid, template_id)
    # TODO(B1)：按 template_id 预览/校验取哪个版本未规定，暂取最新版本
    return list(vs[0].get("lines") or []) if vs else []


def preview(
    s: Session, tid: uuid.UUID, template_id: Any, lines: list[str] | None
) -> Row:
    """只读预览 {template_id, lines}。"""
    src = list(lines) if lines is not None else _lines_of(s, tid, template_id)
    # TODO(B1)：预览是否用示例值替换占位符未规定，暂原样返回各行
    return {"template_id": str(template_id) if template_id else None, "lines": src}


def validate_lines(
    s: Session, tid: uuid.UUID, template_id: Any, lines: list[str] | None
) -> Row:
    """只读校验 {valid, unknown_placeholders}。"""
    src = lines if lines is not None else _lines_of(s, tid, template_id)
    bad = [name for _, name in unknown_placeholders(src)]
    uniq = list(dict.fromkeys(bad))
    return {"valid": not uniq, "unknown_placeholders": uniq}
