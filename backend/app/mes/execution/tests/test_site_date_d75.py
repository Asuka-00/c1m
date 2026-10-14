"""D75 补充：交期风险、首页今日出站、报表区间按站点时区（固定时钟台北 00:30 / 07:59）。"""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.common import sitedate
from app.mes.common.sitedate import site_day_bounds
from app.mes.execution import dispatch
from app.mes.execution.tests.test_exec import Line
from app.mes.execution.tests.test_site_date import _session
from app.mes.planning import board

TPE = ZoneInfo("Asia/Taipei")
SITE_DAY = date(2026, 3, 10)
CLOCKS = [
    datetime(2026, 3, 10, 0, 30, tzinfo=TPE),
    datetime(2026, 3, 10, 7, 59, tzinfo=TPE),
]
IDS = ["0030", "0759"]


def _fix(monkeypatch: pytest.MonkeyPatch, at: datetime, *mods: Any) -> None:
    real = sitedate.site_today

    def fake(s: Session, tid: uuid.UUID, when: datetime | None = None) -> date:
        return real(s, tid, when or at)

    for m in mods:
        monkeypatch.setattr(m, "site_today", fake)


def test_site_day_bounds(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    with _session(str(f.m.tid)) as s:
        a, b = site_day_bounds(s, uuid.UUID(str(f.m.tid)), SITE_DAY)
    assert a == datetime(2026, 3, 9, 16, 0, tzinfo=UTC)
    assert b == datetime(2026, 3, 10, 16, 0, tzinfo=UTC)


@pytest.mark.parametrize("at", CLOCKS, ids=IDS)
def test_wo_board_due_site_date(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch, at: datetime
) -> None:
    _fix(monkeypatch, at, board)
    f = Line(client, db)
    (a,) = f.start(2)
    wo = f.lot(a)["work_order_id"]
    tid = uuid.UUID(str(f.m.tid))

    def row(due: date) -> Any:
        f.sql("UPDATE mes_work_order SET due_date = :d WHERE id = :w", d=due, w=wo)
        with _session(str(f.m.tid)) as s:
            return next(x for x in board.wo_board(s, tid) if x["id"] == wo)

    # UTC 日期仍是 3/9：按 UTC 算，今天到期会被当成「还剩 1 天」
    r = row(SITE_DAY)
    assert r["days_left"] == 0 and r["risk"] == "at_risk"
    r = row(SITE_DAY - timedelta(days=1))
    assert r["days_left"] == -1 and r["risk"] == "overdue"


@pytest.mark.parametrize("at", CLOCKS, ids=IDS)
def test_home_track_outs_today_site_day(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch, at: datetime
) -> None:
    _fix(monkeypatch, at, dispatch)
    f = Line(client, db)
    a, b, c = f.start(1, 1, 1)
    for lot in (a, b, c):
        f.run_step(lot)
    tid = uuid.UUID(str(f.m.tid))
    times = {
        a["id"]: datetime(2026, 3, 10, 0, 0, tzinfo=TPE),  # 当日 00:00 计入
        b["id"]: datetime(2026, 3, 9, 23, 59, tzinfo=TPE),  # 前一日不计
        c["id"]: datetime(2026, 3, 11, 0, 0, tzinfo=TPE),  # 次日 00:00 不计（半开）
    }
    for lid, t in times.items():
        f.sql(
            "UPDATE mes_lot_history SET at = :t WHERE lot_id = :l "
            "AND action = 'track_out'",
            t=t,
            l=lid,
        )
    with _session(str(f.m.tid)) as s:
        assert dispatch.home(s, tid)["track_outs_today"] == 1
