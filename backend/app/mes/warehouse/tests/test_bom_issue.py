"""BOM 生效规则、工单下达锁定 BOM、领料单确认过账与物料需求、机台上料区间冲突。"""

from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.planning.tests.test_wo import Fab
from app.testing.mes import API


def _msgs(r: Any) -> str:
    return " ".join(d["msg"] for d in r["detail"])


class Stock:
    """Fab（已激活产品与默认路线）+ 物料、工序，以及按需创建的物料批 / BOM。"""

    def __init__(self, client: TestClient, db: Session) -> None:
        self.f = f = Fab(client, db)
        self.m = m = f.m
        self.uom = m.fx("uom")
        mt = m.post(
            "material_type", {"code": "MT", "name": "mt", "category": "chemical"}
        )
        self.mat = m.post(
            "material",
            {
                "code": "M1",
                "name": "m1",
                "material_type_id": mt["id"],
                "uom_id": self.uom,
            },
        )
        self.op = m.post("operation", {"code": "OPX", "name": "x"})

    def lot(self, code: str, qty: float = 10, **kw: Any) -> dict[str, Any]:
        return self.m.post(
            "material_lot",
            {
                "code": code,
                "material_id": self.mat["id"],
                "qty_remaining": qty,
                "uom_id": self.uom,
                **kw,
            },
        )

    def bom(
        self, code: str = "B1", qty: float = 2, scrap: float = 10
    ) -> dict[str, Any]:
        b = self.m.post(
            "bom", {"code": code, "name": code, "product_id": self.f.product["id"]}
        )
        self.m.post(
            "bom_line",
            {
                "bom_id": b["id"],
                "operation_id": self.op["id"],
                "material_id": self.mat["id"],
                "qty": qty,
                "uom_id": self.uom,
                "qty_basis": "per_unit",
                "scrap_rate": scrap,
            },
        )
        return b

    def activate(self, b: dict[str, Any], status: int = 200) -> Any:
        m = self.m
        r = m.c.post(
            m.url("bom", b["id"], "status"), headers=m.h, json={"status": "active"}
        )
        assert r.status_code == status, r.text
        return r.json()

    def requirements(self, wo: dict[str, Any]) -> dict[str, Any]:
        r = self.m.c.get(
            f"{API}/material-issue/requirements/{wo['id']}", headers=self.m.h
        )
        assert r.status_code == 200, r.text
        return r.json()  # type: ignore[no-any-return]

    def issue(
        self, wo: dict[str, Any], code: str, *lines: tuple[dict[str, Any], float]
    ) -> Any:
        iss = self.m.post("material_issue", {"code": code, "work_order_id": wo["id"]})
        for lot, qty in lines:
            self.m.post(
                "material_issue_line",
                {
                    "material_issue_id": iss["id"],
                    "material_lot_id": lot["id"],
                    "qty": qty,
                },
            )
        return iss

    def act(self, iss: dict[str, Any], action: str, status: int = 200) -> Any:
        r = self.m.c.post(
            f"{API}/material-issue/{iss['id']}/transition",
            headers=self.m.h,
            json={"action": action},
        )
        assert r.status_code == status, r.text
        return r.json()


def test_bom_activation_rules(client: TestClient, db: Session) -> None:
    s = Stock(client, db)
    m = s.m
    b = m.post("bom", {"code": "B1", "name": "b", "product_id": s.f.product["id"]})
    r = m.c.post(
        m.url("bom", b["id"], "status"), headers=m.h, json={"status": "active"}
    )
    assert r.status_code == 422 and "add at least one line" in _msgs(r.json())
    for body, field in (({"qty": 0}, "qty"), ({"scrap_rate": 150}, "scrap_rate")):
        r = m.c.post(
            m.url("bom_line"),
            headers=m.h,
            json={
                "bom_id": b["id"],
                "operation_id": s.op["id"],
                "material_id": s.mat["id"],
                "qty": 1,
                "uom_id": s.uom,
                **body,
            },
        )
        assert r.status_code == 422 and field in _msgs(r.json())
    line = m.post(
        "bom_line",
        {
            "bom_id": b["id"],
            "operation_id": s.op["id"],
            "material_id": s.mat["id"],
            "qty": 2,
            "uom_id": s.uom,
        },
    )
    assert s.activate(b)["status"] == "active"
    # 生效后明细只读；同一产品不能同时有两个生效的 BOM
    r = m.c.patch(m.url("bom_line", line["id"]), headers=m.h, json={"qty": 3})
    assert r.status_code == 409
    b2 = s.bom("B2")
    assert "already active" in _msgs(s.activate(b2, 422))


