"""B3 验收（D28，bom.md v1.1 §9–10）：机台上料记录。

上料口唯一定位、同一上料口同时只装一批（人工 409 / EAP 自动换批）、外部事件号去重幂等、
source=eap 必填事件号、物料批存在且未过期、卸料、按时间点反查、只读通用接口、权限、迁移。
"""

import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.db import engine
from app.core.tenant import set_tenant
from app.mes.equipment import mount as mount_svc
from app.mes.product.tests.test_bom import _member
from app.testing.mes import API, Mes

EQP = f"{API}/eqp"


class F:
    def __init__(self, client: TestClient, db: Session) -> None:
        m = self.m = Mes(client, db)
        self.c = client
        self.eq = m.post("equipment", {"code": "DA01", "name": "die attach"})
        self.eq2 = m.post("equipment", {"code": "DA02", "name": "die attach 2"})
        mt = m.post(
            "material_type", {"code": "EPX", "name": "epoxy", "category": "chemical"}
        )
        self.mat = m.post(
            "material",
            {
                "code": "EPOXY",
                "name": "epoxy",
                "material_type_id": mt["id"],
                "uom_id": m.fx("uom"),
            },
        )
        self.lots = [self.ml(f"ML{i}") for i in range(4)]

    def ml(self, code: str, **kw: Any) -> Any:
        return self.m.post(
            "material_lot",
            {
                "code": code,
                "material_id": self.mat["id"],
                "qty_remaining": 10,
                "uom_id": self.m.fx("uom"),
                **kw,
            },
        )

    def mount(
        self,
        lot: Any,
        port: str = "P1",
        status: int = 200,
        eq: Any = None,
        h: Any = None,
        **kw: Any,
    ) -> Any:
        r = self.c.post(
            f"{EQP}/{(eq or self.eq)['id']}/mount",
            headers=h or self.m.h,
            json={"port_code": port, "material_lot_id": lot["id"], **kw},
        )
        assert r.status_code == status, r.text
        return r.json()

    def unmount(self, mid: str, status: int = 200, h: Any = None, **kw: Any) -> Any:
        r = self.c.post(
            f"{EQP}/mount/{mid}/unmount", headers=h or self.m.h, json=kw or None
        )
        assert r.status_code == status, r.text
        return r.json()

    def at(self, t: datetime, eq: Any = None, status: int = 200, **kw: Any) -> Any:
        r = self.c.get(
            f"{EQP}/mount/at",
            headers=self.m.h,
            params={"eq_id": (eq or self.eq)["id"], "at": t.isoformat(), **kw},
        )
        assert r.status_code == status, r.text
        return r.json()

    def eap(
        self, lot: Any, port: str, ext: str | None, at: datetime | None = None
    ) -> Any:
        with Session(engine) as s:
            set_tenant(s, uuid.UUID(self.m.tid))
            return mount_svc.mount(
                s,
                uuid.UUID(self.m.tid),
                uuid.UUID(self.eq["id"]),
                {
                    "port_code": port,
                    "material_lot_id": lot["id"],
                    "external_event_id": ext,
                    "mounted_at": at,
                },
                None,
                source="eap",
            )


