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
    env = {
        **os.environ,
        "MIGRATION_DATABASE_URL": url,
        "ALEMBIC_ALLOW_DB_MISMATCH": "1",
    }
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
    au = [
        a
        for a in f.m.list("audit_log", action="qtime_rework", page_size=100)["data"]
        if str(a.get("record_id")) == lot["id"]
    ]
    assert len(au) == 1, au
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
    got = f.m.patch("qtime_rule", rule["id"], {"is_active": False})  # 停用成功
    assert got["is_active"] is False
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


# ---------------- D25 ----------------
def _rule_body(f: Line, **kw: Any) -> dict[str, Any]:
    return {
        "code": f"Q{uuid.uuid4().hex[:5]}",
        "name": "q",
        "route_id": f.route["id"],
        "from_step_id": f.steps[10]["id"],
        "to_step_id": f.steps[20]["id"],
        "max_minutes": 30,
        "action": "hold",
        **kw,
    }


def test_d25_hold_rule_without_reason(client: TestClient, db: Session) -> None:
    """D25：无原因码的 hold 规则可新建、修改、停用；超时 Hold 用 qtime_expired。"""
    f = Line(client, db)
    rule = f.m.post("qtime_rule", _rule_body(f, reason_id=None))
    assert rule["reason_id"] is None
    rule = f.m.patch("qtime_rule", rule["id"], {"max_minutes": 40})
    assert rule["reason_id"] is None
    (lot,) = f.start(1)
    f.run_step(lot)
    _expire(f, lot)
    f.post(f"{EXEC}/qtime/sweep", {})
    (h,) = _list(f, lot)
    assert h["reason"] == "qtime_expired" and h["qtime_rule_id"] == rule["id"]
    got = f.m.patch("qtime_rule", rule["id"], {"is_active": False})
    assert got["is_active"] is False and got["reason_id"] is None
    # 停用后不再计时 / 处置
    (b,) = f.start(1)
    f.run_step(b)
    _expire(f, b)
    r = f.post(f"{EXEC}/qtime/sweep", {})
    assert all(x["lot"] != b["code"] for x in r["actions"])


def test_d25_patch_hold_rule_without_reason_never_422(
    client: TestClient, db: Session
) -> None:
    """D25（QT-B 类）：未配原因码的 hold 规则，任何 PATCH 都不 422。"""
    f = Line(client, db)
    rule = f.m.post("qtime_rule", _rule_body(f, reason_id=None))
    for body in (
        {"name": "renamed"},
        {"max_minutes": 45},
        {"warn_minutes": 20},
        {"description": "x"},
        {"action": "hold"},
        {"reason_id": None},
        {"is_active": False},
        {"is_active": True},
        {"action": "rework"},
        {"action": "hold"},
    ):
        got = f.m.patch("qtime_rule", rule["id"], body)
        assert got["reason_id"] is None
    assert got["action"] == "hold" and got["is_active"] is True


def test_d25_invalid_reason_still_422(client: TestClient, db: Session) -> None:
    """D25：配了不存在 / 其他租户的原因码仍 422。"""
    f = Line(client, db)
    g = Line(client, db)  # 另一个租户
    foreign = g.reasons["hold"]["id"]
    for rid in (str(uuid.uuid4()), foreign):
        r = f.c.post(
            f.m.url("qtime_rule"), headers=f.m.h, json=_rule_body(f, reason_id=rid)
        )
        assert r.status_code == 422, r.text
    ok = f.m.post("qtime_rule", _rule_body(f, reason_id=None))
    r = f.c.patch(
        f.m.url("qtime_rule", ok["id"]), headers=f.m.h, json={"reason_id": foreign}
    )
    assert r.status_code == 422, r.text


