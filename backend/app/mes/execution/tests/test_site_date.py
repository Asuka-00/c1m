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


# ---------------- D75 补充：固定时钟扩展 ----------------
def _fixed(monkeypatch: pytest.MonkeyPatch, at: datetime, *mods: Any) -> None:
    """让模块里的 ``site_today`` 一律按固定时钟 ``at`` 取站点日期。"""
    from app.mes.common import sitedate

    real = sitedate.site_today

    def fake(s: Session, tid: uuid.UUID, _when: datetime | None = None) -> date:
        return real(s, tid, at)

    for m in mods:
        monkeypatch.setattr(m, "site_today", fake)


@pytest.mark.parametrize("at", CLOCKS, ids=["0030", "0759"])
def test_tool_life_expiry_site_date(
    client: TestClient, db: Session, at: datetime
) -> None:
    from app.mes.equipment.status import tool_block

    f = Line(client, db)
    t = f.m.post("tool", {"code": "T", "fixture_id": f.fixture["id"]})
    with _session(str(f.m.tid)) as s:
        tid = uuid.UUID(str(f.m.tid))
        today = _ctx(f, s, at).today
        row = one(s, tid, "tool", t["id"])
        assert row
        for d, blocked in ((YESTERDAY, True), (SITE_DAY, False)):
            tool = {**row, "expiry_date": d}
            r = tool_block(s, tid, tool, today)
            assert (r is not None and "expired" in r) == blocked, (d, r)


@pytest.mark.parametrize("at", CLOCKS, ids=["0030", "0759"])
def test_qual_notify_site_date(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch, at: datetime
) -> None:
    from app.mes.execution import qual
    from app.platform.notification.tests.test_notification import _sub_all, _types

    _fixed(monkeypatch, at, qual)
    f = Line(client, db)
    _sub_all(f)
    me = client.get("/api/v1/users/me", headers=f.m.h).json()
    user = me.get("username") or me["email"]
    ops = [x["id"] for x in f.ops[:2]]
    for op, d in zip(ops, (YESTERDAY, SITE_DAY), strict=True):
        f.m.post(
            "operator_qual",
            {"username": user, "operation_id": op, "expires_on": str(d)},
        )
    with _session(str(f.m.tid)) as s:
        assert qual.qual_notify(s, uuid.UUID(str(f.m.tid))) == 2
        s.commit()
    t = _types(f)
    # 昨天到期：已过期；今天到期：仍是「即将到期」（UTC 日期还是前一天也不影响）
    assert t.count("mes.qual_expired") == 1 and t.count("mes.qual_expiring") == 1


@pytest.mark.parametrize("at", CLOCKS, ids=["0030", "0759"])
def test_fefo_candidates_site_date(
    client: TestClient, db: Session, at: datetime
) -> None:
    from app.mes.execution.consumption import candidate_lots

    f = Line(client, db)
    for code, d in (("FY", YESTERDAY), ("FT", SITE_DAY)):
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
        got = candidate_lots(s, uuid.UUID(str(f.m.tid)), f.mat["id"], utc)
    assert [m["code"] for m in got] == ["FT"]  # 昨天过期排除，今天到期可用


@pytest.mark.parametrize("at", CLOCKS, ids=["0030", "0759"])
def test_track_out_marks_tool_expired_site_date(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch, at: datetime
) -> None:
    from app.mes.execution import track_out

    f = Line(client, db)
    m = f.m
    f.sql(
        "INSERT INTO mes_step_resource (id, tenant_id, route_step_id, resource_kind, "
        "fixture_id) VALUES (gen_random_uuid(), :t, :s, 'fixture', :f)",
        t=m.tid,
        s=f.steps[10]["id"],
        f=f.fixture["id"],
    )
    tools = [m.post("tool", {"code": c, "fixture_id": f.fixture["id"]}) for c in "YT"]
    lots = f.start(1, 1)
    for lot, tl in zip(lots, tools, strict=True):
        f.stage(lot, "move_in", equipment_id=f.eq["id"])
        f.stage(lot, "track_in", equipment_id=f.eq["id"], tool_ids=[tl["id"]])
    for tl, d in zip(tools, (YESTERDAY, SITE_DAY), strict=True):
        f.sql("UPDATE mes_tool SET expiry_date = :d WHERE id = :i", d=d, i=tl["id"])
    _fixed(monkeypatch, at, track_out)
    got = [f.stage(lot, "track_out")["tools"][0]["status"] for lot in lots]
    assert got == ["expired", "available"]  # 昨天过期置 expired；今天到期仍可用
    assert [m.list("tool", q=c)["data"][0]["tool_status"] for c in "YT"] == got
