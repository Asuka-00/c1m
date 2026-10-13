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
    d = _detail(f, str(uuid.uuid4()), 404)["detail"]
    assert d["code"] == "hold_not_found" and d["message"]


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


def test_rw_03_moved_in_rework_clears_move_in_binding(
    client: TestClient, db: Session
) -> None:
    """RW-03：moved_in 批次 Q-Time rework 处置 → 返工路线上 waiting，不残留设备等进站字段。"""
    f, rule = _setup(client, db)
    f.m.patch("qtime_rule", rule["id"], {"action": "rework"})
    (lot,) = f.start(2)
    f.run_step(lot)
    f.stage(lot, "move_in", **_eq(f))
    assert f.lot(lot)["equipment_id"] == f.eq["id"]
    _expire(f, lot)
    r = f.stage(lot, "track_in", **_eq(f))
    assert r["qtime"] == "rework"
    cx = f.ctx(lot)
    got = cx["lot"]
    assert got["lot_status"] == "waiting" and not got["on_hold"]
    assert cx["step"]["route"].startswith("RW")
    for k in ("equipment_id", "recipe_id", "exec_ctx"):
        assert not got[k], k
    ws = f.m.list("wafer", lot=lot["id"])["data"]
    assert ws and all(w["wafer_status"] != "processing" for w in ws)
    hist = f.m.list("lot_history", lot=lot["id"], action="qtime")["data"]
    assert hist and hist[0]["details"]["action"] == "rework"
    assert got["stage_at"]
    # 返工路线首站可正常 Move In
    f.stage(lot, "move_in", **_eq(f))
    assert f.lot(lot)["lot_status"] == "moved_in"


# ---------------- D23 / D24 ----------------
def _m0010() -> Any:
    import importlib.util

    import app

    p = Path(app.__file__).parent / "alembic/versions/0010_qtime_control_track_in.py"
    spec = importlib.util.spec_from_file_location("m0010", p)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(qs: list[str]) -> None:
    from app.core.db import admin_engine

    with admin_engine.begin() as c:
        for q in qs:
            c.execute(text(q))


def _bindings(f: Line) -> list[Any]:
    from app.core.db import admin_engine

    with admin_engine.connect() as c:
        return [
            dict(r._mapping)
            for r in c.execute(
                text(
                    "SELECT b.trigger, b.attrs, b.check_plan_id, "
                    "(SELECT array_agg(r.check_type ORDER BY r.check_type) "
                    " FROM mes_check_plan_item i JOIN mes_check_rule r "
                    " ON r.id=i.check_rule_id WHERE i.check_plan_id=b.check_plan_id) AS types "
                    "FROM mes_check_binding b WHERE b.tenant_id=:t ORDER BY b.trigger"
                ),
                {"t": f.m.tid},
            )
        ]


def test_qs_01_qtime_control_moved_to_track_in(client: TestClient, db: Session) -> None:
    """QS-01（D23）：Move In 时机的 qtime 严重度平移到 Track In（重复执行不重复），
    Move In 不处置，Track In 按配置处置，downgrade 恢复原配置。"""
    f, _ = _setup(client, db)
    f.bind("move_in", ("qtime", "off", {}), ("lot_hold", "block", {}))
    before = _bindings(f)
    assert [b["trigger"] for b in before] == ["move_in"]
    mod = _m0010()
    _run(mod.UPGRADE)
    _run(mod.UPGRADE)  # 重复执行
    bs = _bindings(f)
    ti = [b for b in bs if b["trigger"] == "track_in"]
    assert len(ti) == 1 and ti[0]["types"] == ["qtime"]
    assert [b for b in bs if b["trigger"] == "move_in"] == before
    # 严重度 off：Move In、Track In 都不处置
    a, b = f.start(1, 1)
    for x in (a, b):
        f.run_step(x)
        f.stage(x, "move_in", **_eq(f))  # Move In 不读 qtime
    _expire(f, a)
    _expire(f, b)
    r = f.stage(a, "track_in", **_eq(f))
    assert not r.get("qtime") and f.lot(a)["lot_status"] == "running"
    # 改为 block：Track In 按配置处置（转 Hold）
    rule = next(x for x in f.m.list("check_rule")["data"] if x["check_type"] == "qtime")
    f.m.patch("check_rule", rule["id"], {"severity": "block"})
    assert f.stage(b, "track_in", **_eq(f))["qtime"] == "hold"
    # Move In 时机 block 也不再拦超时批次
    (c,) = f.start(1)
    f.run_step(c)
    _expire(f, c)
    f.stage(c, "move_in", **_eq(f))
    assert not f.lot(c)["on_hold"]
    _run(mod.DOWNGRADE)
    _run(mod.DOWNGRADE)
    after = _bindings(f)
    assert [x["trigger"] for x in after] == ["move_in"]
    assert after[0]["check_plan_id"] == before[0]["check_plan_id"]
    assert after[0]["types"] == before[0]["types"]


def test_qr_01_delete_referenced_qtime_rule_409(
    client: TestClient, db: Session
) -> None:
    """QR-01（D24）：删除被 Hold 引用的 Q-Time 规则 → 409 qtime_rule_in_use；停用可以。"""
    f, rule = _setup(client, db)
    (lot,) = f.start(1)
    f.run_step(lot)
    _expire(f, lot)
    f.post(f"{EXEC}/qtime/sweep", {})
    (h,) = _list(f, lot)
    r = f.c.delete(f.m.url("qtime_rule", rule["id"]), headers=f.m.h)
    assert r.status_code == 409, r.text
    d = r.json()["detail"]
    assert d["code"] == "qtime_rule_in_use" and d["qtime_rule_id"] == rule["id"]
    assert d["message"] and d["hold_count"] == 1
    assert _detail(f, h["id"])["qtime_rule_id"] == rule["id"]
    got = f.m.list("qtime_rule", code=rule["code"])["data"]
    assert [x["id"] for x in got] == [rule["id"]]
    f.m.patch(  # 停用成功（规则 action=hold 校验要求原因码）
        "qtime_rule",
        rule["id"],
        {"is_active": False, "reason_id": f.reasons["hold"]["id"]},
    )
    # 未被引用的规则仍可删除
    other = f.m.post(
        "qtime_rule",
        {
            "code": "QT2",
            "name": "q2",
            "route_id": f.route["id"],
            "from_step_id": f.steps[20]["id"],
            "to_step_id": f.steps[40]["id"] if 40 in f.steps else f.steps[30]["id"],
            "max_minutes": 30,
        },
    )
    f.m.delete("qtime_rule", other["id"])
