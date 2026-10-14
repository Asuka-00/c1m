"""P3-B6（D74）：人员资质履历、受控写、过期拦截、到期汇总、迁移权限。"""

import uuid
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.mes.common.sitedate import site_today
from app.mes.execution import operator_qual as oq
from app.mes.execution.tests.test_exec import Line

API = f"{settings.API_V1_STR}/mes"
EXEC = f"{API}/exec"


def _me(f: Line) -> str:
    me = f.c.get(f"{settings.API_V1_STR}/users/me", headers=f.m.h).json()
    return str(me.get("username") or me["email"])


def _key(f: Line, k: str | None = None) -> dict[str, str]:
    return {**f.m.h, "Idempotency-Key": k or str(uuid.uuid4())}


def _events(f: Line, qid: str) -> list[str]:
    with Session(engine) as s:
        s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(f.m.tid)},
        )
        rows = s.execute(
            text(
                "SELECT action FROM mes_audit_log WHERE record_id = :r "
                "AND action LIKE 'operator_qual.%' ORDER BY created_at"
            ),
            {"r": qid},
        ).all()
    return [r[0] for r in rows]


def _hist(f: Line, qid: str, **p: Any) -> list[dict[str, Any]]:
    r = f.c.get(f"{EXEC}/operator-qual/{qid}/history", headers=f.m.h, params=p)
    assert r.status_code == 200, r.text
    return r.json()["rows"]  # type: ignore[no-any-return]


def _grant(f: Line, user: str, days: int | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "username": user,
        "operation_id": f.steps[10]["operation_id"],
    }
    if days is not None:
        body["expires_on"] = str(_today(f) + timedelta(days=days))
    return f.m.post("operator_qual", body)


def _today(f: Line) -> Any:
    with Session(engine) as s:
        return site_today(s, uuid.UUID(str(f.m.tid)))


