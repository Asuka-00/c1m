"""D19 停表点改到 Track In、D20 Q-Time Hold 附加字段。

编号对应 qa/test-plans/lot-state-machine-cases.md v0.7 §13.2：QT-02、QT-07~09、QF-01~03。
"""

import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlmodel import Session

from app.core.config import settings
from app.mes.execution.tests.test_exec import EXEC, Line

QF = (
    "qtime_rule_id",
    "qtime_from_step_id",
    "qtime_to_step_id",
    "qtime_overdue_seconds",
    "qtime_from_step_name",
    "qtime_to_step_name",
)


def _setup(client: TestClient, db: Session) -> tuple[Line, Any]:
    f = Line(client, db)
    rule = f.m.post(
        "qtime_rule",
        {
            "code": "QT",
            "name": "q",
            "route_id": f.route["id"],
            "from_step_id": f.steps[10]["id"],
            "to_step_id": f.steps[20]["id"],
            "max_minutes": 30,
        },
    )
    f.sql("UPDATE mes_qtime_rule SET reason_id=NULL WHERE id=:i", i=rule["id"])
    return f, rule


def _expire(f: Line, lot: Any) -> None:
    f.sql(
        "UPDATE mes_lot_history SET at = at - interval '2 hours' "
        "WHERE lot_id = :l AND action = 'move_out'",
        l=lot["id"],
    )


def _eq(f: Line) -> dict[str, Any]:
    return {"equipment_id": f.eq["id"]}


def _list(f: Line, lot: Any) -> list[Any]:
    r = f.c.get(f"{EXEC}/holds?include_terminal=true", headers=f.m.h)
    assert r.status_code == 200, r.text
    return [h for h in r.json()["data"] if h["lot_id"] == lot["id"]]


def _detail(f: Line, hid: str, status: int = 200) -> Any:
    r = f.c.get(f"{EXEC}/holds/{hid}", headers=f.m.h)
    assert r.status_code == status, r.text
    return r.json()


def _assert_qf(f: Line, h: Any, rule: Any) -> None:
    """QF-01：四字段 + 两个只读名称；列表与详情一致。"""
    assert h["qtime_rule_id"] == rule["id"]
    assert h["qtime_from_step_id"] == f.steps[10]["id"]
    assert h["qtime_to_step_id"] == f.steps[20]["id"]
    # 超时 2h - 上限 30min ≈ 5400s
    assert 5300 < h["qtime_overdue_seconds"] < 5600
    assert h["qtime_from_step_name"].startswith("10")
    assert h["qtime_to_step_name"].startswith("20")
    d = _detail(f, h["id"])
    assert {k: d[k] for k in QF} == {k: h[k] for k in QF}
    assert d.keys() == h.keys()


def test_qt_02_moved_in_overdue_sweep_holds_and_track_in_rejected(
    client: TestClient, db: Session
) -> None:
    """QT-02：moved_in 超时 → sweep 后 Hold(qtime_expired, qtime)，Track In 422 on_hold。"""
    f, rule = _setup(client, db)
    (lot,) = f.start(1)
    f.run_step(lot)
    f.stage(lot, "move_in", **_eq(f))
    _expire(f, lot)
    r = f.post(f"{EXEC}/qtime/sweep", {})
    assert {"lot": lot["code"], "action": "hold"} in r["actions"]
    got = f.lot(lot)
    assert got["lot_status"] == "moved_in" and got["on_hold"]
    (h,) = _list(f, lot)
    assert h["source"] == "qtime" and h["reason"] == "qtime_expired"
    _assert_qf(f, h, rule)
    d = f.stage(lot, "track_in", 422, **_eq(f))["detail"]
    assert d["code"] == "on_hold"
    assert len(_list(f, lot)) == 1  # 不重复挂


def test_qt_07_track_in_overdue_rejected_and_held(
    client: TestClient, db: Session
) -> None:
    """QT-07（D22）：已超时未 Hold 的 moved_in 批次 Track In → 转 Hold、200 带 qtime=hold；再 Track In 422 on_hold。"""
    f, rule = _setup(client, db)
    (lot,) = f.start(1)
    f.run_step(lot)
    f.stage(lot, "move_in", **_eq(f))
    _expire(f, lot)
    r = f.stage(lot, "track_in", **_eq(f))  # D22：转 Hold 并提交，200，未进站
    assert r["qtime"] == "hold" and r["lot"]["on_hold"]
    assert r["lot"]["lot_status"] == "moved_in"
    got = f.lot(lot)
    assert got["lot_status"] == "moved_in" and got["on_hold"]
    (h,) = _list(f, lot)
    assert h["source"] == "qtime" and h["hold_type"] == "auto"
    _assert_qf(f, h, rule)
    d = f.stage(lot, "track_in", 422, **_eq(f))["detail"]
    assert d["code"] == "on_hold" and d["lot_code"] == lot["code"]
    assert len(_list(f, lot)) == 1


