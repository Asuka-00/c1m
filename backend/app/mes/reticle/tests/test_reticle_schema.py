"""P3-B4 光罩 schema：6 张新表 RLS（ENABLE + FORCE、策略 tenant_isolation）、列类型、
部分唯一索引、mes_reticle 只读字段 422 read_only_field、mes.reticle:* 权限三语说明。"""

from fastapi.testclient import TestClient
from sqlmodel import Session, text

from app.core.db import admin_engine
from app.platform.rbac.labels import permission_description
from app.testing.mes import Mes

NEW = (
    "mes_reticle_applicability",
    "mes_reticle_incident",
    "mes_reticle_mount_log",
    "mes_reticle_usage",
    "mes_reticle_inspection",
    "mes_reticle_status_log",
)


def _q(sql: str, **p: object) -> list:
    with admin_engine.connect() as c:
        return list(c.execute(text(sql), p))


def test_new_tables_rls_force_and_policy() -> None:
    rows = {
        r[0]: (r[1], r[2])
        for r in _q(
            "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = ANY(:t)",
            t=list(NEW),
        )
    }
    assert set(rows) == set(NEW)
    assert all(v == (True, True) for v in rows.values()), rows
    pol = {
        r[0]
        for r in _q(
            "SELECT tablename FROM pg_policies WHERE policyname = 'tenant_isolation' AND tablename = ANY(:t)",
            t=list(NEW),
        )
    }
    assert pol == set(NEW)
    for t in NEW:
        nn = _q(
            "SELECT is_nullable FROM information_schema.columns WHERE table_name = :t AND column_name = 'tenant_id'",
            t=t,
        )
        assert nn == [("NO",)], t


def test_column_types_and_indexes() -> None:
    def typ(t: str, c: str) -> tuple:
        return _q(
            "SELECT data_type, numeric_precision, numeric_scale FROM information_schema.columns WHERE table_name = :t AND column_name = :c",
            t=t,
            c=c,
        )[0]

    for t, c in (
        ("mes_reticle", "max_shots"),
        ("mes_reticle", "shot_count"),
        ("mes_reticle_usage", "delta"),
        ("mes_reticle_usage", "count_after"),
        ("mes_reticle_usage", "estimated_delta"),
        ("mes_reticle_mount_log", "shots_at_unmount"),
    ):
        assert typ(t, c) == ("numeric", 18, 6), (t, c)
    for t, c in (
        ("mes_reticle_status_log", "at"),
        ("mes_reticle_usage", "occurred_at"),
        ("mes_reticle", "mounted_at"),
    ):
        assert typ(t, c)[0] == "timestamp with time zone"
    idx = {
        r[0]: r[1]
        for r in _q(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename LIKE 'mes_reticle%'"
        )
    }
    for name in (
        "uq_mes_reticle_incident_event",
        "uq_mes_reticle_usage_event",
        "uq_mes_reticle_mount_event",
        "uq_mes_reticle_inspection_event",
    ):
        assert "external_event_id IS NOT NULL" in idx[name], name
        assert "(tenant_id, source, external_event_id)" in idx[name], name
    assert "unmounted_at IS NULL" in idx["uq_mes_reticle_mount_open"]
    assert "(tenant_id, code)" in idx["uq_mes_reticle_0"]


def test_crud_read_only_fields_and_storage_location(
    client: TestClient, db: Session
) -> None:
    m = Mes(client, db)
    rt = m.post("reticle", {"code": "R1", "name": "r1", "storage_location": "S-01"})
    assert rt["status_code"] == "available" and rt["inspection_required"] is False
    assert rt["count_basis"] == "track_out" and rt["hold_reason"] is None
    assert rt["received_at"].endswith("Z")
    for k, v in (
        ("status_code", "on_hold"),
        ("hold_reason", "manual"),
        ("status_before_hold", "available"),
        ("inspection_required", True),
        ("shot_count", "1"),
        ("equipment_id", None),
    ):
        d = m.patch("reticle", rt["id"], {k: v}, 422)["detail"]
        assert d[0]["code"] == "read_only_field" and d[0]["loc"] == ["body", k], d
        d = m.post("reticle", {"code": "R2", "name": "r2", k: v}, 422)["detail"]
        assert d[0]["code"] == "read_only_field", d
    d = m.post(
        "reticle", {"code": "R3", "name": "r", "storage_location": "x" * 65}, 422
    )
    assert d["detail"][0]["loc"][-1] == "storage_location"
    m.post("reticle", {"code": "R1", "name": "dup"}, 409)
    # 唯一键只 (tenant, code)：revision 不进唯一键
    m.post("reticle", {"code": "R4", "name": "r", "revision": "A"})
    m.post("reticle", {"code": "R4", "name": "r", "revision": "B"}, 409)


def test_reticle_permissions_three_languages() -> None:
    for act in ("read", "write", "override"):
        d = permission_description(f"mes.reticle:{act}")
        assert d and len(d.split("|")) == 3 and "光罩" in d, d
