"""完工入库：批次完工 → 待入库、入库单流转、部分入库、工单完工数累加、手动结案、权限、RLS。"""

from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution.tests.test_exec import API, Line
from app.platform.users import service as crud
from app.platform.users.schemas import UserCreate
from app.testing.mes import Mes
from app.testing.utils import (
    login_name,
    random_email,
    random_lower_string,
    username_for,
)


def _msgs(r: Any) -> str:
    return " ".join(d["msg"] for d in r["detail"])


class Store:
    """Line + 收货规则 / 仓库 / 库位，以及跑完全流程的批次。"""

    def __init__(self, client: TestClient, db: Session) -> None:
        self.f = f = Line(client, db)
        m = self.m = f.m
        m.post(
            "code_rule",
            {"code": "RCV", "name": "rcv", "target": "receipt", "pattern": "RCV{SEQ}"},
        )
        self.wh = m.post(
            "warehouse", {"code": "WH1", "name": "fg", "site_id": m.fx("site")}
        )
        self.loc = m.post(
            "storage_location",
            {"code": "L1", "name": "l1", "warehouse_id": self.wh["id"]},
        )

    def finished(self, *qty: int) -> list[dict[str, Any]]:
        lots = self.f.start(*qty)
        for lot in lots:
            for _ in range(4):  # 10 -> 20 -> SUB#10 -> 40 -> done
                self.f.run_step(lot)
        return [self.f.lot(x) for x in lots]

    def receipt(self, *lines: tuple[dict[str, Any], int, int]) -> dict[str, Any]:
        rc = self.m.post(
            "receipt", {"warehouse_id": self.wh["id"], "location_id": self.loc["id"]}
        )
        for lot, good, scrap in lines:
            self.m.post(
                "receipt_line",
                {
                    "receipt_id": rc["id"],
                    "lot_id": lot["id"],
                    "good_qty": good,
                    "scrap_qty": scrap,
                },
            )
        return rc

    def act(self, rc: dict[str, Any], action: str, status: int = 200) -> Any:
        return self.f.post(
            f"{API}/receipt/{rc['id']}/transition", {"action": action}, status
        )

    def wo(self) -> dict[str, Any]:
        return self.m.list("work_order")["data"][0]  # type: ignore[no-any-return]


def test_finish_partial_receipt_and_close(client: TestClient, db: Session) -> None:
    s = Store(client, db)
    lot, lot2 = s.finished(5, 3)
    assert lot["lot_status"] == "completed" and s.wo()["completed_qty"] == 0
    rc = s.receipt((lot, 2, 1))
    assert rc["code"] == "RCV0001" and rc["receipt_status"] == "draft"
    rc = s.m.list("receipt")["data"][0]
    assert (rc["lot_count"], rc["total_good"], rc["total_scrap"]) == (1, 2, 1)
    line = s.m.list("receipt_line", receipt=rc["id"])["data"][0]
    assert line["work_order_id"] == s.f.wo["id"]
    # 不能超出可入库数量
    r = s.m.post(
        "receipt_line",
        {"receipt_id": rc["id"], "lot_id": lot2["id"], "good_qty": 4},
        422,
    )
    assert "only 3 left" in _msgs(r)
    assert "add at least one lot" in _msgs(s.act(s.receipt(), "submit", 422))
    s.act(rc, "submit")
    # 已提交的数量被占用；草稿不可再改
    r = s.m.post(
        "receipt_line",
        {"receipt_id": rc["id"], "lot_id": lot2["id"], "good_qty": 1},
        422,
    )
    assert "draft" in _msgs(r)
    rc2 = s.receipt((lot, 2, 0))
    r = s.m.post(
        "receipt_line",
        {"receipt_id": rc2["id"], "lot_id": lot2["id"], "good_qty": 3},
    )
    assert "only 2 left" in _msgs(
        s.m.patch("receipt_line", r["id"], {"lot_id": lot["id"], "good_qty": 3}, 422)
    )
    s.m.delete("receipt", rc2["id"])
    s.m.delete("receipt", rc["id"], 422)  # 非草稿不可删除
    out = s.act(rc, "confirm")
    assert out["receipt_status"] == "confirmed" and out["confirmed_by"]
    lot = s.f.lot(lot)
    assert lot["lot_status"] == "completed" and lot["received_qty"] == 3
    assert lot["scrapped_qty"] == 1 and s.wo()["completed_qty"] == 2
    s.act(rc, "cancel", 422)
    # 剩余部分入库 → 批次已入库并关闭
    rc3 = s.receipt((lot, 2, 0), (lot2, 3, 0))
    s.act(rc3, "submit")
    # 结案前批次必须全部入库
    s.f.post(f"{API}/work-order/{s.f.wo['id']}/transition", {"action": "complete"})
    r = s.f.post(
        f"{API}/work-order/{s.f.wo['id']}/transition", {"action": "close"}, 422
    )
    assert "awaiting receipt" in _msgs(r)
    s.act(rc3, "confirm")
    lot = s.f.lot(lot)
    assert lot["lot_status"] == "stored" and lot["stored_at"]
    assert s.f.lot(lot2)["lot_status"] == "stored"
    assert s.wo()["completed_qty"] == 7
    acts = [
        h["action"]
        for h in s.m.list("lot_history", lot=lot["id"], sort_by="at", page_size=100)[
            "data"
        ]
    ]
    assert acts.count("receive") == 2
    # 已入库批次不可再入库
    r = s.m.post(
        "receipt_line",
        {"receipt_id": s.receipt()["id"], "lot_id": lot["id"], "good_qty": 1},
        422,
    )
    assert "not finished" in _msgs(r)
    w = s.f.post(f"{API}/work-order/{s.f.wo['id']}/transition", {"action": "close"})
    assert w["wo_status"] == "closed" and w["completed_qty"] == 7