def test_manual_mount_unmount_and_port_rules(client: TestClient, db: Session) -> None:
    f = F(client, db)
    r = f.mount(f.lots[0], comment="new epoxy")
    d = r["data"]
    assert r["duplicate"] is False and r["unmounted"] is None
    assert (d["port_code"], d["source"], d["material_lot_code"]) == (
        "P1",
        "manual",
        "ML0",
    )
    assert d["material_id"] == f.mat["id"] and d["unmounted_at"] is None
    assert d["mounted_by"] and d["equipment_label"].startswith("DA01")
    # 同一上料口已有料：409 并写明当前批
    err = f.mount(f.lots[1], status=409)["detail"]
    assert err["code"] == "port_occupied" and err["current_material_lot_code"] == "ML0"
    assert err["current_mount_id"] == d["id"] and err["port_code"] == "P1"
    # 另一个上料口 / 另一台机台的同名上料口：可以
    f.mount(f.lots[1], "P2")
    f.mount(f.lots[2], "P1", eq=f.eq2)
    # 卸料后可再装
    u = f.unmount(d["id"])["data"]
    assert u["unmounted_at"] and u["unmounted_by"]
    err = f.unmount(d["id"], 409)["detail"]
    assert err["code"] == "already_unmounted"
    f.mount(f.lots[3], "P1")
    f.unmount(str(uuid.uuid4()), 404)
    # 物料批：不存在 / 已过期
    r = f.c.post(
        f"{EQP}/{f.eq['id']}/mount",
        headers=f.m.h,
        json={"port_code": "P9", "material_lot_id": str(uuid.uuid4())},
    )
    assert r.status_code == 422 and "not found" in r.text
    old = f.ml("OLD", expiry_date=(date.today() - timedelta(days=1)).isoformat())
    assert "expired" in str(f.mount(old, "P9", 422))
    # 按编码上料
    r = f.c.post(
        f"{EQP}/{f.eq['id']}/mount",
        headers=f.m.h,
        json={"port_code": "P8", "material_lot_code": "ML0"},
    )
    assert r.status_code == 200 and r.json()["data"]["material_lot_code"] == "ML0"
    # 设备不存在 / 未来时间
    f.mount(f.lots[0], "P7", 404, eq={"id": str(uuid.uuid4())})
    fut = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    f.mount(f.lots[0], "P7", 422, mounted_at=fut)
    # 只读通用接口
    lst = f.m.list("equipment_material_mount", equipment=f.eq["id"])
    assert lst["count"] == 4
    r = f.c.post(f"{API}/equipment-material-mount", headers=f.m.h, json={})
    assert r.status_code == 405
    # 审计
    acts = {
        x["action"]
        for x in f.m.list("audit_log", entity_type="equipment_material_mount")["data"]
    }
    assert {"mount", "unmount"} <= acts


def test_mount_at_point_in_time_and_overlap(client: TestClient, db: Session) -> None:
    f = F(client, db)
    t0 = datetime.now(UTC) - timedelta(hours=10)
    a = f.mount(f.lots[0], mounted_at=t0.isoformat())["data"]
    f.unmount(a["id"], unmounted_at=(t0 + timedelta(hours=2)).isoformat())
    b = f.mount(f.lots[1], mounted_at=(t0 + timedelta(hours=3)).isoformat())["data"]
    f.mount(f.lots[2], "P2", mounted_at=(t0 + timedelta(hours=1)).isoformat())
    codes = lambda r: [(x["port_code"], x["material_lot_code"]) for x in r["data"]]  # noqa: E731
    assert codes(f.at(t0 + timedelta(hours=1, minutes=30))) == [
        ("P1", "ML0"),
        ("P2", "ML2"),
    ]
    assert codes(f.at(t0 + timedelta(hours=2))) == [("P2", "ML2")]  # 卸下那一刻不算
    assert codes(f.at(t0 + timedelta(hours=4))) == [("P1", "ML1"), ("P2", "ML2")]
    assert codes(f.at(t0 + timedelta(hours=4), port_code="P1")) == [("P1", "ML1")]
    assert f.at(t0 - timedelta(hours=1))["data"] == []
    assert f.at(t0, eq=f.eq2)["data"] == []
    # 卸下时间不能早于装上
    f.unmount(b["id"], 422, unmounted_at=t0.isoformat())
    # 回填的装上时间不能落进已关闭记录的区间
    f.unmount(b["id"], unmounted_at=(t0 + timedelta(hours=5)).isoformat())
    err = f.mount(
        f.lots[3], mounted_at=(t0 + timedelta(hours=1)).isoformat(), status=409
    )["detail"]
    assert err["code"] == "mount_overlap"
    # 时间点必须带时区
    r = f.c.get(
        f"{EQP}/mount/at",
        headers=f.m.h,
        params={"eq_id": f.eq["id"], "at": "2026-01-01T00:00:00"},
    )
    assert r.status_code == 422


