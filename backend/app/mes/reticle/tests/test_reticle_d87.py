"""D87：光罩 GET 详情 / 列表带 life_state；主数据通用 CRUD 写必须带 Idempotency-Key。"""

import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.reticle.tests.test_reticle_actions import R
from app.testing.mes import API


def test_life_state_in_get_and_list(client: TestClient, db: Session) -> None:
    r = R(client, db, max_shots="100")
    assert r.get()["life_state"] == "ok"
    d = client.get(f"{API}/reticle/{r.id}", headers=r.m.h).json()
    assert d["life_state"] == "ok" and "inspection_pending" not in d
    r.act("usage", {"delta": "95"})
    rows = client.get(f"{API}/reticle", headers=r.m.h).json()["data"]
    (row,) = [x for x in rows if x["id"] == r.id]
    assert row["life_state"] == "warning" and "inspection_pending" not in row
    r.act("usage", {"delta": "5"})
    assert client.get(f"{API}/reticle/{r.id}", headers=r.m.h).json()["life_state"] == (
        "reached"
    )
    # 通用子路径不被 /{rid} 挡住
    assert client.get(f"{API}/reticle/export", headers=r.m.h).status_code == 200


def test_master_writes_require_key(client: TestClient, db: Session) -> None:
    r = R(client, db)
    url = f"{API}/reticle/{r.id}"
    for method, u, body in (
        ("post", f"{API}/reticle", {"code": "X"}),
        ("patch", url, {"name": "x"}),
        ("delete", url, None),
    ):
        kw = {"json": body} if body is not None else {}
        resp = getattr(client, method)(u, headers=r.m.h, **kw)
        assert resp.status_code == 422, (method, resp.text)
        d = resp.json()["detail"][0]
        assert (d["type"], d["loc"]) == ("missing", ["header", "Idempotency-Key"])
    # D81：缺 key 先于 404；带 key 后 404
    missing = f"{API}/reticle/{uuid.uuid4()}"
    assert client.delete(missing, headers=r.m.h).status_code == 422
    assert client.delete(missing, headers=r.m.hk("reticle")).status_code == 404
    # 重放：同 key 同响应 + Idempotent-Replayed
    h = r.m.hk("reticle")
    a = client.patch(url, headers=h, json={"name": "d1"})
    b = client.patch(url, headers=h, json={"name": "d1"})
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    assert b.headers.get("Idempotent-Replayed") == "true"
    assert a.json()["life_state"] == "ok"


def test_openapi(client: TestClient) -> None:
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    one, lst = paths["/api/v1/mes/reticle/{rid}"], paths["/api/v1/mes/reticle"]
    for op in (one["patch"], one["delete"], lst["post"]):
        ps = {p["name"]: p for p in op["parameters"] if p["in"] == "header"}
        assert ps["Idempotency-Key"]["required"] is True
    for op in (one["get"], one["patch"], lst["post"]):
        sch = op["responses"]["200"]["content"]["application/json"]["schema"]
        assert sch["properties"]["life_state"]["enum"] == ["ok", "warning", "reached"]
    items = lst["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert "life_state" in items["properties"]["data"]["items"]["properties"]