def test_d25_form_meta_matches_validation(client: TestClient, db: Session) -> None:
    """D25/D26：表单元数据：处置无 scrap，原因码选填（有说明），与校验一致。"""
    import json

    import app

    f = Line(client, db)
    meta = f.c.get("/api/v1/mes/_meta", headers=f.m.h).json()
    e = next(x for x in meta["entities"] if x["code"] == "qtime_rule")
    fr = next(x for x in e["fields"] if x["name"] == "reason")
    assert not fr["required_when"] and fr["help"]
    acts = meta["enums"]["qtime_action"]
    assert acts == ["warn", "hold", "rework"]
    p = Path(app.__file__).parents[2] / "frontend/src/i18n/locales/mes/zh-CN.json"
    assert "qtime_expired" in json.dumps(json.loads(p.read_text()), ensure_ascii=False)
    # 校验与元数据一致：hold / rework 缺原因码 200
    f.m.post("qtime_rule", _rule_body(f, reason_id=None))
    f.m.post("qtime_rule", _rule_body(f, action="rework", reason_id=None))


def test_d26_scrap_action_rejected(client: TestClient, db: Session) -> None:
    """D26：新建 / 修改提交 scrap → 422 qtime_action_invalid。"""
    f = Line(client, db)
    body = _rule_body(f, action="scrap", reason_id=f.reasons["scrap"]["id"])
    r = f.c.post(f.m.url("qtime_rule"), headers=f.m.h, json=body)
    assert r.status_code == 422, r.text
    d = r.json()["detail"]
    assert d["code"] == "qtime_action_invalid" and d["message"]
    ok = f.m.post("qtime_rule", _rule_body(f, reason_id=None))
    r = f.c.patch(
        f.m.url("qtime_rule", ok["id"]), headers=f.m.h, json={"action": "scrap"}
    )
    assert r.status_code == 422 and r.json()["detail"]["code"] == "qtime_action_invalid"


def _m0011() -> Any:
    import importlib.util

    import app

    p = (
        Path(app.__file__).parent
        / "alembic/versions/0011_qtime_rule_active_no_scrap.py"
    )
    spec = importlib.util.spec_from_file_location("m0011", p)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_d26_migration_scrap_rules_become_hold(client: TestClient, db: Session) -> None:
    """D26：已有 scrap 规则迁移后为 hold，原因码保留（含空）；重复执行不变；downgrade 恢复。"""
    f = Line(client, db)
    a = f.m.post("qtime_rule", _rule_body(f, reason_id=f.reasons["scrap"]["id"]))
    b = f.m.post("qtime_rule", _rule_body(f, reason_id=None))
    f.sql(
        "UPDATE mes_qtime_rule SET action='scrap' WHERE id IN (:a, :b)",
        a=a["id"],
        b=b["id"],
    )
    mod = _m0011()

    def state() -> dict[str, Any]:
        rows = f.m.list("qtime_rule")["data"]
        return {
            x["id"]: (x["action"], x["reason_id"])
            for x in rows
            if x["id"] in (a["id"], b["id"])
        }

    for _ in range(2):
        _run([mod.SCRAP_TO_HOLD])
        assert state() == {
            a["id"]: ("hold", f.reasons["scrap"]["id"]),
            b["id"]: ("hold", None),
        }
    for _ in range(2):
        _run([mod.HOLD_TO_SCRAP])
        assert {k: v[0] for k, v in state().items()} == {
            a["id"]: "scrap",
            b["id"]: "scrap",
        }
    _run([mod.SCRAP_TO_HOLD])
    # 迁移后的规则超时 → Hold，原因码保留（scrap 类型原因码不适用 hold 时回退 qtime_expired）
    (lot,) = f.start(1)
    f.run_step(lot)
    _expire(f, lot)
    f.post(f"{EXEC}/qtime/sweep", {})
    hs = _list(f, lot)
    assert hs and all(h["reason"] == "qtime_expired" for h in hs)


def test_qs_02_0010_conflicting_plan_code_reported(
    client: TestClient, db: Session
) -> None:
    """0010：已有同名 <code>-QT-TI 方案时不静默跳过——CONFLICTS 查出并记 warning。"""
    from app.core.db import admin_engine

    f, _ = _setup(client, db)
    plan = f.bind("move_in", ("qtime", "off", {}))
    f.m.post("check_plan", {"code": f"{plan['code']}-QT-TI", "name": "taken"})
    mod = _m0010()
    with admin_engine.connect() as c:
        rows = c.execute(text(mod.CONFLICTS)).all()
    assert (uuid.UUID(f.m.tid), plan["code"]) in [(r[0], r[1]) for r in rows]
    _run(mod.UPGRADE)
    assert not [b for b in _bindings(f) if b["trigger"] == "track_in"]
    _run(mod.DOWNGRADE)