def test_eap_replace_and_dedupe(client: TestClient, db: Session) -> None:
    f = F(client, db)
    # source=eap 时外部事件号必填
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ex:
        f.eap(f.lots[0], "P1", None)
    assert ex.value.status_code == 422
    t1 = datetime.now(UTC) - timedelta(minutes=30)
    r1 = f.eap(f.lots[0], "P1", "EV-1", t1)
    assert r1["data"]["source"] == "eap" and r1["data"]["external_event_id"] == "EV-1"
    # 重复事件：幂等返回已有记录，不新建
    r1b = f.eap(f.lots[1], "P1", "EV-1")
    assert r1b["duplicate"] is True and r1b["data"]["id"] == r1["data"]["id"]
    # 新事件装新批：同一事务先卸旧批，卸下时间 = 新批装上时间
    t2 = t1 + timedelta(minutes=10)
    r2 = f.eap(f.lots[1], "P1", "EV-2", t2)
    assert r2["unmounted"]["id"] == r1["data"]["id"]
    rows = {x["id"]: x for x in f.m.list("equipment_material_mount")["data"]}
    old, new = rows[r1["data"]["id"]], rows[r2["data"]["id"]]
    assert old["unmounted_at"] == new["mounted_at"]
    assert sum(1 for x in rows.values() if x["unmounted_at"] is None) == 1
    # 人工的同名事件号不与 EAP 冲突（按 source 区分）
    f.mount(f.lots[2], "P2", external_event_id="EV-1")
    # 人工重复事件也幂等
    r = f.mount(f.lots[3], "P3", external_event_id="EV-1")
    assert r["duplicate"] is True
    # EAP 时间早于在装批次：拒绝
    with pytest.raises(HTTPException) as ex:
        f.eap(f.lots[2], "P1", "EV-3", t1)
    assert ex.value.status_code == 422


def test_mount_permissions(client: TestClient, db: Session) -> None:
    f = F(client, db)
    d = f.mount(f.lots[0])["data"]
    hm = _member(client, db, f.m)
    f.mount(f.lots[1], "P2", 403, h=hm)
    f.unmount(d["id"], 403, h=hm)
    r = client.get(
        f"{EQP}/mount/at",
        headers=hm,
        params={"eq_id": f.eq["id"], "at": datetime.now(UTC).isoformat()},
    )
    assert r.status_code == 200 and len(r.json()["data"]) == 1
    assert client.get(f"{API}/equipment-material-mount", headers=hm).status_code == 200


def test_migration_0014_and_metadata_indexes() -> None:
    """0014 可重复执行；表定义里的部分唯一索引与迁移一致（自动生成迁移不会删除）。"""
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
    name = f"{base.database}_mig_b3"
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

    T = "mes_equipment_material_mount"
    eng = create_engine(url)

    def idx() -> set[str]:
        with eng.connect() as c:
            i = inspect(c)
            if T not in i.get_table_names():
                return set()
            return {x["name"] for x in i.get_indexes(T) if x["name"].startswith("uq_")}

    try:
        alembic("upgrade", "head")
        assert idx() == {"uq_mes_eqp_mount_port_open", "uq_mes_eqp_mount_event"}
        ours = {T, "mes_bom"}
        with eng.connect() as c:
            diffs = compare_metadata(MigrationContext.configure(c), SQLModel.metadata)
        flat = [d for x in diffs for d in (x if isinstance(x, list) else [x])]
        bad = [d for d in flat if any(n in str(d) for n in ours) and "uq_" in str(d)]
        assert not bad, bad
        alembic("stamp", "0013_bom_line_operation")
        alembic("upgrade", "head")
        alembic("downgrade", "0013_bom_line_operation")
        assert idx() == set()
        alembic("stamp", "head")
        alembic("downgrade", "0013_bom_line_operation")
        alembic("upgrade", "head")
        assert len(idx()) == 2
    finally:
        eng.dispose()
        with server.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        server.dispose()


