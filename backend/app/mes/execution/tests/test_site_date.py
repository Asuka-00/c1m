"""D74 第 7 条：有效期类检查的「今天」按站点时区取（固定时钟，不依赖墙钟）。"""

import uuid
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlmodel import Session, text

from app.core.db import engine
from app.core.spec.engine import TABLES
from app.core.spec.excel import tenant_tz
from app.mes.common.query import find, one
from app.mes.common.sitedate import site_today
from app.mes.execution.checks.registry import CHECKS, Ctx
from app.mes.execution.tests.test_exec import Line

TPE = ZoneInfo("Asia/Taipei")
SITE_DAY = date(2026, 3, 10)
YESTERDAY = date(2026, 3, 9)
# 台北 00:30 / 07:59：UTC 日期还停在前一天
CLOCKS = [
    datetime(2026, 3, 10, 0, 30, tzinfo=TPE),
    datetime(2026, 3, 10, 7, 59, tzinfo=TPE),
]


def _session(tid: str) -> Session:
    s = Session(engine)
    s.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tid})
    return s


def _ctx(f: Line, s: Session, at: datetime, **kw: Any) -> Ctx:
    tid = uuid.UUID(str(f.m.tid))
    step = one(s, tid, "route_step", f.steps[10]["id"])
    op = one(s, tid, "operation", step["operation_id"])
    return Ctx(
        s=s,
        tid=tid,
        trigger="track_in",
        lot={},
        step=step,
        op=op,
        at=at.astimezone(ZoneInfo("UTC")),
        **kw,
    )


def test_site_today_fixed_clock(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    with _session(str(f.m.tid)) as s:
        tid = uuid.UUID(str(f.m.tid))
        assert tenant_tz(s, tid) == TPE
        for at in CLOCKS:
            assert at.astimezone(ZoneInfo("UTC")).date() == YESTERDAY
            assert site_today(s, tid, at) == SITE_DAY
            assert _ctx(f, s, at).today == SITE_DAY


@pytest.mark.parametrize("at", CLOCKS, ids=["0030", "0759"])
def test_operator_qualified_site_date(
    client: TestClient, db: Session, at: datetime
) -> None:
    f = Line(client, db)
    me = client.get("/api/v1/users/me", headers=f.m.h).json()
    user = me.get("username") or me["email"]
    q = f.m.post(
        "operator_qual",
        {
            "username": user,
            "operation_id": f.steps[10]["operation_id"],
            "expires_on": str(YESTERDAY),
        },
    )
    chk = CHECKS["operator_qualified"]
    with _session(str(f.m.tid)) as s:
        assert chk(_ctx(f, s, at, operator=user), {})[0] == "fail"  # 昨天过期：拦
    f.m.patch("operator_qual", q["id"], {"expires_on": str(SITE_DAY)})
    with _session(str(f.m.tid)) as s:
        assert chk(_ctx(f, s, at, operator=user), {})[0] == "pass"  # 今天到期：放行


@pytest.mark.parametrize("at", CLOCKS, ids=["0030", "0759"])
def test_equipment_qualified_until_site_date(
    client: TestClient, db: Session, at: datetime
) -> None:
    f = Line(client, db)
    t = TABLES["equipment_capability"]
    chk = CHECKS["eqp_capability"]
    for d, want in ((YESTERDAY, "fail"), (SITE_DAY, "pass")):
        with _session(str(f.m.tid)) as s:
            s.execute(
                sa.update(t)
                .where(t.c.equipment_id == f.eq["id"])
                .values(is_qualified=True, qualified_until=d)
            )
            s.commit()
        with _session(str(f.m.tid)) as s:
            tid = uuid.UUID(str(f.m.tid))
            eq = one(s, tid, "equipment", f.eq["id"])
            assert find(s, tid, "equipment_capability", equipment_id=eq["id"])
            assert chk(_ctx(f, s, at, equipment=eq), {})[0] == want, d


@pytest.mark.parametrize("at", CLOCKS, ids=["0030", "0759"])
def test_material_lot_mount_expiry_site_date(
    client: TestClient, db: Session, at: datetime
) -> None:
    from fastapi import HTTPException

    from app.mes.equipment.mount import _material_lot

    f = Line(client, db)
    for code, d in (("MLY", YESTERDAY), ("MLT", SITE_DAY)):
        f.m.post(
            "material_lot",
            {
                "code": code,
                "material_id": f.mat["id"],
                "qty_remaining": 10,
                "uom_id": f.m.fx("uom"),
                "expiry_date": str(d),
            },
        )
    utc = at.astimezone(ZoneInfo("UTC"))
    with _session(str(f.m.tid)) as s:
        tid = uuid.UUID(str(f.m.tid))
        with pytest.raises(HTTPException) as e:  # 昨天过期：拒绝上料
            _material_lot(s, tid, {"material_lot_code": "MLY"}, utc)
        assert e.value.status_code == 422 and "expired" in str(e.value.detail)
        assert _material_lot(s, tid, {"material_lot_code": "MLT"}, utc)["code"] == "MLT"
