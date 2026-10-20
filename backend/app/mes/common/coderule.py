"""编码规则引擎：如 ``LT{YY}{MM}{SEQ}`` → ``LT26100001``。

占位符：{YYYY} {YY} {MM} {DD} {JJJ}（年内第几天）、{SEQ}（十进制，按 seq_width 补零）、
{SEQ36}（36 进制）、{LOT} 与 {SLOT} / {SLOT:2}（晶圆号，由调用方上下文提供）。
计数器按规则 + 周期保存在 ``mes_code_rule_counter``（seq_reset：never / daily / monthly / yearly）。
"""

import re
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.spec.base import conn, now
from app.core.spec.engine import TABLES
from app.core.spec.errors import FieldError, MesError, fe

TOKEN = re.compile(r"\{([A-Z0-9]+)(?::(\d+))?\}")
KNOWN = {"YYYY", "YY", "MM", "DD", "JJJ", "SEQ", "SEQ36", "LOT", "SLOT"}
B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def check_pattern(pattern: str) -> list[FieldError]:
    """校验编码模式，返回字段错误列表（未知占位符、缺少序号等）。"""
    errs: list[FieldError] = []
    tokens = [m.group(1) for m in TOKEN.finditer(pattern)]
    for tk in tokens:
        if tk not in KNOWN:
            errs.append(
                fe(
                    "pattern",
                    ec.CODERULE_UNKNOWN_TOKEN,
                    f"pattern: unknown token {{{tk}}}",
                    token=f"{{{tk}}}",
                )
            )
    if not {"SEQ", "SEQ36", "SLOT"} & set(tokens):
        errs.append(
            fe(
                "pattern",
                ec.CODERULE_NEEDS_SEQ,
                "pattern: needs {SEQ}, {SEQ36} or {SLOT}",
            )
        )
    if re.sub(TOKEN, "", pattern).count("{") or re.sub(TOKEN, "", pattern).count("}"):
        errs.append(fe("pattern", ec.CODERULE_UNBALANCED, "pattern: unbalanced braces"))
    return errs


def period(reset: str | None, at: datetime) -> str:
    """计数器周期键。

    Args:
        reset: 重置方式（never / daily / monthly / yearly）。
        at: 参考时间。

    Returns:
        周期字符串，如 ``2026-10``；never 为空串。
    """
    return {
        "daily": at.strftime("%Y%m%d"),
        "monthly": at.strftime("%Y%m"),
        "yearly": at.strftime("%Y"),
    }.get(reset or "never", "")


def b36(n: int, width: int) -> str:
    """把整数转换为指定宽度的 36 进制字符串（左补零）。"""
    s = ""
    while n:
        n, r = divmod(n, 36)
        s = B36[r] + s
    return (s or "0").rjust(width, "0")


def render(
    rule: dict[str, Any], seq: int, at: datetime, ctx: dict[str, Any] | None = None
) -> str:
    """按规则与序号渲染一个编码。

    Args:
        rule: 编码规则行。
        seq: 序号。
        at: 参考时间（日期占位符）。
        ctx: 上下文占位符值（如 LOT、SLOT）。
    """
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
                    raise MesError(
                        [
                            fe(
                                "seq",
                                ec.CODERULE_SEQ_OVERFLOW,
                                "sequence overflow for this period",
                            )
                        ]
                    )
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
    """预览接下来的 ``count`` 个编码（不占用计数器）。"""
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
    """占用并生成 ``count`` 个编码（行锁下原子递增计数器）。

    Args:
        session: 数据库会话。
        tenant_id: 租户 id。
        rule: 编码规则行。
        count: 数量。
        ctx: 上下文占位符值。
        commit: 是否提交事务。

    Returns:
        生成的编码列表。
    """
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