def test_unfinished_lot_reject_cancel_location(client: TestClient, db: Session) -> None:
    s = Store(client, db)
    (wip,) = s.f.start(2)
    rc = s.receipt()
    r = s.m.post(
        "receipt_line",
        {"receipt_id": rc["id"], "lot_id": wip["id"], "good_qty": 1},
        422,
    )
    assert "not finished" in _msgs(r)
    (lot,) = s.finished(2)
    s.m.post(
        "receipt_line", {"receipt_id": rc["id"], "lot_id": lot["id"], "good_qty": 2}
    )
    s.act(rc, "submit")
    assert s.act(rc, "reject")["receipt_status"] == "draft"
    s.m.patch("receipt", rc["id"], {"remarks": "fixed"})
    assert s.act(rc, "cancel")["receipt_status"] == "cancelled"
    assert s.f.lot(lot)["received_qty"] == 0
    # 库位必须属于所选仓库
    wh2 = s.m.post("warehouse", {"code": "WH2", "name": "x", "site_id": s.m.fx("site")})
    r = s.m.post(
        "receipt", {"warehouse_id": wh2["id"], "location_id": s.loc["id"]}, 422
    )
    assert "does not belong" in _msgs(r)
    assert s.m.list("storage_location", warehouse=s.wh["id"])["count"] == 1


def test_permissions_and_rls(client: TestClient, db: Session) -> None:
    s = Store(client, db)
    (lot,) = s.finished(1)
    rc = s.receipt((lot, 1, 0))
    meta = client.get(f"{API}/_meta", headers=s.m.h).json()
    assert {"mes.wh:read", "mes.wh:write", "mes.wh:confirm"} <= set(meta["perms"])
    email, pw = random_email(), random_lower_string()
    crud.create_user(
        session=db,
        user_create=UserCreate(email=email, username=username_for(email), password=pw),
    )
    client.post(
        f"{API[:-4]}/tenants/{s.m.tid}/members",
        headers=s.m.h,
        json={"username": login_name(email), "roles": ["member"]},
    )
    tok = client.post(
        f"{API[:-4]}/login/access-token",
        data={"username": login_name(email), "password": pw},
    ).json()["access_token"]
    hm = {"Authorization": f"Bearer {tok}", "X-Tenant-ID": s.m.tid}
    assert client.get(s.m.url("receipt"), headers=hm).json()["count"] == 1
    for a in ("submit", "confirm"):
        r = client.post(
            f"{API}/receipt/{rc['id']}/transition", headers=hm, json={"action": a}
        )
        assert r.status_code == 403
    r = client.get(f"{API}/receipt/receivable/{lot['id']}", headers=s.m.h).json()
    assert r["receivable_qty"] == 1 and r["pending_qty"] == 0  # 草稿不占用
    other = Mes(client, db)
    assert other.list("receipt")["count"] == 0
    assert other.list("warehouse")["count"] == 0
