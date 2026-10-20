"""Q-Time 超时转 Hold（D12）、自动 Hold 跳过（D17）、系统原因码（D18）。

编号对应 qa/test-plans/lot-state-machine-cases.md v0.6.1 §13 / §13.1。
"""

import logging
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from app.core import error_codes as ec
from app.core.db import admin_engine, engine
from app.mes.execution import qtime_actions as qa
from app.mes.execution.tests.test_exec import EXEC, Line
from app.mes.lot.service import lock_lot

QX = {"minutes": 120.0}


def _session(tid: str) -> Session:
    s = Session(engine)
    s.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tid})
    return s


def _rule(f: Line, **kw: Any) -> Any:
    return f.m.post(
        "qtime_rule",
        {
            "code": f"QT{uuid.uuid4().hex[:4]}",
            "name": "q",
            "route_id": f.route["id"],
            "from_step_id": f.steps[10]["id"],
            "to_step_id": f.steps[20]["id"],
            "max_minutes": 30,
            **kw,
        },
    )


def _expire(f: Line, lot: Any) -> None:
    f.sql(
        "UPDATE mes_lot_history SET at = at - interval '2 hours' "
        "WHERE lot_id = :l AND action = 'move_out'",
        l=lot["id"],
    )


def _holds(f: Line, lot: Any) -> list[Any]:
    return [h for h in f.m.list("lot_hold", lot=lot["id"])["data"] if h["is_active"]]


def _qe(f: Line) -> Any:
    rs = f.m.list("reason_code", code="qtime_expired")["data"]
    return next(r for r in rs if r["code"] == "qtime_expired")


def _direct_hold(f: Line, lot: Any) -> Any:
    """直接调用超时转 Hold 处置（QT-02/03/AH：直接调用处置，覆盖任意状态）。"""
    tid = uuid.UUID(f.m.tid)
    q = _rule(
        f, reason_id=f.reasons["hold"]["id"]
    )  # D20：Hold 记录引用真实规则（外键）
    r = {
        "id": uuid.UUID(q["id"]),
        "code": q["code"],
        "max_minutes": 30,
        "reason_id": None,
        "from_step_id": uuid.UUID(q["from_step_id"]),
        "to_step_id": uuid.UUID(q["to_step_id"]),
        "action": "hold",
    }
    with _session(f.m.tid) as s:
        row = lock_lot(s, tid, uuid.UUID(lot["id"]))
        got = qa.qtime_hold(s, tid, row, None, r, QX, {"rule": "QT"})
        s.commit()
    return got


def test_qt_01_sweep_waiting_overdue_holds_with_qtime_expired(
    client: TestClient, db: Session
) -> None:
    """QT-01：waiting 超时（hold 规则、无原因码，D25/D26）→ 不报废，Hold(qtime, qtime_expired)。"""
    f = Line(client, db)
    _rule(f, action="hold", reason_id=None)
    (lot,) = f.start(2)
    f.run_step(lot)
    _expire(f, lot)
    r = f.post(f"{EXEC}/qtime/sweep", {})
    assert r["actions"] == [{"lot": lot["code"], "action": "hold"}]
    got = f.lot(lot)
    assert got["lot_status"] == "waiting" and got["on_hold"] and got["qty"] == 2
    (h,) = _holds(f, lot)
    assert h["source"] == "qtime" and h["reason_id"] == _qe(f)["id"]
    hist = [x["action"] for x in f.m.list("lot_history", lot=lot["id"])["data"]]
    assert "scrap" not in hist


@pytest.mark.parametrize("stage", ["moved_in", "running", "tracked_out"])
def test_qt_02_03_ah_02_in_process_lots_auto_held(
    client: TestClient, db: Session, stage: str
) -> None:
    """QT-02 / QT-03 / AH-02：在制批次超时处置 → Hold；running 仍可 Track Out，Move Out 422 on_hold。"""
    f = Line(client, db)
    (lot,) = f.start(1)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    if stage != "moved_in":
        f.stage(lot, "track_in", equipment_id=f.eq["id"])
    if stage == "tracked_out":
        f.stage(lot, "track_out")
    assert _direct_hold(f, lot)
    (h,) = _holds(f, lot)
    assert h["source"] == "qtime" and h["reason_id"] == _qe(f)["id"]
    assert f.lot(lot)["lot_status"] == stage
    if stage == "running":
        f.stage(lot, "track_out")  # B1
        stage = "tracked_out"
    if stage == "tracked_out":
        d = f.stage(lot, "move_out", 422)["detail"]
        assert d["code"] == ec.ON_HOLD  # D2


def test_qt_04_held_lot_overdue_again_stacks_hold(
    client: TestClient, db: Session
) -> None:
    """QT-04：已持 Hold 的 waiting 批次再超时 → 叠加一条 qtime Hold，不报错。"""
    f = Line(client, db)
    _rule(f)
    (lot,) = f.start(1)
    f.run_step(lot)
    f.post(f"{EXEC}/lots/{lot['id']}/hold", {"reason_id": f.reasons["hold"]["id"]})
    _expire(f, lot)
    r = f.post(f"{EXEC}/qtime/sweep", {})
    assert {"lot": lot["code"], "action": "hold"} in r["actions"]
    hs = _holds(f, lot)
    assert len(hs) == 2 and {h["source"] for h in hs} == {"manual", "qtime"}
    f.post(f"{EXEC}/qtime/sweep", {})  # 同一次超时不重复处置
    assert len(_holds(f, lot)) == 2