@pytest.mark.parametrize("stage", ["running", "tracked_out"])
def test_qt_08_after_track_in_no_hold(
    client: TestClient, db: Session, stage: str
) -> None:
    """QT-08：Track In 后（running / tracked_out）超时 → 不 Hold，sweep 不处理。"""
    f, _ = _setup(client, db)
    (lot,) = f.start(1)
    f.run_step(lot)
    f.stage(lot, "move_in", **_eq(f))
    f.stage(lot, "track_in", **_eq(f))
    if stage == "tracked_out":
        f.stage(lot, "track_out")
    _expire(f, lot)
    r = f.post(f"{EXEC}/qtime/sweep", {})
    assert all(a["lot"] != lot["code"] for a in r["actions"])
    got = f.lot(lot)
    assert got["lot_status"] == stage and not got["on_hold"]
    if stage == "running":
        f.stage(lot, "track_out")
    f.stage(lot, "move_out")
    assert not _list(f, lot)


def test_qt_09_move_in_does_not_stop_clock(client: TestClient, db: Session) -> None:
    """QT-09：Move In 不停表、不处置；waiting→moved_in 后计时继续（监控仍显示）。"""
    f, _ = _setup(client, db)
    (lot,) = f.start(1)
    f.run_step(lot)
    _expire(f, lot)
    r = f.stage(lot, "move_in", **_eq(f))
    assert "qtime" not in r or not r.get("qtime")
    got = f.lot(lot)
    assert got["lot_status"] == "moved_in" and not got["on_hold"]
    mon = f.c.get(f"{EXEC}/qtime/monitor", headers=f.m.h).json()["data"]
    (x,) = [m for m in mon if m["lot"] == lot["code"]]
    assert x["exceeded"] and x["minutes"] > 100


def test_qf_02_manual_and_legacy_holds_fields_null(
    client: TestClient, db: Session
) -> None:
    """QF-02：手动 Hold 与旧记录（列为空）六个字段为 null，列表 / 详情正常。"""
    f, _ = _setup(client, db)
    a, b = f.start(1, 1)
    f.post(f"{EXEC}/lots/{a['id']}/hold", {"reason_id": f.reasons["hold"]["id"]})
    # 旧记录：迁移前写入的 qtime Hold，附加列为空
    f.post(f"{EXEC}/lots/{b['id']}/hold", {"reason_id": f.reasons["hold"]["id"]})
    f.sql(
        "UPDATE mes_lot_hold SET source='qtime', hold_type='auto' WHERE lot_id=:l",
        l=b["id"],
    )
    for lot in (a, b):
        (h,) = _list(f, lot)
        assert all(h[k] is None for k in QF), h
        d = _detail(f, h["id"])
        assert all(d[k] is None for k in QF) and d["lot"] == lot["code"]
    _detail(f, str(uuid.uuid4()), 404)


# ---------------- QF-03 迁移可重复执行、可回滚 ----------------
COLS = {
    "qtime_rule_id",
    "qtime_from_step_id",
    "qtime_to_step_id",
    "qtime_overdue_seconds",
}


def _alembic(url: str, *args: str) -> None:
    env = {**os.environ, "MIGRATION_DATABASE_URL": url}
    backend = Path(__file__).resolve().parents[4]
    r = subprocess.run(
        ["alembic", *args], cwd=backend, env=env, capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr[-2000:]


def test_qf_03_migration_rerunnable_and_reversible() -> None:
    """QF-03：0009 升级 / 降级都可重复执行；降级删除四列，升级恢复。"""
    base = make_url(settings.migration_database_url)
    name = f"{base.database}_mig_qf03"
    server = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with server.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = base.set(database=name).render_as_string(hide_password=False)
    eng = create_engine(url)

    def cols() -> set[str]:
        with eng.connect() as c:
            return {x["name"] for x in inspect(c).get_columns("mes_lot_hold")} & COLS

    try:
        _alembic(url, "upgrade", "head")
        assert cols() == COLS
        _alembic(url, "stamp", "0008_system_reason_codes")
        _alembic(url, "upgrade", "head")  # 列已存在时再升级：不报错
        assert cols() == COLS
        _alembic(url, "downgrade", "0008_system_reason_codes")
        assert cols() == set()
        _alembic(url, "stamp", "head")
        _alembic(url, "downgrade", "0008_system_reason_codes")  # 列已不在时再降级
        assert cols() == set()
        _alembic(url, "upgrade", "head")
        assert cols() == COLS
    finally:
        eng.dispose()
        with server.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        server.dispose()
