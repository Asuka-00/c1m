"""P3-B6 人员资质履历（D74 + 补充 Q6-1/Q6-2、D81）。

- 预警天数单一来源 :func:`warn_days`：检查规则 ``qual_expiry_notice`` 的参数 ``warn_days``
  （1–365 整数，缺失 / 非法按 30；规则严重度为 off 时仍读该值）。
- 通用 CRUD 写 ``operator_qual`` 后（同一事务）按变更写一条履历并发 ``operator_qual.*`` 事件
  （:func:`_after_write`，挂在 ``AFTER_WRITE``）。请求体顶层的 ``reason_id`` / ``comment`` /
  ``approved_by`` 由路由先校验（:func:`check_extras`），经 :data:`EXTRA` 传给钩子。
- 每日扫描 :func:`expired_scan`：到期次日（站点时区）发 ``operator_qual.expired`` 并写履历，
  按 (qual_id, expires_on) 去重；``is_active`` 不变（Q6-1）。
"""

import uuid
from contextvars import ContextVar
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session

from app.core.models import actor_name
from app.core.spec.audit import audit
from app.core.spec.base import conn, now
from app.core.spec.engine import ENTITIES, TABLES, Entity
from app.core.spec.errors import http_422
from app.core.spec.excel import tenant_tz
from app.core.spec.write import AFTER_WRITE
from app.mes.common.query import find, one
from app.mes.common.rows import _ins
from app.mes.common.sitedate import site_today
from app.platform.notification.service import notify, register_event

Row = dict[str, Any]

ENT = "operator_qual"
LOG = "operator_qual_log"
DEFAULT_WARN_DAYS = 30
WARN_DAYS_RULE = "qual_expiry_notice"  # 检查规则 check_type；参数名 warn_days
COMMENT_MAX = 300
#: 请求体顶层放行、由本模块处理的字段（不写入资质行）
EXTRA_FIELDS = ("reason_id", "comment", "approved_by")
#: 履历快照字段（列名）
SNAP = (
    "username",
    "operation_id",
    "equipment_type_id",
    "certified_on",
    "expires_on",
    "is_active",
)

_EVENTS = {
    "operator_qual.granted": ("Qualification granted|资质授予|資格付与", "info"),
    "operator_qual.renewed": ("Qualification renewed|资质延期|資格延長", "info"),
    "operator_qual.changed": ("Qualification changed|资质变更|資格変更", "info"),
    "operator_qual.deactivated": (
        "Qualification deactivated|资质停用|資格停止",
        "warning",
    ),
    "operator_qual.expired": ("Qualification expired|资质过期|資格期限切れ", "warning"),
}
for _c, (_l, _sev) in _EVENTS.items():
    register_event(_c, _l, _sev, ENT)
EVENTS = tuple(_EVENTS)

#: 当前请求的附加字段（路由设置，写入钩子读取）
EXTRA: ContextVar[Row | None] = ContextVar("operator_qual_extra", default=None)


# ---------------- 预警天数 ----------------
def warn_days(s: Session, tid: uuid.UUID) -> int:
    """预警天数（唯一来源）：``qual_expiry_notice`` 规则参数 ``warn_days``，非法按 30。"""
    for r in find(
        s, tid, "check_rule", order="code", check_type=WARN_DAYS_RULE, is_active=True
    ):
        v = (r.get("params") or {}).get("warn_days")
        if isinstance(v, bool):
            return DEFAULT_WARN_DAYS
        if isinstance(v, int) and 1 <= v <= 365:
            return v
        if isinstance(v, str) and v.strip().isdigit() and 1 <= int(v) <= 365:
            return int(v)
        return DEFAULT_WARN_DAYS
    return DEFAULT_WARN_DAYS


# ---------------- 请求体附加字段（body 阶段，404 之前） ----------------
def required_extras(method: str, body: Row) -> tuple[str, ...]:
    """按请求体判定必填项（不读库）。

    PATCH 带 ``is_active=false`` → 停用（reason_id、comment）；带 ``expires_on`` → 延期
    （reason_id、comment、approved_by）。
    """
    if method != "PATCH":
        return ()
    need: list[str] = []
    if body.get("is_active") is False:
        need += ["reason_id", "comment"]
    if "expires_on" in body:
        need += ["reason_id", "comment", "approved_by"]
    return tuple(dict.fromkeys(need))