@pytest.mark.parametrize("status", ["completed", "stored", "scrapped", "merged"])
def test_ah_01_qt_05_terminal_lot_auto_hold_skipped(
    client: TestClient, db: Session, status: str, caplog: pytest.LogCaptureFixture
) -> None:
    """AH-01 / QT-05（D17）：终态批次自动 Hold → 跳过：不报错、无 Hold、无历史，记一行日志。"""
    f = Line(client, db)
    (lot,) = f.start(1)
    f.sql("UPDATE mes_lot SET lot_status=:s WHERE id=:i", s=status, i=lot["id"])
    n0 = f.m.list("lot_history", lot=lot["id"])["count"]
    with caplog.at_level(logging.WARNING, logger="app.mes.execution.hold"):
        assert _direct_hold(f, lot) is None
    assert not _holds(f, lot) and not f.lot(lot)["on_hold"]
    assert f.m.list("lot_history", lot=lot["id"])["count"] == n0
    recs = [r for r in caplog.records if "skip" in r.getMessage()]
    assert len(recs) == 1 and lot["code"] in recs[0].getMessage()


def test_ah_01_completed_skips_auto_but_manual_allowed(
    client: TestClient, db: Session
) -> None:
    """「completed 批次被自动 Hold 时跳过不挂」+ AH-03（手动仍允许）。"""
    f = Line(client, db)
    (lot,) = f.start(1)
    f.sql("UPDATE mes_lot SET lot_status='completed' WHERE id=:i", i=lot["id"])
    assert _direct_hold(f, lot) is None and not _holds(f, lot)
    f.post(f"{EXEC}/lots/{lot['id']}/hold", {"reason_id": f.reasons["hold"]["id"]})
    assert len(_holds(f, lot)) == 1


def test_h2_01_completed_hold_release(client: TestClient, db: Session) -> None:
    """H2-01：completed 手动 Hold 后 release → on_hold=F，状态仍 completed。"""
    f = Line(client, db)
    (lot,) = f.start(1)
    f.sql("UPDATE mes_lot SET lot_status='completed' WHERE id=:i", i=lot["id"])
    f.post(f"{EXEC}/lots/{lot['id']}/hold", {"reason_id": f.reasons["hold"]["id"]})
    (h,) = _holds(f, lot)
    r = f.post(
        f"{EXEC}/holds/{h['id']}/release", {"reason_id": f.reasons["release"]["id"]}
    )
    assert not r["on_hold"] and f.lot(lot)["lot_status"] == "completed"


def test_rw_02_rework_with_route_unchanged(client: TestClient, db: Session) -> None:
    """RW-02：工步有返工路线时 move_out(rework) 行为不变。"""
    f = Line(client, db, {20: {"rework_return": "same_step"}})
    (lot,) = f.start(1)
    f.run_step(lot)  # -> 20（有返工路线）
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_out")
    f.stage(lot, "move_out", rework=True)
    got = f.lot(lot)
    assert got["lot_status"] == "waiting" and got["rework_count"] == 1
    assert f.ctx(lot)["step"]["route"].startswith("RW")


# ---------------- D18 系统原因码 ----------------
def _count_qe(tid: str) -> int:
    with admin_engine.connect() as c:
        return int(
            c.execute(
                text(
                    "SELECT count(*) FROM mes_reason_code WHERE tenant_id=:t "
                    "AND code='qtime_expired' AND reason_type='hold'"
                ),
                {"t": tid},
            ).scalar_one()
        )


def _migrate_sql() -> str:
    import importlib.util
    from pathlib import Path

    import app

    p = Path(app.__file__).parent / "alembic/versions/0008_system_reason_codes.py"
    spec = importlib.util.spec_from_file_location("m0008", p)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return str(mod.SQL)


def test_rc_02_new_tenant_has_qtime_expired(client: TestClient, db: Session) -> None:
    """RC-02：新租户初始化自动创建 qtime_expired（hold）。"""
    f = Line(client, db)
    assert _count_qe(f.m.tid) == 1
    assert _qe(f)["is_active"]


def test_rc_01_rc_04_migration_backfills_idempotently(
    client: TestClient, db: Session
) -> None:
    """RC-01：迁移为缺失的现有租户补建；RC-04：重复执行不插重复记录。"""
    f = Line(client, db)
    with admin_engine.begin() as c:
        c.execute(
            text(
                "DELETE FROM mes_reason_code WHERE tenant_id=:t AND code='qtime_expired'"
            ),
            {"t": f.m.tid},
        )
    assert _count_qe(f.m.tid) == 0
    sql = _migrate_sql()
    for _ in range(2):
        with admin_engine.begin() as c:
            c.execute(text(sql))
        assert _count_qe(f.m.tid) == 1


def test_rc_03_missing_reason_falls_back_to_default(
    client: TestClient, db: Session
) -> None:
    """RC-03：qtime_expired 缺失时回退默认 hold 原因。"""
    f = Line(client, db)
    with admin_engine.begin() as c:
        c.execute(
            text(
                "DELETE FROM mes_reason_code WHERE tenant_id=:t AND code='qtime_expired'"
            ),
            {"t": f.m.tid},
        )
    (lot,) = f.start(1)
    assert _direct_hold(f, lot)
    (h,) = _holds(f, lot)
    assert h["reason_id"] == f.reasons["hold"]["id"]
