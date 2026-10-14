"""P1 修复（bom.md §12）：BOM 接口严格载荷（未知 / 系统字段 422）、已有实体通用接口
不受影响（整行原样 PATCH 仍 200）、产品新版本复制 BOM 需 mes.bom:write（否则
warnings 带 bom_copy_skipped）。"""

from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.product.tests.test_bom import B, _member
from app.testing.mes import API, Mes

ROOT = API[:-4]


def _locs(r: Any) -> set[str]:
    return {d["loc"][-1] for d in r["detail"]}


def test_bom_payload_rejects_unwritable_fields(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    b = B(m)
    p = b.product("FG")
    v = b.bom(p)
    # 旧的 route_step_id（已改为 operation_id）不再静默忽略
    r = b.line(v, 10, 422, route_step_id=v["id"])
    assert _locs(r) == {"route_step_id"}
    ln = b.line(v, 10)
    r = m.patch("bom_line", ln["id"], {"qty": 2, "created_at": "2026-01-01"}, 422)
    assert _locs(r) == {"created_at"}
    r = m.post(
        "bom_line_substitute",
        {"bom_line_id": ln["id"], "material_id": b.mats[1]["id"], "foo": 1},
        422,
    )
    assert _locs(r) == {"foo"}
    for k, val in (("confirmed_by", "x"), ("id", v["id"]), ("status", "active")):
        assert _locs(m.patch("bom", v["id"], {k: val}, 422)) == {k}
    # 只传可写字段：正常
    assert m.patch("bom_line", ln["id"], {"qty": 3})["qty"] == 3


def test_existing_entity_full_row_patch_still_ok(
    client: TestClient, db: Session
) -> None:
    """回归：已有实体的通用增删改查保持原行为，GET 的整行原样 PATCH 回去仍 200。"""
    m = Mes(client, db)
    b = B(m)
    for ent, row in (
        ("material", b.mats[0]),
        ("product", b.product("FGX")),
        (
            "uom_conversion",
            m.post(
                "uom_conversion",
                {
                    "from_uom_id": b.g,
                    "to_uom_id": m.post(
                        "uom", {"code": "KG", "name": "kg", "dimension": "mass"}
                    )["id"],
                    "factor": 0.001,
                },
            ),
        ),
    ):
        g = client.get(m.url(ent, row["id"]), headers=m.h)
        assert g.status_code == 200, g.text
        full = g.json()
        r = client.patch(m.url(ent, row["id"]), headers=m.h, json=full)
        assert r.status_code == 200, (ent, r.text)


def test_product_new_version_bom_copy_needs_bom_write(
    client: TestClient, db: Session
) -> None:
    m = Mes(client, db)
    b = B(m)
    p1 = b.product("FG")
    v1 = b.bom(p1)
    b.line(v1, 10)
    b.act(v1, "activate")
    # 有 mes.bom:write：复制，warnings 为空
    p2 = m.action("product", p1["id"], "new-version")
    assert p2["warnings"] == []
    (nb,) = m.list("bom", product=p2["id"])["data"]
    b.act(nb, "activate")
    # 只有产品写权限、没有 mes.bom:write：不复制，warnings 带 bom_copy_skipped
    r = client.post(
        f"{ROOT}/tenants/{m.tid}/roles",
        headers=m.h,
        json={
            "name": "prod_writer",
            "title": "product writer",
            "permission_codes": ["mes.product:read", "mes.product:write"],
        },
    )
    assert r.status_code == 200, r.text
    hm = _member(client, db, m)
    uid = next(
        x["user_id"]
        for x in client.get(f"{ROOT}/tenants/{m.tid}/members", headers=m.h).json()[
            "data"
        ]
        if x["roles"] == ["member"]
    )
    r = client.put(
        f"{ROOT}/tenants/{m.tid}/members/{uid}/roles",
        headers=m.h,
        json={"roles": ["prod_writer"]},
    )
    assert r.status_code == 200, r.text
    r = client.post(f"{API}/product/{p2['id']}/new-version", headers=hm)
    assert r.status_code == 200, r.text
    p3 = r.json()
    (w,) = p3["warnings"]
    assert w["code"] == "bom_copy_skipped"
    assert m.list("bom", product=p3["id"])["count"] == 0
