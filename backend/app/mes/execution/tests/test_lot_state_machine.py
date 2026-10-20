"""批次状态机服务层 / 并发用例（需 PostgreSQL）。

编号对应测试评审 qa/test-plans/lot-state-machine-cases.md；待定项 xfail(strict)。
"""

import threading
import uuid
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, text

from app.core import error_codes as ec
from app.core.db import engine
from app.mes.execution.hold import manage as hold_svc
from app.mes.execution.split_merge import merge as merge_mod
from app.mes.execution.tests.test_exec import EXEC, Line, _msgs
from app.mes.execution.tests.test_split_merge import _line, merge
from app.mes.lot.service import lock_lot


def _hold(f: Line, lot: Any, status: int = 200) -> Any:
    return f.post(
        f"{EXEC}/lots/{lot['id']}/hold", {"reason_id": f.reasons["hold"]["id"]}, status
    )


def _session(tid: str) -> Session:
    s = Session(engine)
    s.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": tid})
    return s


def test_hold_while_running_allows_track_out_not_move_out(
    client: TestClient, db: Session
) -> None:
    """L09 / L10（D2）：持 Hold 的 running 可 track_out，tracked_out 持 Hold 不能 move_out（422 on_hold）。"""
    f = Line(client, db)
    (lot,) = f.start(2)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    _hold(f, lot)
    f.stage(lot, "track_out")
    assert f.lot(lot)["lot_status"] == "tracked_out"
    assert "on hold" in _msgs(f.stage(lot, "move_out", 422))
    hid = f.ctx(lot)["holds"][0]["id"]
    f.post(f"{EXEC}/holds/{hid}/release", {"reason_id": f.reasons["release"]["id"]})
    f.stage(lot, "move_out")
    assert f.lot(lot)["lot_status"] == "waiting"


def test_illegal_stage_transitions(client: TestClient, db: Session) -> None:
    """X03 前提 / M-* 落到接口：非法转移 422，状态与历史不变。"""
    f = Line(client, db)
    (lot,) = f.start(1)
    n0 = len(f.m.list("lot_history", lot=lot["id"])["data"])
    for st in ("track_in", "track_out", "move_out"):
        assert "cannot" in _msgs(f.stage(lot, st, 422))
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "move_in", 422, equipment_id=f.eq["id"])
    acts = [h["action"] for h in f.m.list("lot_history", lot=lot["id"])["data"]]
    assert len(acts) == n0 + 1 and f.lot(lot)["lot_status"] == "moved_in"


def test_terminal_lot_cannot_be_held_even_automatically(
    client: TestClient, db: Session
) -> None:
    """H07 / H08（D4）：终态批次拒绝手工与自动 Hold，不新增 lot_hold。

    P11：手动 422，自动来源静默跳过、不写数据。
    """
    f = Line(client, db)
    (lot,) = f.start(1)
    f.sql("UPDATE mes_lot SET lot_status='scrapped' WHERE id=:i", i=lot["id"])
    assert "scrapped" in _msgs(_hold(f, lot, 422))
    tid = uuid.UUID(f.m.tid)
    with _session(f.m.tid) as s:
        row = lock_lot(s, tid, uuid.UUID(lot["id"]))
        reason = hold_svc.default_reason(s, tid, "hold")
        got = hold_svc.hold_lot(
            s, tid, row, None, reason, hold_type="auto", source="qtime"
        )
        assert got is None  # P11：自动来源静默跳过
        s.commit()
    assert not f.ctx(lot)["holds"]


def test_running_lot_cannot_be_scrapped_to_zero(
    client: TestClient, db: Session
) -> None:
    """B20（D3）：running 批次不能 adjust 报废到 0。"""
    f = Line(client, db, {"product": {"tracking_level": "quantity"}})
    (lot,) = f.start(3)
    f.stage(lot, "move_in")
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    f.post(
        f"{EXEC}/lots/{lot['id']}/adjust",
        {"kind": "scrap", "qty": 3, "reason_id": f.reasons["scrap"]["id"]},
        422,
    )
    assert f.lot(lot)["lot_status"] == "running"