def test_qa_01_deactivated_rule_no_hold(client: TestClient, db: Session) -> None:
    """D24 补充：停用后 Track In / sweep 都跳过（含停用前已在计时的批次），已挂 Hold 不动。"""
    f, rule = _setup(client, db)
    a, b, c = f.start(1, 1, 1)
    for x in (a, b, c):
        f.run_step(x)
        _expire(f, x)
    f.post(f"{EXEC}/qtime/sweep", {})  # a/b/c 都 Hold
    f.sql(
        "UPDATE mes_lot_hold SET is_active=false WHERE lot_id IN (:b, :c)",
        b=b["id"],
        c=c["id"],
    )
    f.sql("UPDATE mes_lot SET on_hold=false WHERE id IN (:b, :c)", b=b["id"], c=c["id"])
    f.sql(
        "DELETE FROM mes_lot_history WHERE action='qtime' AND lot_id IN (:b, :c)",
        b=b["id"],
        c=c["id"],
    )
    got = f.m.patch("qtime_rule", rule["id"], {"is_active": False})
    assert got["is_active"] is False
    r = f.post(f"{EXEC}/qtime/sweep", {})
    assert all(x["lot"] not in (b["code"], c["code"]) for x in r["actions"])
    f.stage(c, "move_in", **_eq(f))
    r = f.stage(c, "track_in", **_eq(f))
    assert not r.get("qtime") and f.lot(c)["lot_status"] == "running"
    assert not f.lot(b)["on_hold"]
    assert f.lot(a)["on_hold"] and len(_list(f, a)) == 1  # 已挂 Hold 不动
    mon = f.c.get(f"{EXEC}/qtime/monitor", headers=f.m.h).json()["data"]
    assert not [m for m in mon if m["lot"] == b["code"]]


def test_qa_02_reenabled_rule_not_retroactive(client: TestClient, db: Session) -> None:
    """D24 补充：重新启用只对此后开始计时的批次生效，不追溯。"""
    f, rule = _setup(client, db)
    f.m.patch("qtime_rule", rule["id"], {"is_active": False})
    (old,) = f.start(1)
    f.run_step(old)
    f.sql(
        "UPDATE mes_lot_history SET at = at - interval '3 hours' "
        "WHERE lot_id = :l AND action = 'move_out'",
        l=old["id"],
    )
    got = f.m.patch("qtime_rule", rule["id"], {"is_active": True})
    assert got["is_active"] is True and got["active_since"]
    # 把启用时间前移 150 分钟，便于构造「启用后到达、且已超时」的新批次
    f.sql(
        "UPDATE mes_qtime_rule SET active_since = now() - interval '150 minutes' "
        "WHERE id=:i",
        i=rule["id"],
    )
    (new,) = f.start(1)
    f.run_step(new)
    _expire(f, new)  # 计时起点 now-2h，晚于启用时间
    r = f.post(f"{EXEC}/qtime/sweep", {})
    codes = [x["lot"] for x in r["actions"]]
    assert new["code"] in codes and old["code"] not in codes
    assert not f.lot(old)["on_hold"] and f.lot(new)["on_hold"]
    # 修改其他字段不改变启用时间
    since = f.m.list("qtime_rule", code=rule["code"])["data"][0]["active_since"]
    got = f.m.patch("qtime_rule", rule["id"], {"name": "x", "active_since": None})
    assert got["active_since"] == since  # 只读，且改其他字段不变


def test_qa_03_form_meta_is_active(client: TestClient, db: Session) -> None:
    """表单元数据含 is_active 开关且列表显示。"""
    f = Line(client, db)
    meta = f.c.get("/api/v1/mes/_meta", headers=f.m.h).json()
    e = next(x for x in meta["entities"] if x["code"] == "qtime_rule")
    fa = next(x for x in e["fields"] if x["name"] == "is_active")
    assert fa["type"] == "bool" and fa.get("list", True)
