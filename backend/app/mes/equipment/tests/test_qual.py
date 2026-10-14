"""B6 验收（bom-p1-tasks.md）：PM 判 OK 后机台待 Qual（WAIT_QUAL）并生成 Qual 任务；待 Qual
时进站（Move In / Track In）硬拦截并写卡控记录；Qual 通过恢复、不通过保持待 Qual（生成复测
任务）；PM 判 NG 周期不重置、机台状态不变；接口严格载荷、权限；PM 输出时间为 UTC Z；迁移 0017。
"""

from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution.tests.test_exec import Line
from app.mes.product.tests.test_bom import _member

EQP = "/api/v1/mes/eqp"


def _pm(f: Line, **kw: Any) -> tuple[Any, Any]:
    plan = f.m.post(
        "pm_plan",
        {"code": "PM-Q", "name": "pm", "equipment_id": f.eq["id"], "interval_days": 30},
    )
    return plan, f.post(
        f"{EQP}/pm/{plan['id']}/complete", {"equipment_id": f.eq["id"], **kw}
    )


def _blocked(r: Any) -> list[Any]:
    d = r["detail"]
    assert d["code"] == "check_blocked", r
    return [x for x in d["results"] if x["check_type"] == "eqp_wait_qual"]


def _qual(f: Line, task: Any, status: int = 200, h: Any = None, **body: Any) -> Any:
    return f.post(f"{EQP}/qual/{task['id']}/result", body, status, h=h)


def _eq(f: Line) -> Any:
    return f.m.list("equipment", q=f.eq["code"])["data"][0]