def check_extras(
    s: Session, tid: uuid.UUID, method: str, body: Row, user: Any = None
) -> Row:
    """请求体阶段（404 前）校验附加字段，顺序：

    1. ``is_active=false`` 与 ``expires_on`` 同时出现 → 422 value_error
       ``conflicting_fields``（D85 补充二）；
    2. 缺失 → 422 missing；
    3. 格式 / 原因码 / 批准人不合法 → 422 value_error；
    4. ``approved_by`` = 发请求的用户 → 422 value_error ``self_approval``（任何带
       approved_by 的写请求，含 POST 授予、停用）。
    """
    extra = {k: body.pop(k) for k in EXTRA_FIELDS if k in body}
    errs: list[tuple[Any, ...]] = []
    if method == "PATCH" and body.get("is_active") is False and "expires_on" in body:
        raise http_422(
            [
                (
                    "is_active",
                    "deactivate and renew cannot be combined in one request",
                    "value_error",
                    {
                        "reason": "conflicting_fields",
                        "fields": ["is_active", "expires_on"],
                    },
                )
            ]
        )
    for k in required_extras(method, body):
        v = extra.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            errs.append((k, "Field required", "missing"))
    if errs:
        raise http_422(errs)
    c = extra.get("comment")
    if c is not None and (not isinstance(c, str) or len(c) > COMMENT_MAX):
        errs.append(
            (
                "comment",
                f"comment: string of at most {COMMENT_MAX} characters",
                "value_error",
                {"reason": "max_length", "max_length": COMMENT_MAX},
            )
        )
    rid = extra.get("reason_id")
    if rid is not None:
        rc = None
        try:
            rc = one(s, tid, "reason_code", uuid.UUID(str(rid)))
        except ValueError:
            rc = None
        if (
            not rc
            or rc.get("reason_type") != "operator_qual"
            or rc.get("is_active") is False
        ):
            errs.append(
                (
                    "reason_id",
                    "reason_id: must be an active reason code of type operator_qual",
                    "value_error",
                    {"reason": "invalid_reason"},
                )
            )
        else:
            extra["reason_id"] = rc["id"]
            extra["reason_code"] = rc["code"]
    ab = extra.get("approved_by")
    if ab is not None and (
        not isinstance(ab, str) or len(ab) > 64 or not _member(s, tid, ab)
    ):
        errs.append(
            (
                "approved_by",
                "approved_by: not a user of this tenant",
                "value_error",
                {"reason": "user_not_found"},
            )
        )
    if errs:
        raise http_422(errs)
    ab = extra.get("approved_by")
    me = actor_name(user) if user is not None else None
    if ab and me and ab.strip().lower() == me.lower():
        raise http_422(
            [
                (
                    "approved_by",
                    "approved_by must not be the requesting user",
                    "value_error",
                    {"reason": "self_approval"},
                )
            ]
        )
    return extra


def _member(s: Session, tid: uuid.UUID, username: str) -> bool:
    return bool(
        conn(s)
        .execute(
            sa.text(
                'SELECT 1 FROM tenant_member m JOIN "user" u ON u.id = m.user_id '
                "WHERE m.tenant_id = :t AND lower(u.username) = lower(:n) LIMIT 1"
            ),
            {"t": tid, "n": username.strip()},
        )
        .first()
    )


def check_holder_approval(extra: Row, row: Row) -> None:
    """批准人不能是资质持有人（D85）：404 之后、409 之前；POST 时 row 为请求体。"""
    ab = extra.get("approved_by")
    holder = row.get("username")
    if ab and isinstance(holder, str) and ab.strip().lower() == holder.strip().lower():
        raise http_422(
            [
                (
                    "approved_by",
                    "approved_by must not be the qualification holder",
                    "value_error",
                    {"reason": "holder_approval"},
                )
            ]
        )


# ---------------- 履历 + 事件 ----------------
def _j(v: Any) -> Any:
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat().replace("+00:00", "Z")
    if isinstance(v, date):
        return v.isoformat()
    return v


def _snap(row: Row, keys: list[str]) -> Row:
    return {k: _j(row.get(k)) for k in keys}