def test_duplicate_release_rejected(client: TestClient, db: Session) -> None:
    """H01-H05：多重 Hold，逐条释放，重复释放 422。"""
    f = Line(client, db)
    (lot,) = f.start(1)
    _hold(f, lot)
    _hold(f, lot)
    h1, h2 = (h["id"] for h in f.ctx(lot)["holds"])
    rel = {"reason_id": f.reasons["release"]["id"]}
    assert f.post(f"{EXEC}/holds/{h1}/release", rel)["on_hold"]
    assert "already released" in _msgs(f.post(f"{EXEC}/holds/{h1}/release", rel, 422))
    assert not f.post(f"{EXEC}/holds/{h2}/release", rel)["on_hold"]
    acts = [h["action"] for h in f.m.list("lot_history", lot=lot["id"])["data"]]
    assert acts.count("release") == 2


def test_concurrent_release_only_once(client: TestClient, db: Session) -> None:
    """H13：两会话并发释放同一 Hold，只释放一次（锁顺序 lot → lot_hold）。"""
    f = Line(client, db)
    (lot,) = f.start(1)
    _hold(f, lot)
    hid = uuid.UUID(f.ctx(lot)["holds"][0]["id"])
    tid = uuid.UUID(f.m.tid)
    rid = f.reasons["release"]["id"]
    out: dict[str, Any] = {}

    def b() -> None:
        with _session(f.m.tid) as s:
            try:
                hold_svc.release_hold(s, tid, hid, None, rid, "b")
                out["b"] = "ok"
            except HTTPException as e:
                s.rollback()
                out["b"] = e.status_code

    with _session(f.m.tid) as a:
        lock_lot(a, tid, uuid.UUID(lot["id"]))  # A 先持有批次锁
        t = threading.Thread(target=b)
        t.start()
        t.join(1.0)
        assert t.is_alive()  # B 在批次锁上等待，而不是先改了 lot_hold
        hold_svc.release_hold(a, tid, hid, None, rid, "a")  # 内部提交，释放锁
    t.join(10)
    assert out["b"] == 422
    acts = [h["action"] for h in f.m.list("lot_history", lot=lot["id"])["data"]]
    assert acts.count("release") == 1 and not f.lot(lot)["on_hold"]


