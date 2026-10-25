"""演示数据编排（生成 / 清除），由各模块的 demo.py 组合而成。"""

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.core.spec.base import conn
from app.core.spec.engine import ENTITIES, TABLES
from app.core.spec.write import create_row, set_status
from app.platform.users.models import User

# each domain demo module appends its rows to DEMO at import: the import order
# below is the seeding order (dependencies first)
from app.mes.factory import demo as _factory  # noqa: F401  # isort: skip
from app.mes.product import demo as _product  # noqa: F401  # isort: skip
from app.mes.equipment import demo as _equipment  # noqa: F401  # isort: skip
from app.mes.process import demo as _process  # noqa: F401  # isort: skip
from app.mes.quality import demo as _quality  # noqa: F401  # isort: skip
from app.mes.lot import demo as _lot  # noqa: F401  # isort: skip
from app.mes.planning import demo as _planning  # noqa: F401  # isort: skip
from app.mes.execution import demo as _execution  # noqa: F401  # isort: skip
from app.mes.warehouse import demo as _warehouse  # noqa: F401  # isort: skip
from app.mes.common.demo import ACTIVATE, DEMO, _exists, _resolve, default_tenant
from app.mes.execution.demo import _post_demo, _run_exec
from app.mes.planning.demo import STARTS

DEMO_SUB = "[demo] "


def _demo_subscriptions(session: Session, tid: Any) -> None:
    """演示通知订阅：租户 admin / owner 角色订阅全部可订阅的 MES 事件（幂等）。"""
    import app.mes.equipment.events  # noqa: F401  （登记事件类型）
    import app.mes.execution.events  # noqa: F401
    from app.platform.notification.models import NotificationSubscription
    from app.platform.notification.service import event_types
    from app.platform.rbac.models import Role

    roles = session.exec(
        select(Role.id).where(
            Role.tenant_id == tid, col(Role.name).in_(("admin", "owner"))
        )
    ).all()
    have = set(
        session.exec(
            select(NotificationSubscription.event_type).where(
                NotificationSubscription.tenant_id == tid,
                col(NotificationSubscription.name).startswith(DEMO_SUB),
            )
        ).all()
    )
    for e in event_types():
        if e["code"].startswith("mes.") and not e["direct"] and e["code"] not in have:
            session.add(
                NotificationSubscription(
                    tenant_id=tid,
                    name=f"{DEMO_SUB}{e['code']}",
                    event_type=e["code"],
                    role_ids=[str(r) for r in roles],
                )
            )
    session.commit()


def seed(session: Session) -> int:
    """生成演示数据（先清除旧演示数据），按模块依赖顺序写入，最后运行执行示例。

    Args:
        session: 数据库会话。

    Returns:
        写入的行数。
    """
    tid = default_tenant(session)
    admin = session.exec(select(User).where(User.is_superuser)).first()
    _demo_subscriptions(session, tid)
    n = 0
    for ent, raw in DEMO:
        values: dict[str, Any] = {}
        for k, v in raw.items():
            if isinstance(v, tuple):
                rid = _resolve(session, tid, v)
                assert rid, f"{ent}.{k}: {v} not found"
                values[f"{k}_id"] = rid
                values.setdefault("_refs", {})[k] = rid
            else:
                values[k] = v
        refs = values.pop("_refs", {})
        if _exists(session, tid, ent, values, refs):
            continue
        values["attrs"] = {**(values.get("attrs") or {}), "_demo": True}
        create_row(session, tid, ENTITIES[ent], values, admin)
        n += 1
    for ref in ACTIVATE:
        rid = _resolve(session, tid, ref)
        row = (
            conn(session)
            .execute(
                sa.select(TABLES[ref[0]].c.status).where(TABLES[ref[0]].c.id == rid)
            )
            .scalar()
        )
        if row == "draft":
            set_status(session, tid, ENTITIES[ref[0]], rid, "active", admin)
    from app.mes.planning import service as wos

    for code, lots in STARTS:
        w = _resolve(session, tid, ("work_order", code))
        row = (
            conn(session)
            .execute(
                sa.select(TABLES["work_order"]).where(TABLES["work_order"].c.id == w)
            )
            .mappings()
            .first()
        )
        if not row or row["started_qty"]:
            continue
        if row["wo_status"] == "draft":
            wos.transition(session, tid, row["id"], "release", admin)
        wos.start(
            session,
            tid,
            row["id"],
            [
                {"qty": q, "carrier_id": c and _resolve(session, tid, ("carrier", c))}
                for q, c in lots
            ],
            admin,
            demo=True,
        )
    _run_exec(session, tid, admin)
    _post_demo(session, tid, admin)
    return n


def remove(session: Session) -> int:
    """删除所有带 ``attrs._demo`` 标记的行。

    按子表优先的顺序删除；遇外键冲突时多轮重试直至无进展。

    Returns:
        删除的行数。
    """
    tid = default_tenant(session)
    c = conn(session)
    total = 0
    pending = [e for e in ENTITIES.values() if e.code != "audit_log" and not e.internal]
    for _ in range(len(pending) + 1):
        progress = False
        for e in reversed(pending):
            t = TABLES[e.code]
            demo = sa.cast(t.c.attrs, JSONB)["_demo"].astext == "true"
            try:
                with c.begin_nested():
                    r = c.execute(sa.delete(t).where(t.c.tenant_id == tid, demo))
                total += r.rowcount
                progress = progress or r.rowcount > 0
            except IntegrityError:
                continue
        if not progress:
            break
    from app.platform.notification.models import NotificationSubscription

    conn(session).execute(
        sa.delete(NotificationSubscription).where(
            col(NotificationSubscription.tenant_id) == tid,
            col(NotificationSubscription.name).startswith(DEMO_SUB),
        )
    )
    session.commit()
    return total