def _later(a: date | None, b: date | None) -> bool:
    """B 比 a 更晚（None = 永久有效，视为最晚）。"""
    if a is None:
        return False
    return b is None or b > a


def classify(old: Row | None, new: Row) -> tuple[str, list[str]] | None:
    """动作与变更字段；无变更返回 None。优先级：停用 / 启用 > 延期 > 变更。"""
    if old is None:
        return "granted", list(SNAP)
    changed = [k for k in SNAP if old.get(k) != new.get(k)]
    if not changed:
        return None
    if "is_active" in changed:
        return ("deactivated" if not new.get("is_active") else "reactivated"), changed
    if "expires_on" in changed and _later(old.get("expires_on"), new.get("expires_on")):
        return "renewed", changed
    return "changed", changed


def write_log(
    s: Session,
    tid: uuid.UUID,
    qual: Row,
    action: str,
    before: Row | None,
    after: Row | None,
    extra: Row,
    user: Any,
) -> uuid.UUID:
    """追加一条履历（调用方事务内）。"""
    return _ins(
        s,
        tid,
        LOG,
        user,
        qual_id=qual["id"],
        action=action,
        before=before,
        after=after,
        reason_id=extra.get("reason_id"),
        comment=extra.get("comment"),
        approved_by=extra.get("approved_by"),
        username=actor_name(user) or "system",
        at=now(),
    )


def emit(
    s: Session, tid: uuid.UUID, event: str, qual: Row, user: Any, payload: Row
) -> None:
    """资质领域事件：audit_log（entity=operator_qual，action=事件名）+ 订阅通知。"""
    assert event in _EVENTS, event
    op = one(s, tid, "operation", qual.get("operation_id"))
    body = {
        "qual_id": str(qual["id"]),
        "tenant_id": str(tid),
        "username": qual.get("username"),
        "operation_id": _j(qual.get("operation_id")),
        "operation_code": op["code"] if op else None,
        "equipment_type_id": _j(qual.get("equipment_type_id")),
        "occurred_at": _j(now()),
        "actor": actor_name(user) or "system",
        **payload,
    }
    audit(s, tid, ENTITIES[ENT], event, qual, user, {"payload": (None, body)})
    notify(
        s,
        tid,
        event,
        title=f"{_EVENTS[event][0].split('|')[0]}: {qual.get('username')}",
        params=body,
        object_type=ENT,
        object_id=qual["id"],
        object_code=qual.get("username"),
        link="/mes/operator-qual",
    )


def _payload(
    action: str,
    old: Row | None,
    new: Row,
    before: Row | None,
    after: Row,
    keys: list[str],
    extra: Row,
) -> Row | None:  # noqa: E501
    rid = _j(extra.get("reason_id"))
    if action == "granted":
        return {
            "certified_on": _j(new.get("certified_on")),
            "expires_on": _j(new.get("expires_on")),
            "reason_id": rid,
            "comment": extra.get("comment"),
        }
    if action == "renewed":
        return {
            "expires_on_before": _j((old or {}).get("expires_on")),
            "expires_on": _j(new.get("expires_on")),
            "reason_id": rid,
            "reason_code": extra.get("reason_code"),
            "comment": extra.get("comment"),
            "approved_by": extra.get("approved_by"),
        }
    if action == "deactivated":
        return {
            "reason_id": rid,
            "reason_code": extra.get("reason_code"),
            "comment": extra.get("comment"),
        }
    if action == "changed":
        return {
            "changes": {k: [(before or {}).get(k), after[k]] for k in keys},
            "reason_id": rid,
            "comment": extra.get("comment"),
        }
    return None  # reactivated：只写履历（domain-events 未登记该事件）


def _after_write(
    s: Session, tid: uuid.UUID, _e: Entity, old: Row | None, new: Row, user: Any
) -> None:
    c = classify(old, new)
    if c is None:
        return
    action, keys = c
    extra = EXTRA.get() or {}
    before = None if old is None else _snap(old, keys)
    after = _snap(new, keys)
    write_log(s, tid, new, action, before, after, extra, user)
    payload = _payload(action, old, new, before, after, keys, extra)
    if payload is not None:
        emit(s, tid, f"operator_qual.{action}", new, user, payload)


AFTER_WRITE.setdefault(ENT, []).append(_after_write)


