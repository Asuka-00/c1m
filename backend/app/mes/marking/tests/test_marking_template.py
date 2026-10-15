"""P3-B1 打标模板（D79 / D81 / D89）。"""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.testing.mes import Mes

API = settings.API_V1_STR
URL = f"{API}/mes/marking-template"
LINES = ["{product_code}", "{date_code} {trace_code}"]


def _k(h: dict[str, str], key: str | None = None) -> dict[str, str]:
    return {**h, "Idempotency-Key": key or str(uuid.uuid4())}


def _member(m: Mes, roles: list[str]) -> dict[str, str]:
    name, pw = "mk_" + uuid.uuid4().hex[:8], uuid.uuid4().hex
    r = m.c.post(
        f"{API}/tenants/{m.tid}/members/new",
        headers=m.h,
        json={"username": name, "full_name": "x", "password": pw, "roles": roles},
    )
    assert r.status_code == 200, r.text
    tok = m.c.post(
        f"{API}/login/access-token", data={"username": name, "password": pw}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}", "X-Tenant-ID": str(m.tid)}


def _pc(m: Mes) -> dict[str, str]:
    """每次新建一对产品 + 客户（D89 补充二：产品+客户租户内唯一）。"""
    p = m.post("product", {"code": "P-MK-" + uuid.uuid4().hex[:6], "name": "prod"})
    c = m.post("customer", {"code": "C-MK-" + uuid.uuid4().hex[:6], "name": "cust"})
    return {"product_id": p["id"], "customer_id": c["id"]}


def _create(m: Mes, code: str = "MT1", **kw: Any) -> Any:
    r = m.c.post(
        URL,
        headers=_k(m.h),
        json={"code": code, "lines": LINES, **_pc(m), **kw},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _events(tid: Any) -> list[str]:
    with Session(engine) as s:
        s.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tid)}
        )
        return [
            r[0]
            for r in s.execute(
                text(
                    "SELECT action FROM mes_audit_log WHERE entity_type='marking_template'"
                    " AND action LIKE 'marking_template.%'"
                )
            ).all()
        ]