def test_release_locks_active_bom(client: TestClient, db: Session) -> None:
    s = Stock(client, db)
    f = s.f
    before = f.act(f.wo(), "release")
    assert before["bom_id"] is None  # 没有生效 BOM 不拦截下达
    b = s.bom()
    s.activate(b)
    wo = f.act(f.wo(), "release")
    assert wo["bom_id"] == b["id"]
    # 之后换新版本生效，已下达工单仍用下达时的版本
    v2 = s.m.action("bom", b["id"], "new-version")
    s.activate(v2)
    assert s.m.list("work_order", q=wo["code"])["data"][0]["bom_id"] == b["id"]


def test_material_issue_flow(client: TestClient, db: Session) -> None:
    s = Stock(client, db)
    m, f = s.m, s.f
    s.activate(s.bom())
    wo = f.act(f.wo(planned_qty=50), "release")
    src = s.lot("ML1", 10)
    # 需求 = 2 × 50 ×（1 + 10%）
    assert s.requirements(wo)["lines"] == [
        {
            "material_id": s.mat["id"],
            "material": "M1",
            "uom": "FX-EA",
            "required": 110,
            "issued": 0,
            "short": 110,
        }
    ]
    iss = s.issue(wo, "ISS1", (src, 3))
    assert iss["issue_status"] == "draft"
    r = m.c.post(
        m.url("material_issue_line"),
        headers=m.h,
        json={"material_issue_id": iss["id"], "material_lot_id": src["id"], "qty": 11},
    )
    assert r.status_code == 422 and "has only 10" in _msgs(r.json())
    done = s.act(iss, "confirm")
    assert done["issue_status"] == "confirmed" and done["confirmed_by"]
    assert m.list("material_lot", q="ML1")["data"][0]["qty_remaining"] == 7
    child = m.list("material_lot", q="ISS1-1")["data"][0]
    assert child["qty_remaining"] == 3 and child["work_order_id"] == wo["id"]
    req = s.requirements(wo)["lines"][0]
    assert (req["issued"], req["short"]) == (3, 107)
    # 已确认的单据不能再改 / 再确认；已归属工单的批不能再被领
    r = m.c.patch(
        m.url("material_issue", iss["id"]), headers=m.h, json={"remarks": "x"}
    )
    assert r.status_code == 422
    assert "cannot confirm" in _msgs(s.act(iss, "confirm", 422))
    iss2 = m.post("material_issue", {"code": "ISS2", "work_order_id": wo["id"]})
    r = m.c.post(
        m.url("material_issue_line"),
        headers=m.h,
        json={
            "material_issue_id": iss2["id"],
            "material_lot_id": child["id"],
            "qty": 1,
        },
    )
    assert r.status_code == 422 and "not available" in _msgs(r.json())
    assert s.act(iss2, "cancel")["issue_status"] == "cancelled"
    # 没有明细的单据不能确认；未下达的工单不能领料
    iss3 = m.post("material_issue", {"code": "ISS3", "work_order_id": wo["id"]})
    assert "add at least one line" in _msgs(s.act(iss3, "confirm", 422))
    draft = f.wo()
    r = m.c.post(
        m.url("material_issue"),
        headers=m.h,
        json={"code": "ISS4", "work_order_id": draft["id"]},
    )
    assert r.status_code == 422 and "is draft" in _msgs(r.json())


def test_mount_rules(client: TestClient, db: Session) -> None:
    s = Stock(client, db)
    m = s.m
    eq = m.post("equipment", {"code": "EQ1", "name": "eq"})
    a, b = s.lot("ML-A"), s.lot("ML-B")

    def mount(lot: dict[str, Any], pos: str, at: str, off: str | None = None) -> Any:
        return m.c.post(
            m.url("equipment_material_mount"),
            headers=m.h,
            json={
                "equipment_id": eq["id"],
                "position": pos,
                "material_lot_id": lot["id"],
                "mounted_at": at,
                "unmounted_at": off,
            },
        )

    first = mount(a, "P1", "2026-01-01T00:00:00Z")
    assert first.status_code == 200, first.text
    busy = mount(b, "P1", "2026-02-01T00:00:00Z")  # P1 仍装着 ML-A
    assert busy.status_code == 422 and "already holds" in _msgs(busy.json())
    assert mount(b, "P2", "2026-02-01T00:00:00Z").status_code == 200
    m.patch(
        "equipment_material_mount",
        first.json()["id"],
        {"unmounted_at": "2026-01-15T00:00:00Z"},
    )
    assert mount(b, "P1", "2026-02-01T00:00:00Z").status_code == 200
    bad = mount(a, "P3", "2026-03-01T00:00:00Z", "2026-02-01T00:00:00Z")
    assert bad.status_code == 422 and "must be after" in _msgs(bad.json())
    empty = s.lot("ML-E", ml_status="empty")
    gone = mount(empty, "P4", "2026-03-01T00:00:00Z")
    assert gone.status_code == 422 and "not available" in _msgs(gone.json())