# ---------------- 有履历不可删（D74 / D72） ----------------
def check_referenced(s: Session, tid: uuid.UUID, qual_id: Any) -> None:
    """资质不可删（D85 补充二）：D81 校验之后恒 409 referenced，改用停用。"""
    t = TABLES[LOG]
    n = (
        conn(s)
        .execute(
            sa.select(sa.func.count()).where(
                t.c.tenant_id == tid, t.c.qual_id == qual_id
            )
        )
        .scalar()
    )
    raise HTTPException(
        status_code=409,
        detail={
            "code": "referenced",
            "message": "qualification cannot be deleted; deactivate it instead",
            "ref_type": LOG,
            "ref_count": int(n or 0),
        },
    )


# ---------------- 查询 ----------------
def history(
    s: Session, tid: uuid.UUID, qual_id: uuid.UUID, limit: int, offset: int
) -> Row:
    """资质履历（D74）：按 at 倒序。"""
    t = TABLES[LOG]
    rows = (
        conn(s)
        .execute(
            sa.select(t)
            .where(t.c.tenant_id == tid, t.c.qual_id == qual_id)
            .order_by(t.c.at.desc(), t.c.created_at.desc(), t.c.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .mappings()
        .all()
    )
    return {
        "rows": [
            {
                "id": str(r["id"]),
                "action": r["action"],
                "before": r["before"],
                "after": r["after"],
                "reason_id": _j(r["reason_id"]),
                "comment": r["comment"],
                "approved_by": r["approved_by"],
                "username": r["username"],
                "at": _j(r["at"]),
            }
            for r in rows
        ]
    }


def expiring(s: Session, tid: uuid.UUID, days: int | None) -> Row:
    """即将到期汇总（D64/D74）：is_active 且 days_left ∈ [0, days]；永久的不返回。"""
    wd = warn_days(s, tid)
    d = days if days is not None else wd
    today = site_today(s, tid)
    out = []
    for q in find(s, tid, ENT, is_active=True):
        exp = q.get("expires_on")
        if not exp:
            continue
        left = (exp - today).days
        if 0 <= left <= d:
            op = one(s, tid, "operation", q["operation_id"])
            et = one(s, tid, "equipment_type", q.get("equipment_type_id"))
            out.append(
                {
                    "qual_id": str(q["id"]),
                    "username": q["username"],
                    "operation": op["code"] if op else None,
                    "equipment_type": et["code"] if et else None,
                    "expires_on": exp.isoformat(),
                    "days_left": left,
                }
            )
    out.sort(key=lambda r: (r["days_left"], r["username"]))
    return {"warn_days": wd, "timezone": str(tenant_tz(s, tid)), "rows": out}


# ---------------- 每日到期扫描 ----------------
def expired_scan(s: Session, tid: uuid.UUID, today: date | None = None) -> int:
    """到期次日起写 expired 履历 + 发事件，按 (qual_id, expires_on) 去重；不改 is_active。"""
    today = today or site_today(s, tid)
    t = TABLES[LOG]
    n = 0
    for q in find(s, tid, ENT, is_active=True):
        exp = q.get("expires_on")
        if not exp or exp >= today:
            continue
        iso = exp.isoformat()
        seen = (
            conn(s)
            .execute(
                sa.select(t.c.id).where(
                    t.c.tenant_id == tid,
                    t.c.qual_id == q["id"],
                    t.c.action == "expired",
                    sa.cast(t.c.after, sa.JSON)["expires_on"].as_string() == iso,
                )
            )
            .first()
        )
        if seen:
            continue
        write_log(s, tid, q, "expired", None, {"expires_on": iso}, {}, None)
        emit(s, tid, "operator_qual.expired", q, None, {"expires_on": iso})
        n += 1
    return n


# ---------------- 通用 CRUD 受控写登记（D81：必带 Idempotency-Key） ----------------
def _register() -> None:
    from app.mes.common.keyed_write import KEYED, META_HOOKS, KeyedWrite

    META_HOOKS[ENT] = lambda s, tid: {"warn_days": warn_days(s, tid)}

    KEYED[ENT] = KeyedWrite(
        extras=check_extras,
        after_404=check_holder_approval,
        before_delete=check_referenced,
        extra_var=EXTRA,
    )


_register()
