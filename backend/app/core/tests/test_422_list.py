"""D65 补充：所有 422 的 detail 都是列表（不再有字符串 detail）。"""

import ast
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.mes.alarm.tests.test_alarm import _line

APP = Path(__file__).resolve().parents[2]
MES = f"{settings.API_V1_STR}/mes"


def _is_422(call: ast.Call) -> bool:
    args = [*call.args[:1], *(k.value for k in call.keywords if k.arg == "status_code")]
    return any(isinstance(a, ast.Constant) and a.value == 422 for a in args)


def _detail(call: ast.Call) -> ast.expr | None:
    for k in call.keywords:
        if k.arg == "detail":
            return k.value
    return call.args[1] if len(call.args) > 1 else None


def test_no_string_detail_422_in_source() -> None:
    bad = []
    for p in APP.rglob("*.py"):
        if "tests" in p.parts or "alembic" in p.parts:
            continue
        for n in ast.walk(ast.parse(p.read_text())):
            if (
                isinstance(n, ast.Call)
                and getattr(n.func, "id", getattr(n.func, "attr", ""))
                == "HTTPException"
                and _is_422(n)
            ):
                d = _detail(n)
                if isinstance(d, ast.Constant | ast.JoinedStr):
                    bad.append(f"{p.relative_to(APP)}:{n.lineno}")
    assert not bad, bad


def test_endpoints_return_list_detail(client: TestClient, db: Session) -> None:
    f = _line(client, db)
    h = f.m.h
    url = f"{MES}/exec/reports/oee-trend"
    r = client.get(
        url, headers=h, params={"date_from": "2026-01-01", "date_to": "2026-06-01"}
    )
    assert r.status_code == 422
    assert r.json()["detail"] == [
        {
            "loc": ["query", "date_to"],
            "msg": "range too long (max 92 days)",
            "type": "date_range_too_large",
            "code": "date_range_too_large",
            "ctx": {"max_days": 92},
        }
    ]
    r = client.get(
        url, headers=h, params={"date_from": "2026-02-01", "date_to": "2026-01-01"}
    )
    assert r.status_code == 422
    assert r.json()["detail"][0]["code"] == "date_range_invalid"
    r = client.get(
        f"{MES}/eqp/mount/at",
        headers=h,
        params={"eq_id": f.eq["id"], "at": "2026-01-01T00:00:00"},
    )
    assert r.status_code == 422, r.text
    d = r.json()["detail"][0]
    assert d["loc"] == ["query", "at"] and d["code"] == "timezone_required"
    r = client.get(f"{MES}/alarm-code/distinct/severity", headers=h)
    assert r.status_code == 422, r.text
    d = r.json()["detail"][0]
    assert d["loc"] == ["path", "field"] and d["code"] == "not_text_filter"
    # 原生 RequestValidationError（路径 / 查询 / 请求体）也带 code = type
    r = client.get(f"{MES}/alarm-code/not-a-uuid", headers=h)
    assert r.status_code == 422
    d = r.json()["detail"][0]
    assert d["loc"] == ["path", "rid"] and d["code"] == d["type"]
    r = client.get(f"{MES}/alarm-code", headers=h, params={"page": "x"})
    d = r.json()["detail"][0]
    assert d["loc"][0] == "query" and d["code"] == d["type"]
    r = client.post(f"{MES}/alarm-code", headers=h, content=b"{bad")
    d = r.json()["detail"][0]
    assert d["loc"] == ["body"] and d["code"] == "json_invalid"
    # http_422 未带专用码的项：code = type
    r = client.get(f"{MES}/alarm-code", headers=h, params={"has_migration_note": "x"})
    d = r.json()["detail"][0]
    assert d["loc"] == ["query", "has_migration_note"] and d["code"] == "value_error"


def test_every_422_item_has_code(client: TestClient, db: Session) -> None:
    """扫描一组典型 422：detail 必为列表，每项都有 loc / msg / type / code。"""
    f = _line(client, db)
    h = f.m.h
    calls = [
        ("get", f"{MES}/alarm-code", {"params": {"sort_by": "zz"}}),
        ("get", f"{MES}/lot", {"params": {"lot_status": "zz"}}),
        ("get", f"{MES}/equipment/xx", {}),
        ("post", f"{MES}/alarm-code", {"json": {"foo": 1}}),
        ("post", f"{MES}/alarm-code", {"json": [1]}),
        ("get", f"{MES}/exec/customer-lots", {}),
        ("get", f"{MES}/eqp/mount/at", {"params": {"eq_id": f.eq["id"], "at": "x"}}),
    ]
    for m, u, kw in calls:
        r = getattr(client, m)(u, headers=h, **kw)
        assert r.status_code == 422, (u, r.text)
        d = r.json()["detail"]
        assert isinstance(d, list) and d, (u, d)
        for x in d:
            assert {"loc", "msg", "type", "code"} <= set(x), (u, x)
            assert x["loc"][0] in ("body", "query", "path"), (u, x)


def test_meta_open_to_eap_service(client: TestClient, db: Session) -> None:
    from app.mes.alarm.tests.test_alarm import _setup
    from app.mes.alarm.tests.test_eap_events import _account

    f, _, _ = _setup(client, db)
    svc = _account(client, db, f, "eap_service")
    assert client.get(f"{MES}/_meta", headers=svc).status_code == 200
