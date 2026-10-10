"""Code rule engine: patterns like ``LT{YY}{MM}{SEQ}`` -> ``LT26100001``.

Tokens: {YYYY} {YY} {MM} {DD} {JJJ} (day of year), {SEQ} (decimal, zero padded
to seq_width), {SEQ36} (base 36), {LOT} and {SLOT} / {SLOT:2} (wafer IDs, from
the caller's context). Counters live in ``mes_code_rule_counter`` per rule and
period (seq_reset: never / daily / monthly / yearly).
"""

import re
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.mes.core import TABLES
from app.mes.service import MesError, conn, now

TOKEN = re.compile(r"\{([A-Z0-9]+)(?::(\d+))?\}")
KNOWN = {"YYYY", "YY", "MM", "DD", "JJJ", "SEQ", "SEQ36", "LOT", "SLOT"}
B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def check_pattern(pattern: str) -> list[tuple[str, str]]:
    errs: list[tuple[str, str]] = []
    tokens = [m.group(1) for m in TOKEN.finditer(pattern)]
    for tk in tokens:
        if tk not in KNOWN:
            errs.append(("pattern", f"pattern: unknown token {{{tk}}}"))
    if not {"SEQ", "SEQ36", "SLOT"} & set(tokens):
        errs.append(("pattern", "pattern: needs {SEQ}, {SEQ36} or {SLOT}"))
    if re.sub(TOKEN, "", pattern).count("{") or re.sub(TOKEN, "", pattern).count("}"):
        errs.append(("pattern", "pattern: unbalanced braces"))
    return errs


def period(reset: str | None, at: datetime) -> str:
    return {
        "daily": at.strftime("%Y%m%d"),
        "monthly": at.strftime("%Y%m"),
        "yearly": at.strftime("%Y"),
    }.get(reset or "never", "")


def b36(n: int, width: int) -> str:
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = B36[r] + s
    return (s or "0").rjust(width, "0")


def render(
    rule: dict[str, Any], seq: int, at: datetime, ctx: dict[str, Any] | None = None
) -> str:
    ctx = ctx or {}
    width = int(rule.get("seq_width") or 4)

    def sub(m: re.Match[str]) -> str:
        tk, arg = m.group(1), m.group(2)
        match tk:
            case "YYYY":
                return at.strftime("%Y")
            case "YY":
                return at.strftime("%y")
            case "MM":
                return at.strftime("%m")
            case "DD":
                return at.strftime("%d")
            case "JJJ":
                return at.strftime("%j")
            case "SEQ":
                s = str(seq).rjust(width, "0")
                if len(s) > width:
                    raise MesError([("seq", "sequence overflow for this period")])
                return s
            case "SEQ36":
                return b36(seq, width)
            case "LOT":
                return str(ctx.get("LOT", ""))
            case "SLOT":
                return str(ctx.get("SLOT", seq)).rjust(int(arg or 2), "0")
        return m.group(0)

    return TOKEN.sub(sub, rule["pattern"])


def _counter(
    session: Session, tenant_id: uuid.UUID, rule: dict[str, Any], per: str, lock: bool
) -> dict[str, Any] | None:
    t = TABLES["code_rule_counter"]
    stmt = sa.select(t).where(
        t.c.tenant_id == tenant_id, t.c.code_rule_id == rule["id"], t.c.period == per
    )
    if lock:
        stmt = stmt.with_for_update()
    r = conn(session).execute(stmt).mappings().first()
    return dict(r) if r else None


def preview(
    session: Session,
    tenant_id: uuid.UUID,
    rule: dict[str, Any],
    count: int,
    ctx: dict[str, Any] | None = None,
) -> list[str]:
    at = now()
    c = _counter(
        session, tenant_id, rule, period(rule.get("seq_reset"), at), lock=False
    )
    start = (c["value"] + 1) if c else int(rule.get("seq_start") or 1)
    return [render(rule, start + i, at, ctx) for i in range(count)]


def generate(
    session: Session,
    tenant_id: uuid.UUID,
    rule: dict[str, Any],
    count: int,
    ctx: dict[str, Any] | None = None,
    *,
    commit: bool = True,
) -> list[str]:
    """Reserve `count` codes (increments the counter atomically)."""
    at = now()
    per = period(rule.get("seq_reset"), at)
    t = TABLES["code_rule_counter"]
    c = conn(session)
    cur = _counter(session, tenant_id, rule, per, lock=True)
    if cur is None:
        c.execute(
            sa.insert(t).values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                code_rule_id=rule["id"],
                period=per,
                value=int(rule.get("seq_start") or 1) - 1,
                created_at=at,
            )
        )
        cur = _counter(session, tenant_id, rule, per, lock=True)
    assert cur
    first = cur["value"] + 1
    codes = [render(rule, first + i, at, ctx) for i in range(count)]
    c.execute(
        sa.update(t)
        .where(t.c.id == cur["id"])
        .values(value=cur["value"] + count, updated_at=at)
    )
    if commit:
        session.commit()
    return codes
