"""P2-B9 设备报警：主数据唯一与 D59 校验、set 只切设备状态不 Hold（D58，trigger=equipment）、
迁移表不允许时 state_changed=false、未登记只记录、幂等（active 同 ALID / 同事件号，事件号同内容不同
422）、清除、按批次反查、严格载荷、先查权限、UTC Z、raw 返回。"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.mes.execution.tests.test_split_merge import _line
from app.mes.product.tests.test_bom import _member

EQP = f"{settings.API_V1_STR}/mes/eqp"


def _setup(client: TestClient, db: Session) -> Any:
    f = _line(client, db)
    lot, idle = f.start(2, 2)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    et = f.eq["equipment_type_id"]
    f.m.post(
        "alarm_code",
        {
            "equipment_type_id": et,
            "alid": "1001",
            "severity": "major",
            "action": "set_state",
            "target_state": "DOWN",
            "text_en": "Chamber pressure high",
        },
    )
    return f, lot, idle


def _set(f: Any, status: int = 200, eq: Any = None, **body: Any) -> Any:
    return f.post(f"{EQP}/{(eq or f.eq)['id']}/alarms", body, status)


def test_alarm_set_links_holds_e10_and_clear(client: TestClient, db: Session) -> None:
    f, lot, idle = _setup(client, db)
    m = f.m
    # 主数据：同类型同 ALID 重复 → 409/422（部分唯一索引）
    r = client.post(
        m.url("alarm_code"),
        headers=m.h,
        json={
            "equipment_type_id": f.eq["equipment_type_id"],
            "alid": "1001",
            "severity": "info",
            "action": "none",
        },
    )
    assert r.status_code in (409, 422), r.text
    # D59：set_state 必须带存在的状态编码；none 不能带 target_state；旧 action 值 422
    base = {"equipment_type_id": f.eq["equipment_type_id"], "severity": "info"}
    for bad in (
        {"alid": "2002", "action": "set_state"},
        {"alid": "2002", "action": "set_state", "target_state": "NOPE"},
        {"alid": "2002", "action": "none", "target_state": "DOWN"},
        {"alid": "2002", "action": "hold_lot"},
        {"alid": "2002", "action": "hold_both", "target_state": "DOWN"},
    ):
        r = client.post(m.url("alarm_code"), headers=m.h, json={**base, **bad})
        assert r.status_code == 422, (bad, r.text)
    at = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    r = _set(
        f,
        alid=" 1001 ",
        raw={"S5F1": {"ALCD": 132}},
        occurred_at=at,
        external_event_id="EV-1",
    )
    assert r["duplicate"] is False
    a = r["data"]
    assert a["alarm_status"] == "active" and a["unregistered"] is False
    assert a["set_at"].endswith("Z") and a["raw"] == {"S5F1": {"ALCD": 132}}
    assert [x["lot_code"] for x in a["lots"]] == [lot["code"]]
    # D58：不 Hold；设备切到 DOWN，E10 履历 source=manual（报警来源）、trigger=equipment
    assert r["state_changed"] is True and r["state_skip_reason"] is None
    assert r["data"]["state_changed"] is True and r["data"]["state_skip_reason"] is None
    assert a["hold_ids"] is None and f.lot(lot)["on_hold"] is False
    assert m.list("lot_hold", lot=lot["id"])["count"] == 0
    assert a["e10_change"]["from"] == "SBY" and a["e10_change"]["to"] == "DOWN"
    assert a["e10_change"]["trigger"] == "equipment"
    eh = m.list("e10_history", equipment=f.eq["id"])["data"]
    assert [(x["source"], x["trigger"]) for x in eh] == [("manual", "equipment")]
    # e10_history.trigger 枚举不再与 e10_auto_rule 的 e10_trigger 冲突：过滤 200
    r = f.c.get(
        m.url("e10_history"),
        headers=m.h,
        params={"trigger": "equipment", "equipment": f.eq["id"]},
    )
    assert r.status_code == 200, r.text
    assert [x["trigger"] for x in r.json()["data"]] == ["equipment"]
    meta = f.c.get(f"{settings.API_V1_STR}/mes/_meta", headers=m.h).json()
    ent = {e["code"]: e for e in meta["entities"]}
    tf = next(x for x in ent["e10_history"]["fields"] if x["name"] == "trigger")
    assert tf["enum"] == "e10_history_trigger"
    rf = next(x for x in ent["e10_auto_rule"]["fields"] if x["name"] == "trigger")
    assert rf["enum"] == "e10_trigger"
    assert meta["enums"]["e10_history_trigger"] == ["manual", "equipment", "system"]
    assert meta["enums"]["e10_trigger"] == ["track_in", "track_out"]
    # 幂等：同 active ALID / 同事件号 → 已有记录
    for body in ({"alid": "1001"}, {"alid": "1001", "external_event_id": "EV-1"}):
        d = _set(f, **body)
        assert d["duplicate"] is True and d["data"]["id"] == a["id"]
    # D57：同事件号、内容不同 → 422 idempotency_key_reused，不写入
    for bad in (
        {"alid": "1002", "external_event_id": "EV-1"},
        {"alid": "1001", "external_event_id": "EV-1", "raw": {"x": 1}},
        {"alid": "1001", "external_event_id": "EV-1", "lot_ids": [idle["id"]]},
    ):
        d = _set(f, 422, **bad)["detail"]
        assert d["code"] == "idempotency_key_reused"
    assert m.list("alarm_lot", alarm_log=a["id"])["count"] == 1
    # 按批次反查
    r = client.get(f"{EQP}/alarms", headers=m.h, params={"lot_id": lot["id"]})
    assert r.status_code == 200 and r.json()["count"] == 1
    # 清除：不恢复 E10；同清除事件号重放返回原记录；再清除 200 cleared=false（D55）
    url = f"{EQP}/alarms/{a['id']}/clear"
    c = f.post(url, {"comment": "fixed", "external_event_id": "CL-1"})
    assert c["cleared"] is True and c["data"]["alarm_status"] == "cleared"
    assert c["data"]["cleared_at"].endswith("Z")
    rp = f.post(url, {"external_event_id": "CL-1"})
    assert rp["duplicate"] is True and rp["cleared"] is False
    assert rp["data"]["cleared_at"] == c["data"]["cleared_at"]
    again = f.post(url, {"comment": "x"})
    assert again["cleared"] is False and again["data"]["comment"] == "fixed"
    # 清除后同 ALID 再报：新的一次发生；设备已是 DOWN → state_changed=false
    r2 = _set(f, alid="1001")
    assert r2["data"]["id"] != a["id"]
    assert (
        r2["state_changed"] is False and r2["state_skip_reason"] == "already_in_state"
    )
    assert r2["data"]["state_changed"] is False
    assert r2["data"]["state_skip_reason"] == "already_in_state"
    assert client.get(f"{EQP}/alarms/{a['id']}", headers=m.h).json()["raw"]
    r = client.get(f"{EQP}/alarms/{f.lot(lot)['id']}", headers=m.h)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "alarm_not_found"


def test_alarm_unregistered_strict_perm(client: TestClient, db: Session) -> None:
    f, lot, _idle = _setup(client, db)
    m = f.m
    a = _set(f, alid="9999", alarm_text="unknown")["data"]
    assert a["unregistered"] is True and a["action"] == "none"
    # D55 OQ-3：未登记也写在制批关联，但不 Hold、不切 E10
    assert [x["lot_code"] for x in a["lots"]] == [lot["code"]]
    assert f.lot(lot)["on_hold"] is False and a["e10_change"] is None
    r = client.get(f"{EQP}/alarms", headers=m.h, params={"unregistered": True})
    assert r.json()["count"] == 1
    # D30：source 422；未知字段 422；未来时间 422 time_in_future；偏移换算成 Z
    for bad in ({"alid": "1", "source": "eap"}, {"alid": "1", "foo": 1}):
        _set(f, 422, **bad)
    fut = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    d = _set(f, 422, alid="3", set_at=fut)["detail"]
    assert d[0]["code"] == "time_in_future"
    near = (datetime.now(UTC) + timedelta(minutes=4)).isoformat()
    _set(f, alid="3", set_at=near)  # 5 分钟以内接受
    r = _set(f, alid="4", set_at="2026-01-01T08:00:00+08:00")
    assert r["data"]["set_at"] == "2026-01-01T00:00:00Z"
    _set(f, 422, alid="5", lot_ids=[f.eq["id"]])
    # 先查权限（D34）：只读成员带非法体也是 403
    h = _member(client, db, m)
    r = client.post(f"{EQP}/{f.eq['id']}/alarms", headers=h, json={"foo": 1})
    assert r.status_code == 403
    assert client.get(f"{EQP}/alarms", headers=h).status_code in (200, 403)


def test_alarm_explicit_lot_ids_and_skip(client: TestClient, db: Session) -> None:
    f, lot, idle = _setup(client, db)
    f.m.post(
        "alarm_code",
        {
            "equipment_type_id": f.eq["equipment_type_id"],
            "alid": "7",
            "severity": "minor",
            "action": "set_state",
            "target_state": "PRD",
        },
    )
    # 上报带入的 waiting 批次也关联；不 Hold（D58）
    f.post(f"{EQP}/{f.eq['id']}/e10", {"to_state_id": f.st["DOWN"]["id"]})
    r = _set(f, alid="7", lot_ids=[idle["id"]])
    a = r["data"]
    assert {x["lot_code"] for x in a["lots"]} == {lot["code"], idle["code"]}
    assert f.lot(idle)["on_hold"] is False and f.lot(lot)["on_hold"] is False
    # D59：DOWN -> PRD 不在迁移表：报警照记，状态不变，200 state_changed=false + 原因 + 审计
    assert (
        r["state_changed"] is False
        and r["state_skip_reason"] == "transition_not_allowed"
    )
    assert a["e10_change"]["state_changed"] is False
    eh = f.m.list("e10_history", equipment=f.eq["id"])["data"]
    assert len(eh) == 1 and eh[0]["trigger"] == "manual"  # 只有人工那条
    n = f.sql(
        "SELECT count(*) FROM mes_audit_log WHERE tenant_id = :t AND action = 'alarm_state_skipped'",
        t=f.m.tid,
    )
    assert n[0][0] == 1


def test_migration_0029_up_down() -> None:
    """0029 可重复执行：e10_history.trigger、alarm_code.target_state，旧列已删。"""
    from app.mes.equipment.tests.test_qual import _migration_roundtrip

    def check(i: Any) -> tuple[frozenset[str], bool]:
        h = {c["name"] for c in i.get_columns("mes_e10_history")}
        c = {c["name"] for c in i.get_columns("mes_alarm_code")}
        return frozenset(
            {"trigger"} & h | {"target_state"} & c
        ), "hold_reason_id" not in c

    _migration_roundtrip(
        "0028_eap_events_idempotency",
        "d58",
        check,
        ("mes_e10_history", "mes_alarm_code", "trigger", "target_state"),
    )


def test_alarm_code_unknown_fields_422(client: TestClient, db: Session) -> None:
    """P2-D6 / D38：报警码未知字段（含已删除的 target_e10_state_id）→ 422（严格载荷）。"""
    f = _line(client, db)
    url = f"{settings.API_V1_STR}/mes/alarm-code"
    base = {"equipment_type_id": f.eq["equipment_type_id"], "alid": "D6"}
    for extra in ({"foo": 1}, {"target_e10_state_id": f.st["DOWN"]["id"]}):
        r = f.c.post(url, headers=f.m.h, json={**base, **extra})
        assert r.status_code == 422, r.text
        d = r.json()["detail"]
        assert [x["loc"][-1] for x in d] == list(extra)
    r = f.c.post(url, headers=f.m.h, json=base)
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    r = f.c.patch(f"{url}/{rid}", headers=f.m.h, json={"foo": "x"})
    assert r.status_code == 422 and r.json()["detail"][0]["loc"][-1] == "foo"
    # 字段名与列名（xxx_id）都可用
    r = f.c.patch(f"{url}/{rid}", headers=f.m.h, json={"severity": "minor"})
    assert r.status_code == 200, r.text


def test_migration_0029_no_udt_note() -> None:
    """OQ-20：租户无 UDT 时 hold_equipment / hold_both 降为 none，写 migration_note、记 WARNING；
    升 → 降 → 升，降级删列。"""
    import os
    import subprocess
    import uuid as _u
    from pathlib import Path

    from sqlalchemy import create_engine, inspect
    from sqlalchemy.engine import make_url

    base = make_url(settings.migration_database_url)
    name = f"{base.database}_mig_oq20"
    server = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with server.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = base.set(database=name).render_as_string(hide_password=False)
    backend = Path(__file__).resolve().parents[4]

    def alembic(*args: str) -> str:
        env = {**os.environ, "MIGRATION_DATABASE_URL": url, "POSTGRES_DB": name}
        r = subprocess.run(
            ["alembic", *args], cwd=backend, env=env, capture_output=True, text=True
        )
        assert r.returncode == 0, r.stderr[-2000:]
        return r.stderr + r.stdout

    eng = create_engine(url)
    ids = {k: _u.uuid4() for k in ("he", "hb", "hl", "ok", "t1", "t2", "s")}
    try:
        alembic("upgrade", "0028_eap_events_idempotency")
        with eng.begin() as c:
            # 临时库：去掉租户 / 设备类型外键，只造报警码与状态行
            for t in ("mes_alarm_code", "mes_e10_state"):
                for (fk,) in c.execute(
                    text(
                        "SELECT conname FROM pg_constraint WHERE contype = 'f'"
                        " AND conrelid = CAST(:t AS regclass)"
                    ),
                    {"t": t},
                ):
                    c.execute(text(f'ALTER TABLE {t} DROP CONSTRAINT "{fk}"'))
            # t1 无 UDT；t2 有 UDT
            c.execute(
                text(
                    "INSERT INTO mes_e10_state (id, tenant_id, code, name, e10_category,"
                    " created_at, updated_at) VALUES (:s, :t2, 'UDT', 'UDT', 'UDT', now(), now())"
                ),
                {"s": ids["s"], "t2": ids["t2"]},
            )
            for k, t, act in (
                ("he", "t1", "hold_equipment"),
                ("hb", "t1", "hold_both"),
                ("hl", "t1", "hold_lot"),
                ("ok", "t2", "hold_both"),
            ):
                c.execute(
                    text(
                        "INSERT INTO mes_alarm_code (id, tenant_id, equipment_type_id, alid,"
                        " alcd_category, category, severity, action, require_qual_on_clear, is_active,"
                        " created_at, updated_at) VALUES (:i, :t, :et, :a, 0, 'other', 'major', :act,"
                        " false, true, now(), now())"
                    ),
                    {"i": ids[k], "t": ids[t], "et": _u.uuid4(), "a": k, "act": act},
                )
        out = alembic("upgrade", "head")
        assert out.count("no UDT state") >= 2, out
        assert str(ids["he"]) in out and str(ids["t1"]) in out and "hold_both" in out

        def rows() -> dict[str, tuple[str, str | None]]:
            with eng.connect() as c:
                return {
                    r.alid: (r.action, r.migration_note)
                    for r in c.execute(
                        text("SELECT alid, action, migration_note FROM mes_alarm_code")
                    )
                }

        want = {
            "he": ("none", "0029: was hold_equipment, no UDT state"),
            "hb": ("none", "0029: was hold_both, no UDT state"),
            "hl": ("none", None),
            "ok": ("set_state", None),
        }
        assert rows() == want
        alembic("downgrade", "0028_eap_events_idempotency")
        with eng.connect() as c:
            cols = {x["name"] for x in inspect(c).get_columns("mes_alarm_code")}
        assert "migration_note" not in cols
        alembic("upgrade", "head")
        with eng.connect() as c:
            cols = {x["name"] for x in inspect(c).get_columns("mes_alarm_code")}
        assert "migration_note" in cols
    finally:
        eng.dispose()
        with server.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        server.dispose()


def test_alarm_code_migration_note_api(client: TestClient, db: Session) -> None:
    """OQ-20：migration_note 只读（写入 422）；改为 set_state 自动清空；?has_migration_note。"""
    f = _line(client, db)
    url = f"{settings.API_V1_STR}/mes/alarm-code"
    base = {"equipment_type_id": f.eq["equipment_type_id"], "alid": "N1"}
    r = f.c.post(url, headers=f.m.h, json={**base, "migration_note": "x"})
    assert r.status_code == 422 and r.json()["detail"][0]["type"] == "read_only_field"
    a = f.c.post(url, headers=f.m.h, json=base).json()
    b = f.c.post(url, headers=f.m.h, json={**base, "alid": "N2"}).json()
    assert a["migration_note"] is None
    r = f.c.patch(f"{url}/{a['id']}", headers=f.m.h, json={"migration_note": None})
    assert r.status_code == 422
    f.sql(
        "UPDATE mes_alarm_code SET migration_note = '0029: was hold_both, no UDT state'"
        " WHERE id IN (:a, :b)",
        a=a["id"],
        b=b["id"],
    )
    got = f.c.get(
        url, headers=f.m.h, params={"has_migration_note": "true", "alid": "N1"}
    ).json()
    assert [x["id"] for x in got["data"]] == [a["id"]]
    assert got["data"][0]["migration_note"] == "0029: was hold_both, no UDT state"
    r = f.c.patch(
        f"{url}/{a['id']}",
        headers=f.m.h,
        json={"action": "set_state", "target_state": "DOWN"},
    )
    assert r.status_code == 200 and r.json()["migration_note"] is None, r.text
    ids = {
        x["id"]
        for x in f.c.get(
            url, headers=f.m.h, params={"has_migration_note": "false"}
        ).json()["data"]
    }
    assert a["id"] in ids and b["id"] not in ids
    # 改其他字段不清空
    r = f.c.patch(f"{url}/{b['id']}", headers=f.m.h, json={"severity": "minor"})
    assert r.json()["migration_note"] == "0029: was hold_both, no UDT state"