def test_pm_ok_wait_qual_interlock_and_release(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    a, b = f.start(1, 1)
    f.stage(b, "move_in", equipment_id=f.eq["id"])  # PM 前已进站
    plan, r = _pm(f)
    # PM 判 OK：待 Qual + 一条 Qual 任务；PM 输出时间为 UTC Z
    assert r["qual_state"] == "wait_qual" and r["qual_task"]["qual_status"] == "open"
    task = r["qual_task"]
    assert task["pm_plan_id"] == plan["id"] and task["requested_at"].endswith("Z")
    pm = r["pm"][0]
    assert pm["last_done"].endswith("Z") and pm["next_due"].endswith("Z")
    assert _eq(f)["qual_state"] == "wait_qual"
    board = client.get(f"{EQP}/board", headers=f.m.h).json()["data"]
    row = next(x for x in board if x["id"] == f.eq["id"])
    assert row["qual_state"] == "wait_qual" and row["qual_task_id"] == task["id"]
    assert row["pm"][0]["last_done"].endswith("Z")
    # 再判一次 OK：沿用未登记的任务，不重复生成
    f.post(f"{EQP}/pm/{plan['id']}/complete", {"equipment_id": f.eq["id"]})
    assert f.m.list("equipment_qual", equipment=f.eq["id"])["count"] == 1
    # 进站被拦（Move In 与 Track In），强制放行也不行；写卡控记录
    (x,) = _blocked(f.stage(a, "move_in", 409, equipment_id=f.eq["id"]))
    assert x["data"]["task_id"] == task["id"] and not x["overridable"]
    _blocked(
        f.stage(
            a,
            "move_in",
            409,
            equipment_id=f.eq["id"],
            override=True,
            override_reason="try",
        )
    )
    _blocked(f.stage(b, "track_in", 409, equipment_id=f.eq["id"]))
    logs = f.m.list("check_log", check_type="eqp_wait_qual")["data"]
    assert {(g["trigger"], g["result"]) for g in logs} == {
        ("move_in", "block"),
        ("track_in", "block"),
    }
    assert len(logs) == 3
    # Qual 不通过：任务 failed + 复测任务，机台保持待 Qual，仍拦截
    r = _qual(f, task, result="fail", comment="particle NG")
    assert r["data"]["qual_status"] == "failed" and r["data"]["done_at"].endswith("Z")
    nxt = r["next_task"]
    assert nxt["qual_status"] == "open" and nxt["retry_of_id"] == task["id"]
    assert r["equipment"]["qual_state"] == "wait_qual"
    _blocked(f.stage(b, "track_in", 409, equipment_id=f.eq["id"]))
    # 已登记的任务不能再登记
    d = _qual(f, task, 409, result="pass")["detail"]
    assert d["code"] == "qual_task_closed" and d["qual_status"] == "failed"
    # 复测通过：恢复可生产，进站放行
    r = _qual(f, nxt, result="pass")
    assert r["next_task"] is None and r["equipment"]["qual_state"] == "ready"
    f.stage(b, "track_in", equipment_id=f.eq["id"])
    f.stage(a, "move_in", equipment_id=f.eq["id"])


def test_pm_ng_keeps_state(client: TestClient, db: Session) -> None:
    """PM 判 NG：周期不重置、机台状态不变、不生成 Qual 任务。"""
    f = Line(client, db)
    _, r = _pm(f, result="ng")
    assert r["qual_state"] == "ready" and r["qual_task"] is None
    assert r["pm"][0]["last_done"] is None
    assert f.m.list("equipment_qual")["count"] == 0
    (a,) = f.start(1)
    f.stage(a, "move_in", equipment_id=f.eq["id"])


def test_qual_payload_and_permission(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    _, r = _pm(f)
    task = r["qual_task"]
    for body in (
        {"result": "pass", "qual_status": "passed"},
        {"result": "pass", "done_by": "x"},
        {"result": "maybe"},
        {},
    ):
        _qual(f, task, 422, **body)
    hm = _member(client, db, f.m)
    _qual(f, task, 403, h=hm, result="pass")
    # 通用接口只读
    url = "/api/v1/mes/equipment-qual"
    assert client.get(url, headers=hm).status_code == 200
    r = client.post(url, headers=f.m.h, json={"equipment_id": f.eq["id"]})
    assert r.status_code in (403, 405)
    assert f.post(f"{EQP}/qual/{f.eq['id']}/result", {"result": "pass"}, 404)


def _migration_roundtrip(
    prev: str,
    tag: str,
    check: Any,
    keys: tuple[str, ...] = ("mes_equipment_qual", "qual_state"),
) -> None:
    """升到 head → 与表定义对比 → stamp prev 再升（已存在）→ 降回 prev → stamp head 再降
    （已不在）→ 再升。``check(insp)`` 返回 (升级后期望, 降级后期望) 之一的当前状态。"""
    import os
    import subprocess
    from pathlib import Path

    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.engine import make_url
    from sqlmodel import SQLModel

    from app.core.config import settings

    base = make_url(settings.migration_database_url)
    name = f"{base.database}_mig_{tag}"
    server = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with server.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = base.set(database=name).render_as_string(hide_password=False)
    backend = Path(__file__).resolve().parents[4]

    def alembic(*args: str) -> None:
        env = {**os.environ, "MIGRATION_DATABASE_URL": url}
        r = subprocess.run(
            ["alembic", *args], cwd=backend, env=env, capture_output=True, text=True
        )
        assert r.returncode == 0, r.stderr[-2000:]

    eng = create_engine(url)

    def state() -> Any:
        with eng.connect() as c:
            return check(inspect(c))

    try:
        alembic("upgrade", "head")
        up = state()
        with eng.connect() as c:
            diffs = compare_metadata(MigrationContext.configure(c), SQLModel.metadata)
        flat = [d for x in diffs for d in (x if isinstance(x, list) else [x])]
        bad = [d for d in flat if any(k in str(d) for k in keys)]
        assert not bad, bad
        alembic("stamp", prev)
        alembic("upgrade", "head")  # 已存在：不报错
        assert state() == up
        alembic("downgrade", prev)
        down = state()
        assert down != up
        alembic("stamp", "head")
        alembic("downgrade", prev)  # 已不在：不报错
        assert state() == down
        alembic("upgrade", "head")
        assert state() == up
    finally:
        eng.dispose()
        with server.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        server.dispose()


def test_migration_0017_up_down() -> None:
    """0017 可重复执行；表定义与迁移一致。"""

    def check(i: Any) -> tuple[bool, bool]:
        col = any(x["name"] == "qual_state" for x in i.get_columns("mes_equipment"))
        return col, "mes_equipment_qual" in i.get_table_names()

    _migration_roundtrip("0016_material_consumption_event", "b6", check)


def test_migration_0018_qual_source_index() -> None:
    """0018 可重复执行：source / external_event_id / chamber_id（0019 起为 sub_unit_id）与部分唯一索引。"""

    def check(i: Any) -> tuple[frozenset[str], bool]:
        cols = frozenset(
            x["name"]
            for x in i.get_columns("mes_equipment_qual")
            if x["name"] in ("source", "external_event_id", "chamber_id", "sub_unit_id")
        )
        idx = any(
            x["name"] == "uq_mes_eqp_qual_event"
            for x in i.get_indexes("mes_equipment_qual")
        )
        return cols, idx

    _migration_roundtrip("0017_equipment_qual", "b6s", check)


def test_qual_reserved_fields_rejected(client: TestClient, db: Session) -> None:
    """人工登记不开放 source / external_event_id / sub_unit（子单元）：传了 422；本期一律
    manual / 空。"""
    f = Line(client, db)
    _, r = _pm(f)
    task = r["qual_task"]
    assert (task["source"], task["external_event_id"], task["sub_unit_id"]) == (
        "manual",
        None,
        None,
    )
    for k, v in (
        ("source", "eap"),
        ("source", "manual"),
        ("external_event_id", "EV-1"),
        ("sub_unit_id", f.eq["id"]),
        ("sub_unit", "C1"),
        ("chamber_id", f.eq["id"]),
    ):
        d = _qual(f, task, 422, result="pass", **{k: v})["detail"]
        assert any(x["loc"][-1] == k for x in d), (k, d)
    assert _qual(f, task, result="pass")["data"]["source"] == "manual"


def test_migration_0019_customer_sub_unit() -> None:
    """0019 可重复执行、可降级：客户表 / 批次与物料批客户字段 / chamber_id → sub_unit_id。"""

    def check(i: Any) -> tuple[Any, ...]:
        def cols(t: str) -> frozenset[str]:
            return frozenset(x["name"] for x in i.get_columns(t))

        q = cols("mes_equipment_qual")
        return (
            "mes_customer" in i.get_table_names(),
            cols("mes_lot") & {"customer_lot_no", "ownership", "customer_id"},
            cols("mes_material_lot") & {"ownership", "customer_id"},
            q & {"chamber_id", "sub_unit_id"},
        )

    _migration_roundtrip(
        "0018_equipment_qual_source",
        "b7",
        check,
        ("mes_equipment_qual", "qual_state", "customer", "ownership"),
    )
