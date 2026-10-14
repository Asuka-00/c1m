"""操作员资质到期提醒。"""

import uuid
from datetime import date, timedelta

from sqlmodel import Session

from app.mes.common.query import find, one
from app.mes.common.sitedate import site_today
from app.mes.common.switch import switch
from app.mes.execution.events import QUAL_EXPIRED, QUAL_EXPIRING
from app.mes.execution.operator_qual import warn_days
from app.platform.notification.service import notify


def qual_notify(s: Session, tid: uuid.UUID, today: date | None = None) -> int:
    """资质即将到期 / 已过期各通知一次（按资质与有效期去重），返回发送数。

    由「资质到期提醒」检查规则开关（严重度 off 关闭）；预警天数取
    :func:`app.mes.execution.operator_qual.warn_days`（唯一来源，默认 30，D74）。
    """
    sw = switch(s, tid, "qual_expiry_notice")
    if sw is None:
        return 0
    today = today or site_today(s, tid)
    edge = today + timedelta(days=warn_days(s, tid))
    n = 0
    for q in find(s, tid, "operator_qual", is_active=True):
        exp = q["expires_on"]
        if not exp or exp > edge:
            continue
        ev = QUAL_EXPIRED if exp < today else QUAL_EXPIRING
        op = one(s, tid, "operation", q["operation_id"])
        code = op["code"] if op else "?"
        n += bool(
            notify(
                s,
                tid,
                ev,
                title=f"Qualification of {q['username']} for {code} "
                + ("expired" if exp < today else "expires")
                + f" on {exp}",
                params={"user": q["username"], "operation": code, "date": str(exp)},
                object_type="operator_qual",
                object_id=q["id"],
                object_code=q["username"],
                link="/mes/operator-qual",
                dedupe_key=f"{ev}:{q['id']}:{exp}",
            )
        )
    return n