def test_log_events_and_history(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    user = _me(f)
    q = _grant(f, user, 10)
    ex = f.m.qual_extra("renew 90d")
    f.m.patch(
        "operator_qual",
        q["id"],
        {"expires_on": str(_today(f) + timedelta(days=90)), **ex},
    )
    f.m.patch("operator_qual", q["id"], {"certified_on": str(_today(f))})
    f.m.patch(
        "operator_qual",
        q["id"],
        {"is_active": False, "reason_id": ex["reason_id"], "comment": "left"},
    )
    f.m.patch("operator_qual", q["id"], {"is_active": True})
    rows = _hist(f, q["id"])
    acts = [r["action"] for r in rows]
    assert acts[0] == "reactivated" and acts[1] == "deactivated"
    assert acts[2:] == ["changed", "renewed", "granted"]
    assert all(r["at"].endswith("Z") for r in rows), [r["at"] for r in rows]
    ren = next(r for r in rows if r["action"] == "renewed")
    assert ren["approved_by"] == ex["approved_by"] and ren["comment"] == "renew 90d"
    assert ren["reason_id"] == ex["reason_id"] and ren["username"] == user
    ev = _events(f, q["id"])
    for name in ("granted", "renewed", "changed", "deactivated"):
        assert f"operator_qual.{name}" in ev
    assert "operator_qual.reactivated" not in ev
    # 分页 + 403 先于 404
    assert len(_hist(f, q["id"], limit=1, offset=1)) == 1
    r = client.get(
        f"{EXEC}/operator-qual/{q['id']}/history", headers=f.m.h, params={"limit": 201}
    )
    assert r.status_code == 422 and r.json()["detail"][0]["ctx"]["max"] == 200
    r = client.get(f"{EXEC}/operator-qual/{uuid.uuid4()}/history", headers=f.m.h)
    assert r.status_code == 404


def test_validation_order(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    user = _me(f)
    q = _grant(f, user, 10)
    url = f"{API}/operator-qual/{q['id']}"
    new_exp = str(_today(f) + timedelta(days=60))
    # 缺 key → 422（先于 body）
    r = client.patch(url, headers=f.m.h, json={"expires_on": new_exp})
    assert r.status_code == 422 and r.json()["detail"][0]["loc"] == [
        "header",
        "Idempotency-Key",
    ]
    # 缺附加字段 → 422 missing（先于 404）
    r = client.patch(
        f"{API}/operator-qual/{uuid.uuid4()}",
        headers=_key(f),
        json={"expires_on": new_exp},
    )
    assert r.status_code == 422
    assert {tuple(d["loc"]) for d in r.json()["detail"]} == {
        ("body", "reason_id"),
        ("body", "comment"),
        ("body", "approved_by"),
    }
    r = client.patch(url, headers=_key(f), json={"is_active": False})
    assert {d["loc"][1] for d in r.json()["detail"]} == {"reason_id", "comment"}
    ex = f.m.qual_extra()
    r = client.patch(
        url, headers=_key(f), json={"expires_on": new_exp, **ex, "comment": "c" * 301}
    )
    assert r.status_code == 422 and r.json()["detail"][0]["ctx"]["max_length"] == 300
    # D85：self_approval 请求体阶段（先于 404）
    me_ex = {**ex, "approved_by": user}
    r = client.patch(
        f"{API}/operator-qual/{uuid.uuid4()}",
        headers=_key(f),
        json={"expires_on": new_exp, **me_ex},
    )
    assert r.status_code == 422
    d = r.json()["detail"][0]
    assert (d["loc"], d["ctx"]["reason"]) == (["body", "approved_by"], "self_approval")
    # 停用请求带 approved_by 同样拦
    r = client.patch(url, headers=_key(f), json={"is_active": False, **me_ex})
    assert r.json()["detail"][0]["ctx"]["reason"] == "self_approval"
    # POST 授予带 approved_by=自己 → self_approval
    r = client.post(
        f"{API}/operator-qual",
        headers=_key(f),
        json={
            "username": "x_" + uuid.uuid4().hex[:6],
            "operation_id": f.steps[10]["operation_id"],
            "approved_by": user,
        },
    )
    assert r.json()["detail"][0]["ctx"]["reason"] == "self_approval"
    # holder_approval：404 之后、409 之前
    holder = ex["approved_by"]
    hq = _grant(f, holder, 5)
    r = client.patch(
        f"{API}/operator-qual/{uuid.uuid4()}",
        headers=_key(f),
        json={"expires_on": new_exp, **ex},
    )
    assert r.status_code == 404
    r = client.patch(
        f"{API}/operator-qual/{hq['id']}",
        headers=_key(f),
        json={"expires_on": new_exp, **ex},
    )
    assert r.status_code == 422
    d = r.json()["detail"][0]
    assert (d["loc"], d["ctx"]["reason"]) == (
        ["body", "approved_by"],
        "holder_approval",
    )
    # POST：holder_approval 先于唯一冲突 409
    r = client.post(
        f"{API}/operator-qual",
        headers=_key(f),
        json={
            "username": holder,
            "operation_id": f.steps[10]["operation_id"],
            "approved_by": holder,
        },
    )
    assert r.status_code == 422
    assert r.json()["detail"][0]["ctx"]["reason"] == "holder_approval"
    # 停用 + 延期同时 → conflicting_fields（请求体阶段，先于 missing / 404）
    r = client.patch(
        f"{API}/operator-qual/{uuid.uuid4()}",
        headers=_key(f),
        json={"is_active": False, "expires_on": new_exp},
    )
    assert r.status_code == 422
    d = r.json()["detail"][0]
    assert (d["type"], d["loc"], d["ctx"]) == (
        "value_error",
        ["body", "is_active"],
        {"reason": "conflicting_fields", "fields": ["is_active", "expires_on"]},
    )
    # 授予不要求原因 / 批准人
    _grant(f, "plain_" + uuid.uuid4().hex[:6], None)
    # 重放：同 key 同结果，只写一条履历
    k = str(uuid.uuid4())
    a = client.patch(url, headers=_key(f, k), json={"expires_on": new_exp, **ex})
    b = client.patch(url, headers=_key(f, k), json={"expires_on": new_exp, **ex})
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    assert "idempotent-replayed" not in a.headers
    assert b.headers["Idempotent-Replayed"] == "true"
    assert [r["action"] for r in _hist(f, q["id"])].count("renewed") == 1
    # DELETE：缺 key 422 → 404 → 恒 409 referenced
    r = client.delete(url, headers=f.m.h)
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"] == ["header", "Idempotency-Key"]
    assert (
        client.delete(
            f"{API}/operator-qual/{uuid.uuid4()}", headers=_key(f)
        ).status_code
        == 404
    )
    r = client.delete(url, headers=_key(f))
    assert r.status_code == 409
    j = r.json()["detail"]
    assert j["code"] == "referenced" and j["ref_type"] == "operator_qual_log"
    assert j["ref_count"] == len(_hist(f, q["id"]))


def test_expired_move_in_blocked_and_scan(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    user = _me(f)
    (a,) = f.start(2)
    f.bind("move_in", ("operator_qualified", "block", {}))
    q = _grant(f, user, -1)
    r = f.stage(a, "move_in", 409, equipment_id=f.eq["id"])
    d = r["detail"]
    assert d["code"] == "check_blocked" and d["overridable"] is False
    (res,) = [x for x in d["results"] if x["check_type"] == "operator_qualified"]
    assert res["overridable"] is False and res["data"]["reason"] == "expired"
    assert res["data"]["expires_on"] == str(_today(f) - timedelta(days=1))
    assert res["ctx"] == {"qual_id": q["id"], "expires_on": res["data"]["expires_on"]}
    with Session(engine) as s:
        s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(f.m.tid)},
        )
        tid = uuid.UUID(str(f.m.tid))
        assert oq.expired_scan(s, tid) == 1
        assert oq.expired_scan(s, tid) == 0  # 去重
        s.commit()
    assert _events(f, q["id"]).count("operator_qual.expired") == 1
    # 不自动停用
    assert f.m.list("operator_qual", id=q["id"])["data"][0]["is_active"] is True


def test_expiring_and_meta(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    _grant(f, "u_far_" + uuid.uuid4().hex[:4], 100)
    near = _grant(f, "u_near", 3)
    _grant(f, "u_perm", None)
    r = client.get(f"{EXEC}/operator-qual/expiring", headers=f.m.h)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["warn_days"] == 30 and j["timezone"]
    assert [x["qual_id"] for x in j["rows"]] == [near["id"]] and j["rows"][0][
        "days_left"
    ] == 3
    r = client.get(
        f"{EXEC}/operator-qual/expiring", headers=f.m.h, params={"days": 365}
    )
    assert len(r.json()["rows"]) == 2
    for bad in ("0", "366", "x"):
        r = client.get(
            f"{EXEC}/operator-qual/expiring", headers=f.m.h, params={"days": bad}
        )
        assert r.status_code == 422 and r.json()["detail"][0]["ctx"] == {
            "min": 1,
            "max": 365,
        }
    f.bind("track_in", ("qual_expiry_notice", "warn", {"warn_days": 5}))
    meta = client.get(f"{API}/_meta", headers=f.m.h).json()
    (m,) = [e for e in meta["entities"] if e["code"] == "operator_qual"]
    assert m["warn_days"] == 5


def test_app_user_dml_on_log_table(db: Session) -> None:
    for p in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        ok = db.execute(
            text("SELECT has_table_privilege('app_user', 'mes_operator_qual_log', :p)"),
            {"p": p},
        ).scalar()
        assert ok, p


def test_excel_import_only_grants(client: TestClient, db: Session) -> None:
    """D88-3：导入只允许新建授予；改已有资质 is_active / expires_on 整行拒绝 use_api。"""
    f = Line(client, db)
    op_id = f.steps[10]["operation_id"]
    op = next(o for o in f.m.list("operation", limit=200)["data"] if o["id"] == op_id)
    exp = str(_today(f) + timedelta(days=10))
    q = f.m.post(
        "operator_qual", {"username": "imp_a", "operation_id": op_id, "expires_on": exp}
    )
    hdr = ["username", "operation", "expires_on", "is_active", "certified_on"]
    later = str(_today(f) + timedelta(days=99))

    def imp(*rows: list[Any], status: int = 200) -> Any:
        return f.m.import_rows("operator_qual", [hdr, *rows], status=status)

    for row, field in (
        (["imp_a", op["code"], later, None, None], "expires_on"),
        (["imp_a", op["code"], exp, "false", None], "is_active"),
    ):
        r = imp(["imp_new1", op["code"], exp, None, None], row, status=422)
        (e,) = r["detail"]["errors"]
        assert e["row"] == 3 and e["type"] == "value_error", e
        assert e["ctx"]["reason"] == "use_api" and field in e["ctx"]["fields"]
    # 整个导入回滚：新行未建，已有行未改
    assert f.m.list("operator_qual", username="imp_new1")["count"] == 0
    cur = f.m.list("operator_qual", id=q["id"])["data"][0]
    assert cur["expires_on"] == exp and cur["is_active"] is True
    # 新建授予 + 不改 is_active / expires_on 的已有行可导入
    res = imp(
        ["imp_new2", op["code"], exp, None, None],
        ["imp_a", op["code"], exp, "true", str(_today(f))],
    )
    assert res == {"created": 1, "updated": 1}
    acts = [r["action"] for r in _hist(f, q["id"])]
    assert "renewed" not in acts and "deactivated" not in acts