def test_merge_locks_all_lots_once_in_id_order(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """K03：合批把目标与源批次一次按 id 升序加锁。"""
    calls: list[list[uuid.UUID]] = []
    real = merge_mod.lock_lots

    def spy(s: Session, tid: uuid.UUID, ids: Any) -> Any:
        ids = list(ids)
        calls.append(ids)
        return real(s, tid, ids)

    monkeypatch.setattr(merge_mod, "lock_lots", spy)
    f = _line(client, db)
    a, b, c = f.start(2, 2, 2)
    merge(f, c, [b, a])
    (ids,) = calls
    assert {str(x) for x in ids} == {a["id"], b["id"], c["id"]}
    assert f.lot(a)["lot_status"] == f.lot(b)["lot_status"] == "merged"


def test_reverse_merges_do_not_deadlock(client: TestClient, db: Session) -> None:
    """K01：反向同时合批无死锁（无 40P01），一个成功，另一个 ∈{409,422}（P16）。"""
    f = _line(client, db)
    l1, l2 = f.start(2, 2)
    tid = uuid.UUID(f.m.tid)
    res: dict[str, Any] = {}
    go = threading.Barrier(2)

    def run(name: str, tgt: Any, src: Any) -> None:
        with _session(f.m.tid) as s:
            go.wait()
            try:
                merge_mod.merge(
                    s, tid, uuid.UUID(tgt["id"]), {"source_lot_ids": [src["id"]]}, None
                )
                s.commit()
                res[name] = "ok"
            except HTTPException as e:
                s.rollback()
                res[name] = e.status_code
            except Exception as e:  # noqa: BLE001
                s.rollback()
                res[name] = type(e).__name__

    ts = [
        threading.Thread(target=run, args=("a", l1, l2)),
        threading.Thread(target=run, args=("b", l2, l1)),
    ]
    for t in ts:
        t.start()
    for t in ts:
        t.join(30)
    assert "ok" in res.values() and len(res) == 2, res
    other = next(v for v in res.values() if v != "ok")
    assert other in (409, 422), res


def test_l11_release_on_terminal_lot(client: TestClient, db: Session) -> None:
    """L12（P05）：终态批次可释放遗留 Hold，只清 Hold 标志不改状态。"""
    f = Line(client, db)
    (lot,) = f.start(1)
    _hold(f, lot)
    f.sql("UPDATE mes_lot SET lot_status='scrapped' WHERE id=:i", i=lot["id"])
    hid = f.ctx(lot)["holds"][0]["id"]
    r = f.post(f"{EXEC}/holds/{hid}/release", {"reason_id": f.reasons["release"]["id"]})
    assert not r["on_hold"] and f.lot(lot)["lot_status"] == "scrapped"


def test_h06_release_unknown_hold_404(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    f.post(f"{EXEC}/holds/{uuid.uuid4()}/release", {}, 404)


def test_b03_split_all_rejected(client: TestClient, db: Session) -> None:
    """B03（P13）：拆完母批 → 422 lot_status。"""
    f = _line(client, db, min_wafers=1)
    (lot,) = f.start(2)
    us = [u["id"] for u in f.ctx(lot)["units"]]
    r = f.post(f"{EXEC}/lots/{lot['id']}/split", {"children": [{"unit_ids": us}]}, 422)
    assert r["detail"]["code"] == ec.LOT_STATUS and f.lot(lot)["qty"] == 2


def test_b07_split_running_rejected(client: TestClient, db: Session) -> None:
    """B07：running 批次拆批 → 422 lot_status。"""
    f = _line(client, db)
    (lot,) = f.start(4)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    us = [u["id"] for u in f.ctx(lot)["units"]][:2]
    r = f.post(f"{EXEC}/lots/{lot['id']}/split", {"children": [{"unit_ids": us}]}, 422)
    assert "cannot split a running lot" in _msgs(r)


def test_b11_b13_merge_duplicate_or_self_rejected(
    client: TestClient, db: Session
) -> None:
    """B11 / B13（P14）：源含目标或重复 id → 422，不静默去重。"""
    f = _line(client, db)
    a, b = f.start(2, 2)
    url = f"{EXEC}/lots/{a['id']}/merge"
    d = f.post(url, {"source_lot_ids": [b["id"], b["id"]]}, 422)["detail"]
    assert d["code"] == ec.MERGE_SOURCE_INVALID and d["duplicates"] == [b["id"]]
    assert not d["includes_target"] and d["message"]
    d = f.post(url, {"source_lot_ids": [b["id"], a["id"]]}, 422)["detail"]  # B12
    assert d["code"] == ec.MERGE_SOURCE_INVALID and d["includes_target"]
    d = f.post(url, {"source_lot_ids": [a["id"]]}, 422)["detail"]  # B11
    assert d["code"] == ec.MERGE_SOURCE_INVALID
    assert f.lot(b)["lot_status"] == "waiting" and f.lot(a)["qty"] == 2


def test_k04_lock_timeout_409_lot_busy(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """K04（P16）：批次被长事务锁住 → 409 lot_busy（测试把超时调成 200ms）。"""
    from app.mes.lot import state

    monkeypatch.setattr(state, "LOCK_TIMEOUT", "200ms")
    f = Line(client, db)
    (lot,) = f.start(1)
    tid = uuid.UUID(f.m.tid)
    with _session(f.m.tid) as a:
        lock_lot(a, tid, uuid.UUID(lot["id"]))
        r = f.stage(lot, "move_in", 409, equipment_id=f.eq["id"])
        assert r["detail"]["code"] == ec.LOT_BUSY
        a.rollback()
    assert f.lot(lot)["lot_status"] == "waiting"


def test_p15_scrap_to_zero_keeps_hold(client: TestClient, db: Session) -> None:
    """P15（kai mi 定 A）：持 Hold 报废到 0，遗留 Hold 保留不自动释放。"""
    f = Line(client, db, {"product": {"tracking_level": "quantity"}})
    (lot,) = f.start(3)
    _hold(f, lot)
    f.post(
        f"{EXEC}/lots/{lot['id']}/adjust",
        {
            "kind": "scrap",
            "qty": 3,
            "reason_id": f.reasons["scrap"]["id"],
            "override": True,
            "override_reason": "test",
        },
    )
    got = f.lot(lot)
    assert got["lot_status"] == "scrapped" and got["on_hold"]
    assert len(f.ctx(lot)["holds"]) == 1


def _field(r: Any) -> str:
    d = r["detail"]
    assert d["message"]  # N5：{code, message, ...}
    return ec.CODES[d["code"]].lower()


def test_b08_merge_different_status_rejected(client: TestClient, db: Session) -> None:
    """B08（N4）：源与目标状态不同 → 422 lot_status，无变化。"""
    f = _line(client, db)
    a, b = f.start(2, 2)
    f.stage(b, "move_in", equipment_id=f.eq["id"])
    assert _field(merge(f, a, [b], 422)) == "lot_status"
    assert f.lot(b)["lot_status"] == "moved_in" and f.lot(a)["qty"] == 2


def test_b10_merge_on_hold_rejected(client: TestClient, db: Session) -> None:
    """B10（N4）：源持 Hold → 422 on_hold；目标持 Hold 同样 422 on_hold。"""
    f = _line(client, db)
    a, b = f.start(2, 2)
    _hold(f, b)
    assert _field(merge(f, a, [b], 422)) == "on_hold"
    assert _field(merge(f, b, [a], 422)) == "on_hold"
    assert f.lot(a)["qty"] == 2 and f.lot(b)["lot_status"] == "waiting"


def test_n4_status_takes_precedence_over_hold(client: TestClient, db: Session) -> None:
    """N4：源状态非法且持 Hold → 以 lot_status 为准。"""
    f = _line(client, db)
    a, b = f.start(2, 2)
    f.stage(b, "move_in", equipment_id=f.eq["id"])
    f.stage(b, "track_in", equipment_id=f.eq["id"])
    _hold(f, b)
    assert _field(merge(f, a, [b], 422)) == "lot_status"


def test_n4_target_first_then_sources_by_id(client: TestClient, db: Session) -> None:
    """N4：先查目标，再按 id 升序查源，返回第一个不合格。"""
    f = _line(client, db)
    t_, x, y = f.start(2, 2, 2)
    lo, hi = sorted((x, y), key=lambda r: r["id"])
    _hold(f, hi)
    f.stage(lo, "move_in", equipment_id=f.eq["id"])
    r = merge(f, t_, [hi, lo], 422)  # 请求里高 id 在前，仍先报低 id 源
    assert _field(r) == "lot_status" and r["detail"]["lot_code"] == lo["code"]
    _hold(f, t_)
    assert _field(merge(f, t_, [hi, lo], 422)) == "on_hold"  # 目标优先


def test_n4_rule_mismatch_still_409(client: TestClient, db: Session) -> None:
    """N4：状态机通过后，规则不一致（不同工步）仍 409 check_blocked。"""
    f = _line(client, db)
    a, b = f.start(2, 2)
    f.run_step(b)
    assert merge(f, a, [b], 409)["detail"]["code"] == ec.CHECK_BLOCKED


def test_x03_duplicate_track_out_without_key(client: TestClient, db: Session) -> None:
    """X03 / IK10：不带键重复 track_out，第二次 422 lot_status，状态只前进一步。"""
    f = Line(client, db)
    (lot,) = f.start(1)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_out")
    r = f.stage(lot, "track_out", 422)
    assert r["detail"]["code"] == ec.LOT_STATUS
    assert f.lot(lot)["lot_status"] == "tracked_out"


@pytest.mark.xfail(strict=True, reason="待定 #IK01 Idempotency-Key 留到事件步骤")
def test_ik01_same_key_returns_first_result(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    (lot,) = f.start(1)
    f.stage(lot, "move_in", equipment_id=f.eq["id"])
    f.stage(lot, "track_in", equipment_id=f.eq["id"])
    h = {**f.m.h, "Idempotency-Key": "k1"}
    first = f.post(f"{EXEC}/lots/{lot['id']}/track_out", {}, 200, h)
    assert f.post(f"{EXEC}/lots/{lot['id']}/track_out", {}, 200, h) == first


def test_hold_list_excludes_terminal_by_default(
    client: TestClient, db: Session
) -> None:
    """N6（M2 修订）：Hold 列表默认排除 scrapped / merged；include_terminal=true 包含；返回 lot_status，count 一致。"""
    f = Line(client, db)
    a, b, c = f.start(1, 1, 1)
    for x in (a, b, c):
        _hold(f, x)
    f.sql("UPDATE mes_lot SET lot_status='scrapped' WHERE id=:i", i=b["id"])
    f.sql("UPDATE mes_lot SET lot_status='completed' WHERE id=:i", i=c["id"])

    def get(**p: Any) -> Any:
        r = f.c.get(f"{EXEC}/holds", headers=f.m.h, params=p)
        assert r.status_code == 200, r.text
        return r.json()

    r = get()  # M2：默认只排除 scrapped / merged，completed 仍显示
    assert r["count"] == len(r["data"]) == 2
    assert {x["lot"]: x["lot_status"] for x in r["data"]} == {
        a["code"]: "waiting",
        c["code"]: "completed",
    }
    r = get(include_terminal="true")
    assert r["count"] == 3
    assert {x["lot"]: x["lot_status"] for x in r["data"]}[b["code"]] == "scrapped"
    r = get(include_terminal="true", page_size=1)
    assert r["count"] == 3 and len(r["data"]) == 1


def test_n5_error_shapes(client: TestClient, db: Session) -> None:
    """N5：本步新增 / 改动的错误为 detail {code, message, ...}。"""
    f = Line(client, db)
    (lot,) = f.start(1)
    d = f.stage(lot, "track_in", 422)["detail"]
    assert d["code"] == ec.LOT_STATUS and d["action"] == "track_in"
    assert d["lot_status"] == "waiting" and d["lot_id"] == lot["id"] and d["message"]
    _hold(f, lot)
    d = f.stage(lot, "move_in", 422, equipment_id=f.eq["id"])["detail"]
    assert d["code"] == ec.ON_HOLD and d["message"]


@pytest.mark.parametrize("status", ["completed", "stored"])
def test_m2_manual_hold_completed_stored_allowed(
    client: TestClient, db: Session, status: str
) -> None:
    """M2：completed / stored 允许手动 Hold；scrapped / merged 仍 422（见 H07）。"""
    f = Line(client, db)
    (lot,) = f.start(1)
    f.sql("UPDATE mes_lot SET lot_status=:st WHERE id=:i", st=status, i=lot["id"])
    _hold(f, lot)
    got = f.lot(lot)
    assert got["on_hold"] and got["lot_status"] == status


def test_m2_merged_manual_hold_rejected(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    (lot,) = f.start(1)
    f.sql("UPDATE mes_lot SET lot_status='merged' WHERE id=:i", i=lot["id"])
    assert _hold(f, lot, 422)["detail"]["code"] == ec.LOT_STATUS