def test_manual_mount_strict_payload(client: TestClient, db: Session) -> None:
    """人工上料接口：传 source（任何值）或未知字段 → 422（bom.md §12）。"""
    f = F(client, db)
    for v in ("manual", "eap"):
        r = f.mount(f.lots[0], status=422, source=v)
        assert any(d["loc"][-1] == "source" for d in r["detail"])
    f.mount(f.lots[0], status=422, foo=1)
    d = f.mount(f.lots[0])["data"]
    r = f.unmount(d["id"], 422, unmounted_by="x")
    assert any(d["loc"][-1] == "unmounted_by" for d in r["detail"])
    assert f.m.list("equipment_material_mount")["count"] == 1


def test_manual_external_event_id_dedupe(client: TestClient, db: Session) -> None:
    """D30：人工同一事件号重复提交只记一次（duplicate=true）；与 EAP 同号互不干扰。"""
    f = F(client, db)
    r1 = f.mount(f.lots[0], "P1", external_event_id="EV-9")
    r2 = f.mount(f.lots[1], "P2", external_event_id="EV-9")
    assert r1["duplicate"] is False and r2["duplicate"] is True
    assert r2["data"]["id"] == r1["data"]["id"]
    rows = f.m.list("equipment_material_mount")["data"]
    assert len(rows) == 1 and rows[0]["port_code"] == "P1"
    # EAP 用同一事件号：独立记录；之后各自重复都只返回自己那条
    e1 = f.eap(f.lots[2], "P3", "EV-9")
    assert e1["duplicate"] is False and e1["data"]["source"] == "eap"
    assert f.eap(f.lots[3], "P4", "EV-9")["data"]["id"] == e1["data"]["id"]
    assert (
        f.mount(f.lots[3], "P5", external_event_id="EV-9")["data"]["id"]
        == (r1["data"]["id"])
    )
    rows = f.m.list("equipment_material_mount")["data"]
    assert sorted((x["source"], x["port_code"]) for x in rows) == [
        ("eap", "P3"),
        ("manual", "P1"),
    ]


def test_mount_times_are_utc_z(client: TestClient, db: Session) -> None:
    """D2：输入带任意时区，存 timestamptz；响应统一 UTC（Z）。EAP 换批时旧批卸下
    时间与新批装上时间同为 Z 且相等。"""
    tz8 = timezone(timedelta(hours=8))
    t1 = (datetime.now(UTC) - timedelta(hours=1)).replace(microsecond=0)
    f = F(client, db)
    r = f.mount(f.lots[0], "P9", mounted_at=t1.astimezone(tz8).isoformat())
    assert r["data"]["mounted_at"] == t1.isoformat().replace("+00:00", "Z")
    e1 = f.eap(f.lots[1], "P1", "EV-A", t1)
    t2 = (t1 + timedelta(minutes=5)).astimezone(tz8)
    e2 = f.eap(f.lots[2], "P1", "EV-B", t2)
    old, new = e2["unmounted"]["unmounted_at"], e2["data"]["mounted_at"]
    assert old == new and new.endswith("Z") and e1["data"]["mounted_at"].endswith("Z")
    rows = f.m.list("equipment_material_mount")["data"]
    assert all(x["mounted_at"].endswith("Z") for x in rows)
    u = f.unmount(r["data"]["id"], unmounted_at=datetime.now(tz8).isoformat())
    assert u["data"]["unmounted_at"].endswith("Z")
    # BOM 生效时间同样输出 Z
    from app.mes.product.tests.test_bom import B

    b = B(f.m)
    v = b.bom(b.product("FGZ"))
    b.line(v, 10)
    a = b.act(v, "activate")
    assert a["effective_at"].endswith("Z") and a["confirmed_at"].endswith("Z")