def test_version_flow(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    appr = _member(m, ["admin"])
    t = _create(m, description="d")
    assert t["description"] == "d"
    assert (t["version"], t["status"], t["approved_version"]) == (1, "draft", None)
    assert t["lines"] == LINES
    assert t["created_at"].endswith("Z") and t["created_by"]
    assert (t["product_name"], t["customer_name"]) == ("prod", "cust")
    rid = t["id"]
    # 草稿可编辑
    r = client.patch(f"{URL}/{rid}", headers=_k(m.h), json={"code": "MT1B"})
    assert r.status_code == 200 and r.json()["code"] == "MT1B"
    # 草稿存在 → 再建新版本 409 draft_exists
    r = client.post(f"{URL}/{rid}/versions", headers=_k(m.h))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "draft_exists"
    # 起草人自批 → 422 self_approval
    r = client.post(f"{URL}/{rid}/approve", headers=_k(m.h))
    assert r.status_code == 422
    d = r.json()["detail"][0]
    assert (d["type"], d["ctx"]) == ("value_error", {"reason": "self_approval"})
    r = client.post(f"{URL}/{rid}/approve", headers=_k(appr))
    assert r.status_code == 200, r.text
    j = r.json()
    assert (j["status"], j["approved_version"]) == ("approved", 1)
    assert j["versions"][0]["approved_at"].endswith("Z")
    # 已批准只读
    r = client.patch(f"{URL}/{rid}", headers=_k(m.h), json={"lines": ["x"]})
    assert r.status_code == 409
    assert set(r.json()["detail"]) >= {"code", "message"}
    assert r.json()["detail"]["code"] == "template_readonly"
    # 新版本 v2（201，复制 lines）→ 批准后 v1 自动 retired
    r = client.post(f"{URL}/{rid}/versions", headers=_k(m.h))
    assert r.status_code == 201 and r.json()["version"] == 2
    assert r.json()["lines"] == j["lines"]
    r = client.post(f"{URL}/{rid}/approve", headers=_k(appr))
    st = {v["version"]: v["status"] for v in r.json()["versions"]}
    assert st == {2: "approved", 1: "retired"}
    # 没有待批版本 → 409 invalid_transition
    r = client.post(f"{URL}/{rid}/approve", headers=_k(appr))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "invalid_transition"
    # D91 补充二：没有 retire 接口
    assert client.post(f"{URL}/{rid}/retire", headers=_k(appr)).status_code in (
        404,
        405,
    )
    r = client.patch(f"{URL}/{rid}", headers=_k(m.h), json={"lines": ["x"]})
    assert r.json()["detail"]["code"] == "template_readonly"
    assert _events(m.tid).count("marking_template.approved") == 2
    lst = client.get(URL, headers=m.h).json()
    assert lst["count"] == 1 and "versions" not in lst["data"][0]


def test_body_validation_and_order(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    ro = _member(m, ["member"])
    # 403 先于缺 key
    r = client.post(URL, headers=ro, json={})
    assert r.status_code == 403
    # 缺 key 先于 body
    r = client.post(URL, headers=m.h, json={})
    assert r.status_code == 422 and r.json()["detail"][0]["loc"] == [
        "header",
        "Idempotency-Key",
    ]
    # unknown_placeholder：每个一条
    bad = [
        "{lot_id}{foo}{bar}{foo}",
        "{baz}",
    ]
    r = client.post(URL, headers=_k(m.h), json={"code": "B", "lines": bad, **_pc(m)})
    assert r.status_code == 422
    ds = r.json()["detail"]
    assert [(d["loc"], d["ctx"]["placeholder"]) for d in ds] == [
        (["body", "lines", 0], "foo"),
        (["body", "lines", 0], "bar"),
        (["body", "lines", 1], "baz"),
    ]
    assert all(
        d["type"] == "value_error" and d["ctx"]["reason"] == "unknown_placeholder"
        for d in ds
    )
    # 长度
    # D89 第1条撤回：name / description 不在请求体，多余字段拒绝
    for k in ("name", "date_code_basis", "uses_bin"):
        r = client.post(
            URL, headers=_k(m.h), json={"code": "U", "lines": [], **_pc(m), k: "x"}
        )
        assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body", k]
    for k, n in (("code", 65), ("description", 301)):
        body = {"code": "C", "lines": [], **_pc(m), k: "x" * n}
        r = client.post(URL, headers=_k(m.h), json=body)
        assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body", k], k
    # body 422 先于 404
    r = client.patch(f"{URL}/{uuid.uuid4()}", headers=_k(m.h), json={"lines": bad})
    assert r.status_code == 422
    r = client.patch(f"{URL}/{uuid.uuid4()}", headers=_k(m.h), json={"lines": ["x"]})
    assert r.status_code == 404
    # 唯一 code
    d0 = _create(m, "DUP")
    dup = "A record with the same key already exists"
    r = client.post(URL, headers=_k(m.h), json={"code": "dup", "lines": [], **_pc(m)})
    assert r.status_code == 409 and r.json()["detail"] == dup
    pair = {"product_id": d0["product_id"], "customer_id": d0["customer_id"]}
    r = client.post(URL, headers=_k(m.h), json={"code": "DUP2", "lines": [], **pair})
    assert r.status_code == 409 and r.json()["detail"] == dup
    # D90-3：product_id / customer_id 不可改；同值视为没改
    other = _create(m, "DUP3")
    r = client.patch(f"{URL}/{other['id']}", headers=_k(m.h), json=pair)
    assert r.status_code == 422
    assert [(e["loc"], e["ctx"]["reason"]) for e in r.json()["detail"]] == [
        (["body", "product_id"], "immutable"),
        (["body", "customer_id"], "immutable"),
    ]
    same = {"product_id": other["product_id"], "customer_id": other["customer_id"]}
    r = client.patch(
        f"{URL}/{other['id']}", headers=_k(m.h), json={**same, "lines": ["x"]}
    )
    assert r.status_code == 200 and r.json()["lines"] == ["x"]
    # 幂等重放
    k = str(uuid.uuid4())
    body = {"code": "IDEM", "lines": LINES, **_pc(m)}
    a = client.post(URL, headers=_k(m.h, k), json=body)
    b = client.post(URL, headers=_k(m.h, k), json=body)
    assert a.status_code == b.status_code == 201 and a.json() == b.json()
    assert b.headers.get("Idempotent-Replayed") == "true"
    c = client.post(URL, headers=_k(m.h, k), json={**body, "code": "IDEM2"})
    assert c.status_code == 422
    assert c.json()["detail"]["code"] == "idempotency_key_reused"  # 本期对象格式
    # 无审批权限
    t = _create(m, "P")
    r = client.post(f"{URL}/{t['id']}/approve", headers=_k(ro))
    assert r.status_code == 403


def test_refs_and_line_type(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    pc = _pc(m)
    r = client.post(
        URL,
        headers=_k(m.h),
        json={
            "code": "NP",
            "lines": [],
            **pc,
            "product_id": str(uuid.uuid4()),
        },
    )
    assert r.status_code == 404 and r.json()["detail"]["code"] == "product_not_found"
    r = client.post(
        URL,
        headers=_k(m.h),
        json={"code": "L", "lines": [{"seq": 1, "content": "x"}], **pc},
    )
    assert r.status_code == 422 and r.json()["detail"][0]["loc"][:3] == [
        "body",
        "lines",
        0,
    ]
    t = _create(m, "NAMES")
    assert (t["product_name"], t["customer_name"]) == ("prod", "cust")


def test_detail_versions_and_readonly(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    t = _create(m, "DV")
    ap = _member(m, ["admin"])
    assert client.post(f"{URL}/{t['id']}/approve", headers=_k(ap)).status_code == 200
    r = client.patch(f"{URL}/{t['id']}", headers=_k(m.h), json={"lines": ["y"]})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "template_readonly"
    # D91 补充一：immutable 排在 404 之后、template_readonly 之前
    r = client.patch(
        f"{URL}/{t['id']}", headers=_k(m.h), json={"product_id": _pc(m)["product_id"]}
    )
    assert r.status_code == 422
    assert [(e["type"], e["loc"], e["ctx"]) for e in r.json()["detail"]] == [
        ("value_error", ["body", "product_id"], {"reason": "immutable"})
    ]
    assert client.post(f"{URL}/{t['id']}/versions", headers=_k(m.h)).status_code == 201
    d = client.get(f"{URL}/{t['id']}", headers=m.h).json()["data"]
    vs = d["versions"]
    assert [v["version"] for v in vs] == [2, 1]
    keys = {
        "version",
        "status",
        "created_by",
        "created_at",
        "approved_by",
        "approved_at",
    }
    assert all(keys <= set(v) for v in vs)
    assert vs[1]["status"] == "approved" and vs[1]["approved_at"].endswith("Z")


def test_cross_tenant_404(client: TestClient, db: Session) -> None:
    a, b = Mes(client, db), Mes(client, db)
    t = _create(a)
    assert client.get(f"{URL}/{t['id']}", headers=b.h).status_code == 404
    r = client.patch(f"{URL}/{t['id']}", headers=_k(b.h), json={"lines": ["x"]})
    assert r.status_code == 404
    r = client.post(f"{URL}/preview", headers=b.h, json={"template_id": t["id"]})
    assert r.status_code == 404
    assert client.get(URL, headers=b.h).json()["count"] == 0


def test_preview_validate(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    t = _create(m)
    for path in ("preview", "validate"):
        for body in ({}, {"template_id": t["id"], "lines": LINES}):
            r = client.post(f"{URL}/{path}", headers=m.h, json=body)
            assert r.status_code == 422, (path, body)
            d = r.json()["detail"][0]
            assert (d["type"], d["loc"], d["ctx"]) == (
                "value_error",
                ["body", "template_id"],
                {"reason": "exactly_one_of", "fields": ["template_id", "lines"]},
            )
        # 二选一 422 先于 404
        r = client.post(
            f"{URL}/{path}",
            headers=m.h,
            json={"template_id": str(uuid.uuid4()), "lines": []},
        )
        assert r.status_code == 422
        r = client.post(
            f"{URL}/{path}", headers=m.h, json={"template_id": str(uuid.uuid4())}
        )
        assert r.status_code == 404
    r = client.post(f"{URL}/preview", headers=m.h, json={"template_id": t["id"]})
    assert r.status_code == 200 and r.json()["template_id"] == t["id"]
    assert r.json()["lines"] == LINES
    r = client.post(
        f"{URL}/validate",
        headers=m.h,
        json={"lines": ["{x}{lot_id}{x}"]},
    )
    assert r.json() == {"valid": False, "unknown_placeholders": ["x"]}
    r = client.post(f"{URL}/validate", headers=m.h, json={"template_id": t["id"]})
    assert r.json() == {"valid": True, "unknown_placeholders": []}


def test_openapi_keys(client: TestClient) -> None:
    paths = client.get(f"{API}/openapi.json").json()["paths"]
    p = f"{API}/mes/marking-template"
    for path, meth in (
        (p, "post"),
        (p + "/{rid}", "patch"),
        (p + "/{rid}/versions", "post"),
        (p + "/{rid}/approve", "post"),
    ):
        ps = paths[path][meth]["parameters"]
        assert any(x["name"] == "Idempotency-Key" and x["required"] for x in ps), path
    for path in ("/preview", "/validate"):
        ps = paths[p + path]["post"].get("parameters", [])
        assert not any(x["name"] == "Idempotency-Key" for x in ps)
