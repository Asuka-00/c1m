"""P3-B5 CT / Move 报表（D73 + 补充 T5-1/2/3）：口径、站点时区分日、参数校验、权限。"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution import ct_move
from app.mes.execution.tests.test_exec import EXEC, Line
from app.mes.product.tests.test_bom import _member

URL = f"{EXEC}/reports/ct-move"
TPE = ZoneInfo("Asia/Taipei")
RUN = ("move_in", "track_in", "track_out")


def t(d: int, hh: int, mm: int = 0) -> datetime:
    """2026-03-<d> hh:mm 台北时间。"""
    return datetime(2026, 3, d, hh, mm, tzinfo=TPE)


def _get(f: Line, status: int = 200, h: Any = None, **params: Any) -> Any:
    r = f.c.get(URL, headers=h or f.m.h, params=params)
    assert r.status_code == status, r.text
    return r.json()


def _set(f: Line, lot: Any, at: datetime, action: str, seq: int | None = None) -> None:
    q = "UPDATE mes_lot_history SET at = :at WHERE lot_id = :l AND action = :a"
    p: dict[str, Any] = {"at": at, "l": lot["id"], "a": action}
    if seq is not None:
        q += " AND step_seq = :s"
        p["s"] = seq
    f.sql(q, **p)


def _step(f: Line, lot: Any, seq: int, out: datetime) -> None:
    """把某工步的进站 / 上机 / 下机放在出站前，出站时间设为 ``out``。"""
    for i, a in enumerate(RUN):
        _set(f, lot, out - timedelta(minutes=30 - i * 10), a, seq)
    _set(f, lot, out, "move_out", seq)


def _scene(f: Line) -> tuple[Any, Any]:
    """a(3 片)：开批 03-10 01:00，OP1 出站 03:00，Hold 04:00–05:00，OP2 出站 08:30。
    b(2 片)：开批 03-09 23:30，OP1 出站 03-10 00:30。"""
    a, b = f.start(3, 2)
    f.run_step(a)
    f.post(f"{EXEC}/lots/{a['id']}/hold", {"reason_id": f.reasons["hold"]["id"]})
    (hid,) = f.sql("SELECT id FROM mes_lot_hold WHERE lot_id = :l", l=a["id"])
    f.post(f"{EXEC}/holds/{hid[0]}/release", {"reason_id": f.reasons["release"]["id"]})
    f.run_step(a)
    f.run_step(b)
    _set(f, a, t(10, 1), "start")
    _step(f, a, 10, t(10, 3))
    _set(f, a, t(10, 4), "hold")
    _set(f, a, t(10, 5), "release")
    f.sql(
        "UPDATE mes_lot_hold SET held_at = :h, released_at = :r WHERE lot_id = :l",
        h=t(10, 4),
        r=t(10, 5),
        l=a["id"],
    )
    _step(f, a, 20, t(10, 8, 30))
    _set(f, b, t(9, 23, 30), "start")
    _step(f, b, 10, t(10, 0, 30))
    return a, b


def test_ct_move_figures(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    _scene(f)
    r = _get(f, date_from="2026-03-09", date_to="2026-03-11", junk="x")
    assert (r["date_from"], r["date_to"], r["timezone"]) == (
        "2026-03-09",
        "2026-03-11",
        "Asia/Taipei",
    )
    assert [d["day"] for d in r["trend"]] == ["2026-03-09", "2026-03-10", "2026-03-11"]
    empty = {
        "moves": 0,
        "move_qty": 0,
        "rework_moves": 0,
        "rework_move_qty": 0,
        "rework_qty": 0,
        "ct_avg_hours": None,
        "hold_hours": None,
    }
    assert r["trend"][0] == {"day": "2026-03-09", **empty}
    assert r["trend"][2] == {"day": "2026-03-11", **empty}
    d10 = r["trend"][1]
    assert (d10["moves"], d10["move_qty"]) == (3, 8)
    # CT：b 1h、a@OP1 2h、a@OP2 5.5h（不扣 Hold）→ 平均 2.8333
    assert d10["ct_avg_hours"] == "2.83" and d10["hold_hours"] == "0.33"
    assert r["total"] == {k: v for k, v in d10.items() if k != "day"}
    assert "ct_p50_hours" not in r["total"] and "wip_lots" not in r["total"]
    ops = {o["operation"]: o for o in r["by_operation"]}
    assert [o["operation"] for o in r["by_operation"]][:2] == ["OP1", "OP2"]
    op1, op2 = ops["OP1"], ops["OP2"]
    assert (op1["moves"], op1["move_qty"], op1["operation_name"]) == (2, 5, "o1")
    assert (op1["ct_avg_hours"], op1["ct_p50_hours"], op1["ct_p90_hours"]) == (
        "1.50",
        "1.50",
        "1.90",
    )
    assert op1["hold_hours"] == "0.00"
    assert (op2["moves"], op2["move_qty"], op2["ct_avg_hours"]) == (1, 3, "5.50")
    assert (op2["ct_p50_hours"], op2["ct_p90_hours"], op2["hold_hours"]) == (
        "5.50",
        "5.50",
        "1.00",
    )
    # 在制（03-11 日末）：b 在 OP2 等待；a 已进子流程 OP4
    assert (op2["wip_lots"], op2["on_hold_lots"], op2["on_hold_qty"]) == (1, 0, 0)
    assert op1["wip_lots"] == 0
    assert ops["OP4"]["wip_lots"] == 1 and ops["OP4"]["moves"] == 0
    assert ops["OP4"]["ct_avg_hours"] is None
    # 过滤：工序 / 产品
    r1 = _get(
        f,
        date_from="2026-03-10",
        date_to="2026-03-10",
        operation_id=op2["operation_id"],
    )
    assert [o["operation"] for o in r1["by_operation"]] == ["OP2"]
    assert r1["total"]["moves"] == 1 and r1["total"]["ct_avg_hours"] == "5.50"
    r2 = _get(
        f, date_from="2026-03-10", date_to="2026-03-10", product_id=f.product["id"]
    )
    assert r2["total"]["moves"] == 3


def test_wip_point_in_time_and_hold(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    a, b = _scene(f)
    # 03-09 日末：a 尚未开批；b 已开批，停在 OP1
    r = _get(f, date_from="2026-03-09", date_to="2026-03-09")
    assert [(o["operation"], o["wip_lots"]) for o in r["by_operation"]] == [("OP1", 1)]
    # Hold 跨 03-10 日末：含在 wip（T5-2），另计 on_hold
    f.post(f"{EXEC}/lots/{b['id']}/hold", {"reason_id": f.reasons["hold"]["id"]})
    f.sql(
        "UPDATE mes_lot_hold SET held_at = :h WHERE lot_id = :l AND released_at IS NULL",
        h=t(10, 12),
        l=b["id"],
    )
    _set(f, b, t(10, 12), "hold")
    r = _get(f, date_from="2026-03-10", date_to="2026-03-10")
    op2 = next(o for o in r["by_operation"] if o["operation"] == "OP2")
    assert (op2["wip_lots"], op2["on_hold_lots"], op2["on_hold_qty"]) == (1, 1, 2)


def test_rework_route_and_rework_qty(client: TestClient, db: Session) -> None:
    f = Line(client, db, {20: {"rework_return": "same_step"}})
    (c,) = f.start(2)
    f.run_step(c)  # OP1 -> 20
    f.stage(c, "move_in", equipment_id=f.eq["id"])
    f.stage(c, "track_in", equipment_id=f.eq["id"])
    f.stage(c, "track_out")
    f.stage(c, "move_out", rework=True)  # 普通工步出站 → 正常 move
    f.run_step(c)  # 返工路线 RW#10（OP5）出站 → rework move
    f.sql(
        "UPDATE mes_lot_history SET at = :at WHERE lot_id = :l",
        at=t(10, 9),
        l=c["id"],
    )
    # 普通工步下机带出的返工片（履历 rework + unit_id）→ rework_qty
    (w,) = f.sql("SELECT id FROM mes_wafer WHERE lot_id = :l LIMIT 1", l=c["id"])
    f.sql(
        "INSERT INTO mes_lot_history (id, tenant_id, lot_id, unit_id, action, "
        "route_step_id, step_seq, operation_id, qty, at) "
        "SELECT gen_random_uuid(), tenant_id, lot_id, :w, 'rework', route_step_id, "
        "step_seq, operation_id, 1, at FROM mes_lot_history "
        "WHERE lot_id = :l AND action = 'move_out' AND step_seq = 20",
        w=w[0],
        l=c["id"],
    )
    r = _get(f, date_from="2026-03-10", date_to="2026-03-10")
    tot = r["total"]
    assert (tot["moves"], tot["move_qty"]) == (2, 4)
    assert (tot["rework_moves"], tot["rework_move_qty"], tot["rework_qty"]) == (1, 2, 1)
    ops = {o["operation"]: o for o in r["by_operation"]}
    assert ops["OP5"]["rework_moves"] == 1 and ops["OP5"]["moves"] == 0
    assert ops["OP5"]["ct_avg_hours"] is None  # 返工出站不计 CT
    assert ops["OP2"]["rework_qty"] == 1 and ops["OP2"]["moves"] == 1
    # D73 补充二：带 rework 离开主路线的出站计 move，但不进 CT / Hold 样本
    assert ops["OP2"]["ct_avg_hours"] is None and ops["OP2"]["hold_hours"] is None
    # 返工回到 20 后再出站：该工步 CT 以这次为准，从返工路线出站（回到工步）起算
    f.run_step(c)
    f.sql(
        "UPDATE mes_lot_history SET at = :at WHERE lot_id = :l AND at > :t9",
        at=t(10, 11),
        l=c["id"],
        t9=t(10, 9),
    )
    r = _get(f, date_from="2026-03-10", date_to="2026-03-10")
    op2 = next(o for o in r["by_operation"] if o["operation"] == "OP2")
    assert op2["moves"] == 2 and op2["ct_avg_hours"] == "2.00"
    assert op2["hold_hours"] == "0.00"
    assert r["trend"][0]["rework_qty"] == 1


@pytest.mark.parametrize(
    ("at", "day"),
    [
        (t(10, 0, 30), "2026-03-10"),  # UTC 03-09 16:30
        (t(10, 7, 59), "2026-03-10"),  # UTC 03-09 23:59
        (t(9, 23, 59), "2026-03-09"),
    ],
    ids=["0030", "0759", "2359"],
)
def test_site_day_bucket(
    client: TestClient, db: Session, at: datetime, day: str
) -> None:
    f = Line(client, db)
    (a,) = f.start(1)
    f.run_step(a)
    _set(f, a, at - timedelta(hours=1), "start")
    _step(f, a, 10, at)
    r = _get(f, date_from="2026-03-09", date_to="2026-03-10")
    got = {d["day"]: d["moves"] for d in r["trend"]}
    assert got == {
        "2026-03-09": int(day == "2026-03-09"),
        "2026-03-10": int(day == "2026-03-10"),
    }
    assert r["total"]["ct_avg_hours"] == "1.00"
    # 只查另一天时不计入（日界按站点时区，半开区间）
    other = "2026-03-09" if day == "2026-03-10" else "2026-03-10"
    assert _get(f, date_from=other, date_to=other)["total"]["moves"] == 0


def test_validation_and_permission(client: TestClient, db: Session) -> None:
    f = Line(client, db)

    def err(status: int = 422, **p: Any) -> Any:
        d = _get(f, status, **p)["detail"]
        return d[0] if isinstance(d, list) else d

    e = err(date_to="2026-03-01")
    assert (e["type"], e["loc"]) == ("missing", ["query", "date_from"])
    assert err(date_from="2026-03-01")["loc"] == ["query", "date_to"]
    for bad in ("2026-3-1", "2026/03/01", "20260301", "2026-02-30", "2026-W10-1"):
        e = err(date_from=bad, date_to="2026-03-01")
        assert (e["type"], e["loc"]) == ("value_error", ["query", "date_from"]), bad
    e = err(date_from="2026-03-02", date_to="2026-03-01")
    assert e["type"] == "value_error" and e["ctx"] == {"reason": "range_inverted"}
    r = _get(f, date_from="2026-03-01", date_to="2026-03-01")  # from == to：当天
    assert [d["day"] for d in r["trend"]] == ["2026-03-01"]
    e = err(date_from="2026-01-01", date_to="2026-04-03")  # 93 天
    assert e["type"] == "date_range_too_large" and e["ctx"] == {"max_days": 92}
    r = _get(f, date_from="2026-01-01", date_to="2026-04-02")  # 正好 92 天
    assert len(r["trend"]) == 92
    rid = str(uuid.uuid4())
    d = _get(f, 404, date_from="2026-03-01", date_to="2026-03-01", operation_id=rid)
    assert d["detail"]["code"] == "operation_not_found" and d["detail"]["message"]
    d = _get(f, 404, date_from="2026-03-01", date_to="2026-03-01", product_id=rid)
    assert d["detail"]["code"] == "product_not_found"
    e = err(date_from="2026-03-01", date_to="2026-03-01", operation_id="nope")
    assert (e["type"], e["loc"]) == ("value_error", ["query", "operation_id"])
    # 其他租户的工序：404
    g = Line(client, db)
    d = _get(
        f,
        404,
        date_from="2026-03-01",
        date_to="2026-03-01",
        operation_id=g.ops[0]["id"],
    )
    assert d["detail"]["code"] == "operation_not_found"
    d = _get(
        f,
        404,
        date_from="2026-03-01",
        date_to="2026-03-01",
        product_id=g.product["id"],
    )
    assert d["detail"]["code"] == "product_not_found"
    # 无 mes.exec:read：403（先于参数校验）
    hm = _member(client, db, f.m)
    from app.platform.tenants.service import TenantContext

    orig = TenantContext.can

    def deny(self: Any, p: str) -> bool:
        return p != "mes.exec:read" and orig(self, p)

    mp = pytest.MonkeyPatch()
    mp.setattr(TenantContext, "can", deny)
    try:
        r403 = f.c.get(URL, headers=hm, params={"date_from": "bad"})
        assert r403.status_code == 403 and "loc" not in r403.text
    finally:
        mp.undo()


def test_percentile_and_rounding() -> None:
    xs = [Decimal(x) for x in (1, 2, 3, 4)]
    assert ct_move.percentile(xs, Decimal("0.5")) == Decimal("2.5")
    assert ct_move.percentile(xs, Decimal("0.9")) == Decimal("3.7")
    assert ct_move.percentile([], Decimal("0.5")) is None
    assert ct_move.hours(Decimal(18)) == "0.01"  # 0.005 h → ROUND_HALF_UP
    assert ct_move.hours(Decimal(17)) == "0.00"
    assert ct_move.hours(None) is None


def test_anchor_inherit_and_merge() -> None:
    """子批继承母批拆分前最近起点；合批取自身与各源批最早起点。"""
    an = ct_move._Anchors(None, uuid.uuid4(), datetime(2027, 1, 1, tzinfo=UTC))  # type: ignore[arg-type]
    T = lambda h: datetime(2026, 3, 10, h, tzinfo=UTC)  # noqa: E731
    P, C, S, X = "P", "C", "S", "X"
    an.ev = {
        P: [(T(1), "pos", None), (T(3), "pos", None)],
        C: [(T(4), "inherit", P)],
        S: [(T(2), "pos", None)],
        X: [(T(0), "pos", None), (T(5), "merge", C), (T(5), "merge", S)],
    }
    assert an.at(C, T(6)) == T(3)
    assert an.at(C, T(4)) is None  # 拆分前子批不存在
    assert an.at(P, T(2)) == T(1)
    assert an.at(X, T(7)) == T(0)  # min(X 自身 0 点, C 继承 3 点, S 2 点)
    an.ev[X] = [(T(4), "pos", None), (T(5), "merge", S)]
    assert an.at(X, T(7)) == T(2)


def test_menu_key() -> None:
    from app.platform.menus.service import menu_keys

    it = next(r for r in menu_keys()["items"] if r["key"] == "mes-ct-move-report")
    assert it["component"] == "mes-page:ct-move-report"
    assert it["permission"] == "mes.exec:read" and it["parent"] == "g-wip"
    assert date(2026, 3, 10) == t(10, 0).date()


def test_wip_jump_next_day_stays_on_origin(client: TestClient, db: Session) -> None:
    """P2-1：date_to 当天停在 OP2，次日跳站到 40 并进站 → date_to 的在制仍算 OP2。"""
    f = Line(client, db)
    (a,) = f.start(2)
    f.run_step(a)  # -> 20 (OP2)
    jr = f.m.post("reason_code", {"code": "JMP", "name": "j", "reason_type": "jump"})
    f.post(
        f"{EXEC}/lots/{a['id']}/jump",
        {"to_step_id": f.steps[40]["id"], "reason_id": jr["id"]},
    )
    f.stage(a, "move_in", equipment_id=f.eq["id"])
    _set(f, a, t(10, 1), "start")
    _step(f, a, 10, t(10, 3))
    _set(f, a, t(11, 9), "jump")
    _set(f, a, t(11, 9, 30), "move_in", 40)
    r = _get(f, date_from="2026-03-10", date_to="2026-03-10")
    w = {o["operation"]: o["wip_lots"] for o in r["by_operation"]}
    assert w.get("OP2") == 1 and not w.get("OP3"), r["by_operation"]
    r = _get(f, date_from="2026-03-11", date_to="2026-03-11")
    w = {o["operation"]: o["wip_lots"] for o in r["by_operation"]}
    assert w.get("OP3") == 1 and not w.get("OP2"), r["by_operation"]


def test_on_hold_qty_after_scrap_during_hold(client: TestClient, db: Session) -> None:
    """P3-2：adjust 允许 Hold 中的批次部分报废（RULES adjust hold=True），on_hold_qty 扣掉报废数。"""
    f = Line(client, db, {"product": {"tracking_level": "quantity"}})
    (a,) = f.start(10)
    f.post(f"{EXEC}/lots/{a['id']}/hold", {"reason_id": f.reasons["hold"]["id"]})
    f.post(
        f"{EXEC}/lots/{a['id']}/adjust",
        {
            "kind": "scrap",
            "qty": 3,
            "reason_id": f.reasons["scrap"]["id"],
            "override": True,
            "override_reason": "test",
        },
    )
    assert f.lot(a)["qty"] == 7 and f.lot(a)["on_hold"]
    _set(f, a, t(10, 1), "start")
    _set(f, a, t(10, 2), "hold")
    _set(f, a, t(10, 3), "scrap")
    f.sql(
        "UPDATE mes_lot_hold SET held_at = :h WHERE lot_id = :l", h=t(10, 2), l=a["id"]
    )
    r = _get(f, date_from="2026-03-10", date_to="2026-03-10")
    op1 = next(o for o in r["by_operation"] if o["operation"] == "OP1")
    assert (op1["wip_lots"], op1["on_hold_lots"], op1["on_hold_qty"]) == (1, 1, 7)
