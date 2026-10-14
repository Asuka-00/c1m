"""批次状态机纯函数用例。

编号对应测试评审 qa/test-plans/lot-state-machine-cases.md（§1 M-*、U01-U05）。
"""

import uuid
from typing import Any

import pytest
from fastapi import HTTPException

import app.mes.lot.specs  # noqa: F401  注册 lot_status 枚举
from app.core.spec.engine import ENUMS
from app.mes.lot.lots import TERMINAL as LOTS_TERMINAL
from app.mes.lot.state import RULES, TERMINAL, LotStatus, allowed, check, lock_order


def lot_status_enum() -> list[str]:
    return [v for v, _ in ENUMS["lot_status"]]


# 测试评审用例清单 v0.2 §1 转移矩阵的独立副本（不从 RULES 导入）：
# (编号, 动作, 起始状态, on_hold, 期望) 期望 ∈ ok / lot_status / on_hold / 404
MATRIX: list[tuple[str, str, str, bool, str]] = [
    ("M-undo_start-waiting-N", "undo_start", "waiting", False, "ok"),
    ("M-undo_start-waiting-H", "undo_start", "waiting", True, "on_hold"),
    ("M-undo_start-moved_in-N", "undo_start", "moved_in", False, "lot_status"),
    ("M-undo_start-moved_in-H", "undo_start", "moved_in", True, "lot_status"),
    ("M-undo_start-running-N", "undo_start", "running", False, "lot_status"),
    ("M-undo_start-running-H", "undo_start", "running", True, "lot_status"),
    ("M-undo_start-tracked_out-N", "undo_start", "tracked_out", False, "lot_status"),
    ("M-undo_start-tracked_out-H", "undo_start", "tracked_out", True, "lot_status"),
    ("M-undo_start-completed-N", "undo_start", "completed", False, "lot_status"),
    ("M-undo_start-completed-H", "undo_start", "completed", True, "lot_status"),
    ("M-undo_start-stored-N", "undo_start", "stored", False, "lot_status"),
    ("M-undo_start-stored-H", "undo_start", "stored", True, "lot_status"),
    ("M-undo_start-scrapped-N", "undo_start", "scrapped", False, "lot_status"),
    ("M-undo_start-scrapped-H", "undo_start", "scrapped", True, "lot_status"),
    ("M-undo_start-merged-N", "undo_start", "merged", False, "lot_status"),
    ("M-undo_start-merged-H", "undo_start", "merged", True, "lot_status"),
    ("M-move_in-waiting-N", "move_in", "waiting", False, "ok"),
    ("M-move_in-waiting-H", "move_in", "waiting", True, "on_hold"),
    ("M-move_in-moved_in-N", "move_in", "moved_in", False, "lot_status"),
    ("M-move_in-moved_in-H", "move_in", "moved_in", True, "lot_status"),
    ("M-move_in-running-N", "move_in", "running", False, "lot_status"),
    ("M-move_in-running-H", "move_in", "running", True, "lot_status"),
    ("M-move_in-tracked_out-N", "move_in", "tracked_out", False, "lot_status"),
    ("M-move_in-tracked_out-H", "move_in", "tracked_out", True, "lot_status"),
    ("M-move_in-completed-N", "move_in", "completed", False, "lot_status"),
    ("M-move_in-completed-H", "move_in", "completed", True, "lot_status"),
    ("M-move_in-stored-N", "move_in", "stored", False, "lot_status"),
    ("M-move_in-stored-H", "move_in", "stored", True, "lot_status"),
    ("M-move_in-scrapped-N", "move_in", "scrapped", False, "lot_status"),
    ("M-move_in-scrapped-H", "move_in", "scrapped", True, "lot_status"),
    ("M-move_in-merged-N", "move_in", "merged", False, "lot_status"),
    ("M-move_in-merged-H", "move_in", "merged", True, "lot_status"),
    ("M-track_in-waiting-N", "track_in", "waiting", False, "lot_status"),
    ("M-track_in-waiting-H", "track_in", "waiting", True, "lot_status"),
    ("M-track_in-moved_in-N", "track_in", "moved_in", False, "ok"),
    ("M-track_in-moved_in-H", "track_in", "moved_in", True, "on_hold"),
    ("M-track_in-running-N", "track_in", "running", False, "lot_status"),
    ("M-track_in-running-H", "track_in", "running", True, "lot_status"),
    ("M-track_in-tracked_out-N", "track_in", "tracked_out", False, "lot_status"),
    ("M-track_in-tracked_out-H", "track_in", "tracked_out", True, "lot_status"),
    ("M-track_in-completed-N", "track_in", "completed", False, "lot_status"),
    ("M-track_in-completed-H", "track_in", "completed", True, "lot_status"),
    ("M-track_in-stored-N", "track_in", "stored", False, "lot_status"),
    ("M-track_in-stored-H", "track_in", "stored", True, "lot_status"),
    ("M-track_in-scrapped-N", "track_in", "scrapped", False, "lot_status"),
    ("M-track_in-scrapped-H", "track_in", "scrapped", True, "lot_status"),
    ("M-track_in-merged-N", "track_in", "merged", False, "lot_status"),
    ("M-track_in-merged-H", "track_in", "merged", True, "lot_status"),
    ("M-track_out-waiting-N", "track_out", "waiting", False, "lot_status"),
    ("M-track_out-waiting-H", "track_out", "waiting", True, "lot_status"),
    ("M-track_out-moved_in-N", "track_out", "moved_in", False, "lot_status"),
    ("M-track_out-moved_in-H", "track_out", "moved_in", True, "lot_status"),
    ("M-track_out-running-N", "track_out", "running", False, "ok"),
    ("M-track_out-running-H", "track_out", "running", True, "ok"),
    ("M-track_out-tracked_out-N", "track_out", "tracked_out", False, "lot_status"),
    ("M-track_out-tracked_out-H", "track_out", "tracked_out", True, "lot_status"),
    ("M-track_out-completed-N", "track_out", "completed", False, "lot_status"),
    ("M-track_out-completed-H", "track_out", "completed", True, "lot_status"),
    ("M-track_out-stored-N", "track_out", "stored", False, "lot_status"),
    ("M-track_out-stored-H", "track_out", "stored", True, "lot_status"),
    ("M-track_out-scrapped-N", "track_out", "scrapped", False, "lot_status"),
    ("M-track_out-scrapped-H", "track_out", "scrapped", True, "lot_status"),
    ("M-track_out-merged-N", "track_out", "merged", False, "lot_status"),
    ("M-track_out-merged-H", "track_out", "merged", True, "lot_status"),
    ("M-move_out-waiting-N", "move_out", "waiting", False, "lot_status"),
    ("M-move_out-waiting-H", "move_out", "waiting", True, "lot_status"),
    ("M-move_out-moved_in-N", "move_out", "moved_in", False, "lot_status"),
    ("M-move_out-moved_in-H", "move_out", "moved_in", True, "lot_status"),
    ("M-move_out-running-N", "move_out", "running", False, "lot_status"),
    ("M-move_out-running-H", "move_out", "running", True, "lot_status"),
    ("M-move_out-tracked_out-N", "move_out", "tracked_out", False, "ok"),
    ("M-move_out-tracked_out-H", "move_out", "tracked_out", True, "on_hold"),
    ("M-move_out-completed-N", "move_out", "completed", False, "lot_status"),
    ("M-move_out-completed-H", "move_out", "completed", True, "lot_status"),
    ("M-move_out-stored-N", "move_out", "stored", False, "lot_status"),
    ("M-move_out-stored-H", "move_out", "stored", True, "lot_status"),
    ("M-move_out-scrapped-N", "move_out", "scrapped", False, "lot_status"),
    ("M-move_out-scrapped-H", "move_out", "scrapped", True, "lot_status"),
    ("M-move_out-merged-N", "move_out", "merged", False, "lot_status"),
    ("M-move_out-merged-H", "move_out", "merged", True, "lot_status"),
    ("M-jump-waiting-N", "jump", "waiting", False, "ok"),
    ("M-jump-waiting-H", "jump", "waiting", True, "on_hold"),
    ("M-jump-moved_in-N", "jump", "moved_in", False, "lot_status"),
    ("M-jump-moved_in-H", "jump", "moved_in", True, "lot_status"),
    ("M-jump-running-N", "jump", "running", False, "lot_status"),
    ("M-jump-running-H", "jump", "running", True, "lot_status"),
    ("M-jump-tracked_out-N", "jump", "tracked_out", False, "lot_status"),
    ("M-jump-tracked_out-H", "jump", "tracked_out", True, "lot_status"),
    ("M-jump-completed-N", "jump", "completed", False, "lot_status"),
    ("M-jump-completed-H", "jump", "completed", True, "lot_status"),
    ("M-jump-stored-N", "jump", "stored", False, "lot_status"),
    ("M-jump-stored-H", "jump", "stored", True, "lot_status"),
    ("M-jump-scrapped-N", "jump", "scrapped", False, "lot_status"),
    ("M-jump-scrapped-H", "jump", "scrapped", True, "lot_status"),
    ("M-jump-merged-N", "jump", "merged", False, "lot_status"),
    ("M-jump-merged-H", "jump", "merged", True, "lot_status"),
    ("M-split-waiting-N", "split", "waiting", False, "ok"),
    ("M-split-waiting-H", "split", "waiting", True, "ok"),
    ("M-split-moved_in-N", "split", "moved_in", False, "ok"),
    ("M-split-moved_in-H", "split", "moved_in", True, "ok"),
    ("M-split-running-N", "split", "running", False, "lot_status"),
    ("M-split-running-H", "split", "running", True, "lot_status"),
    ("M-split-tracked_out-N", "split", "tracked_out", False, "lot_status"),
    ("M-split-tracked_out-H", "split", "tracked_out", True, "lot_status"),
    ("M-split-completed-N", "split", "completed", False, "lot_status"),
    ("M-split-completed-H", "split", "completed", True, "lot_status"),
    ("M-split-stored-N", "split", "stored", False, "lot_status"),
    ("M-split-stored-H", "split", "stored", True, "lot_status"),
    ("M-split-scrapped-N", "split", "scrapped", False, "lot_status"),
    ("M-split-scrapped-H", "split", "scrapped", True, "lot_status"),
    ("M-split-merged-N", "split", "merged", False, "lot_status"),
    ("M-split-merged-H", "split", "merged", True, "lot_status"),
    ("M-merge_src-waiting-N", "merge_src", "waiting", False, "ok"),
    ("M-merge_src-waiting-H", "merge_src", "waiting", True, "on_hold"),
    ("M-merge_src-moved_in-N", "merge_src", "moved_in", False, "ok"),
    ("M-merge_src-moved_in-H", "merge_src", "moved_in", True, "on_hold"),
    ("M-merge_src-running-N", "merge_src", "running", False, "lot_status"),
    ("M-merge_src-running-H", "merge_src", "running", True, "lot_status"),
    ("M-merge_src-tracked_out-N", "merge_src", "tracked_out", False, "lot_status"),
    ("M-merge_src-tracked_out-H", "merge_src", "tracked_out", True, "lot_status"),
    ("M-merge_src-completed-N", "merge_src", "completed", False, "lot_status"),
    ("M-merge_src-completed-H", "merge_src", "completed", True, "lot_status"),
    ("M-merge_src-stored-N", "merge_src", "stored", False, "lot_status"),
    ("M-merge_src-stored-H", "merge_src", "stored", True, "lot_status"),
    ("M-merge_src-scrapped-N", "merge_src", "scrapped", False, "lot_status"),
    ("M-merge_src-scrapped-H", "merge_src", "scrapped", True, "lot_status"),
    ("M-merge_src-merged-N", "merge_src", "merged", False, "lot_status"),
    ("M-merge_src-merged-H", "merge_src", "merged", True, "lot_status"),
    ("M-merge_tgt-waiting-N", "merge_tgt", "waiting", False, "ok"),
    ("M-merge_tgt-waiting-H", "merge_tgt", "waiting", True, "on_hold"),
    ("M-merge_tgt-moved_in-N", "merge_tgt", "moved_in", False, "ok"),
    ("M-merge_tgt-moved_in-H", "merge_tgt", "moved_in", True, "on_hold"),
    ("M-merge_tgt-running-N", "merge_tgt", "running", False, "lot_status"),
    ("M-merge_tgt-running-H", "merge_tgt", "running", True, "lot_status"),
    ("M-merge_tgt-tracked_out-N", "merge_tgt", "tracked_out", False, "lot_status"),
    ("M-merge_tgt-tracked_out-H", "merge_tgt", "tracked_out", True, "lot_status"),
    ("M-merge_tgt-completed-N", "merge_tgt", "completed", False, "lot_status"),
    ("M-merge_tgt-completed-H", "merge_tgt", "completed", True, "lot_status"),
    ("M-merge_tgt-stored-N", "merge_tgt", "stored", False, "lot_status"),
    ("M-merge_tgt-stored-H", "merge_tgt", "stored", True, "lot_status"),
    ("M-merge_tgt-scrapped-N", "merge_tgt", "scrapped", False, "lot_status"),
    ("M-merge_tgt-scrapped-H", "merge_tgt", "scrapped", True, "lot_status"),
    ("M-merge_tgt-merged-N", "merge_tgt", "merged", False, "lot_status"),
    ("M-merge_tgt-merged-H", "merge_tgt", "merged", True, "lot_status"),
    ("M-adjust_scrap-waiting-N", "adjust_scrap", "waiting", False, "ok"),
    ("M-adjust_scrap-waiting-H", "adjust_scrap", "waiting", True, "ok"),
    ("M-adjust_scrap-moved_in-N", "adjust_scrap", "moved_in", False, "ok"),
    ("M-adjust_scrap-moved_in-H", "adjust_scrap", "moved_in", True, "ok"),
    ("M-adjust_scrap-running-N", "adjust_scrap", "running", False, "lot_status"),
    ("M-adjust_scrap-running-H", "adjust_scrap", "running", True, "lot_status"),
    ("M-adjust_scrap-tracked_out-N", "adjust_scrap", "tracked_out", False, "ok"),
    ("M-adjust_scrap-tracked_out-H", "adjust_scrap", "tracked_out", True, "ok"),
    ("M-adjust_scrap-completed-N", "adjust_scrap", "completed", False, "lot_status"),
    ("M-adjust_scrap-completed-H", "adjust_scrap", "completed", True, "lot_status"),
    ("M-adjust_scrap-stored-N", "adjust_scrap", "stored", False, "lot_status"),
    ("M-adjust_scrap-stored-H", "adjust_scrap", "stored", True, "lot_status"),
    ("M-adjust_scrap-scrapped-N", "adjust_scrap", "scrapped", False, "lot_status"),
    ("M-adjust_scrap-scrapped-H", "adjust_scrap", "scrapped", True, "lot_status"),
    ("M-adjust_scrap-merged-N", "adjust_scrap", "merged", False, "lot_status"),
    ("M-adjust_scrap-merged-H", "adjust_scrap", "merged", True, "lot_status"),
    ("M-adjust_qty-waiting-N", "adjust_qty", "waiting", False, "ok"),
    ("M-adjust_qty-waiting-H", "adjust_qty", "waiting", True, "ok"),
    ("M-adjust_qty-moved_in-N", "adjust_qty", "moved_in", False, "ok"),
    ("M-adjust_qty-moved_in-H", "adjust_qty", "moved_in", True, "ok"),
    ("M-adjust_qty-running-N", "adjust_qty", "running", False, "ok"),
    ("M-adjust_qty-running-H", "adjust_qty", "running", True, "ok"),
    ("M-adjust_qty-tracked_out-N", "adjust_qty", "tracked_out", False, "ok"),
    ("M-adjust_qty-tracked_out-H", "adjust_qty", "tracked_out", True, "ok"),
    ("M-adjust_qty-completed-N", "adjust_qty", "completed", False, "lot_status"),
    ("M-adjust_qty-completed-H", "adjust_qty", "completed", True, "lot_status"),
    ("M-adjust_qty-stored-N", "adjust_qty", "stored", False, "lot_status"),
    ("M-adjust_qty-stored-H", "adjust_qty", "stored", True, "lot_status"),
    ("M-adjust_qty-scrapped-N", "adjust_qty", "scrapped", False, "lot_status"),
    ("M-adjust_qty-scrapped-H", "adjust_qty", "scrapped", True, "lot_status"),
    ("M-adjust_qty-merged-N", "adjust_qty", "merged", False, "lot_status"),
    ("M-adjust_qty-merged-H", "adjust_qty", "merged", True, "lot_status"),
    ("M-change_carrier-waiting-N", "change_carrier", "waiting", False, "ok"),
    ("M-change_carrier-waiting-H", "change_carrier", "waiting", True, "ok"),
    ("M-change_carrier-moved_in-N", "change_carrier", "moved_in", False, "ok"),
    ("M-change_carrier-moved_in-H", "change_carrier", "moved_in", True, "ok"),
    ("M-change_carrier-running-N", "change_carrier", "running", False, "lot_status"),
    ("M-change_carrier-running-H", "change_carrier", "running", True, "lot_status"),
    ("M-change_carrier-tracked_out-N", "change_carrier", "tracked_out", False, "ok"),
    ("M-change_carrier-tracked_out-H", "change_carrier", "tracked_out", True, "ok"),
    (
        "M-change_carrier-completed-N",
        "change_carrier",
        "completed",
        False,
        "lot_status",
    ),
    ("M-change_carrier-completed-H", "change_carrier", "completed", True, "lot_status"),
    ("M-change_carrier-stored-N", "change_carrier", "stored", False, "lot_status"),
    ("M-change_carrier-stored-H", "change_carrier", "stored", True, "lot_status"),
    ("M-change_carrier-scrapped-N", "change_carrier", "scrapped", False, "lot_status"),
    ("M-change_carrier-scrapped-H", "change_carrier", "scrapped", True, "lot_status"),
    ("M-change_carrier-merged-N", "change_carrier", "merged", False, "lot_status"),
    ("M-change_carrier-merged-H", "change_carrier", "merged", True, "lot_status"),
    ("M-priority-waiting-N", "priority", "waiting", False, "ok"),
    ("M-priority-waiting-H", "priority", "waiting", True, "ok"),
    ("M-priority-moved_in-N", "priority", "moved_in", False, "ok"),
    ("M-priority-moved_in-H", "priority", "moved_in", True, "ok"),
    ("M-priority-running-N", "priority", "running", False, "ok"),
    ("M-priority-running-H", "priority", "running", True, "ok"),
    ("M-priority-tracked_out-N", "priority", "tracked_out", False, "ok"),
    ("M-priority-tracked_out-H", "priority", "tracked_out", True, "ok"),
    ("M-priority-completed-N", "priority", "completed", False, "lot_status"),
    ("M-priority-completed-H", "priority", "completed", True, "lot_status"),
    ("M-priority-stored-N", "priority", "stored", False, "lot_status"),
    ("M-priority-stored-H", "priority", "stored", True, "lot_status"),
    ("M-priority-scrapped-N", "priority", "scrapped", False, "lot_status"),
    ("M-priority-scrapped-H", "priority", "scrapped", True, "lot_status"),
    ("M-priority-merged-N", "priority", "merged", False, "lot_status"),
    ("M-priority-merged-H", "priority", "merged", True, "lot_status"),
    ("M-hold-waiting-N", "hold", "waiting", False, "ok"),
    ("M-hold-waiting-H", "hold", "waiting", True, "ok"),
    ("M-hold-moved_in-N", "hold", "moved_in", False, "ok"),
    ("M-hold-moved_in-H", "hold", "moved_in", True, "ok"),
    ("M-hold-running-N", "hold", "running", False, "ok"),
    ("M-hold-running-H", "hold", "running", True, "ok"),
    ("M-hold-tracked_out-N", "hold", "tracked_out", False, "ok"),
    ("M-hold-tracked_out-H", "hold", "tracked_out", True, "ok"),
    ("M-hold-completed-N", "hold", "completed", False, "ok"),  # M2
    ("M-hold-completed-H", "hold", "completed", True, "ok"),  # M2
    ("M-hold-stored-N", "hold", "stored", False, "ok"),  # M2
    ("M-hold-stored-H", "hold", "stored", True, "ok"),  # M2
    ("M-hold-scrapped-N", "hold", "scrapped", False, "lot_status"),
    ("M-hold-scrapped-H", "hold", "scrapped", True, "lot_status"),
    ("M-hold-merged-N", "hold", "merged", False, "lot_status"),
    ("M-hold-merged-H", "hold", "merged", True, "lot_status"),
    ("M-release-waiting-N", "release", "waiting", False, "404"),
    ("M-release-waiting-H", "release", "waiting", True, "ok"),
    ("M-release-moved_in-N", "release", "moved_in", False, "404"),
    ("M-release-moved_in-H", "release", "moved_in", True, "ok"),
    ("M-release-running-N", "release", "running", False, "404"),
    ("M-release-running-H", "release", "running", True, "ok"),
    ("M-release-tracked_out-N", "release", "tracked_out", False, "404"),
    ("M-release-tracked_out-H", "release", "tracked_out", True, "ok"),
    ("M-release-completed-N", "release", "completed", False, "404"),
    ("M-release-completed-H", "release", "completed", True, "ok"),
    ("M-release-stored-N", "release", "stored", False, "404"),
    ("M-release-stored-H", "release", "stored", True, "ok"),
    ("M-release-scrapped-N", "release", "scrapped", False, "404"),
    ("M-release-scrapped-H", "release", "scrapped", True, "ok"),
    ("M-release-merged-N", "release", "merged", False, "404"),
    ("M-release-merged-H", "release", "merged", True, "ok"),
    ("M-store-waiting-N", "store", "waiting", False, "lot_status"),
    ("M-store-waiting-H", "store", "waiting", True, "lot_status"),
    ("M-store-moved_in-N", "store", "moved_in", False, "lot_status"),
    ("M-store-moved_in-H", "store", "moved_in", True, "lot_status"),
    ("M-store-running-N", "store", "running", False, "lot_status"),
    ("M-store-running-H", "store", "running", True, "lot_status"),
    ("M-store-tracked_out-N", "store", "tracked_out", False, "lot_status"),
    ("M-store-tracked_out-H", "store", "tracked_out", True, "lot_status"),
    ("M-store-completed-N", "store", "completed", False, "ok"),
    ("M-store-completed-H", "store", "completed", True, "on_hold"),
    ("M-store-stored-N", "store", "stored", False, "lot_status"),
    ("M-store-stored-H", "store", "stored", True, "lot_status"),
    ("M-store-scrapped-N", "store", "scrapped", False, "lot_status"),
    ("M-store-scrapped-H", "store", "scrapped", True, "lot_status"),
    ("M-store-merged-N", "store", "merged", False, "lot_status"),
    ("M-store-merged-H", "store", "merged", True, "lot_status"),
]
# 清单动作名 -> RULES 动作名
ACTION = {
    "adjust_qty": "adjust",
    "adjust_scrap": "scrap",
    "merge_src": "merge_source",
    "merge_tgt": "merge_target",
}


def _from(act: str) -> set[str]:
    return {str(x) for x in RULES[act].from_}


def _lot(status: str, on_hold: bool = False) -> dict[str, Any]:
    return {"lot_status": status, "on_hold": on_hold}


def test_rules_cover_matrix_actions() -> None:
    # ship（D13 规则层）、auto_hold（D17）、transform（B5）不在清单矩阵中；qtime_scrap 按 D12 删除
    assert set(RULES) - {"ship", "auto_hold", "transform"} == {
        ACTION.get(r[1], r[1]) for r in MATRIX
    }
    assert "qtime_scrap" not in RULES
    assert (
        len(MATRIX) == 256 and sum(r[4] == "ok" for r in MATRIX) == 64
    )  # 清单 62 + M2 的 4 条


@pytest.mark.parametrize(
    "case,action,status,on_hold,expect", MATRIX, ids=[r[0] for r in MATRIX]
)
def test_matrix(
    case: str, action: str, status: str, on_hold: bool, expect: str
) -> None:
    """清单 §1 M-*：8 状态 × 17 动作 × on_hold 全枚举。"""
    assert case.startswith(f"M-{action}-{status}-")
    lot = _lot(status, on_hold)
    act = ACTION.get(action, action)
    if expect in ("ok", "404"):
        # 404：无 active hold 时 release 由服务层按 hold_id 返回 404（见 H06），
        # 状态机本身对任意状态放行（P05）
        assert allowed(lot, act)
        return
    with pytest.raises(HTTPException) as e:
        check(lot, act)
    assert e.value.status_code == 422
    assert e.value.detail["code"] == expect  # P01 / N5


def test_u01_track_out_targets() -> None:
    assert (
        check(_lot("running"), "track_out", to="tracked_out") == LotStatus.TRACKED_OUT
    )
    assert check(_lot("running"), "track_out", to="scrapped") == LotStatus.SCRAPPED
    for to in ("completed", "waiting"):
        with pytest.raises(HTTPException):
            check(_lot("running"), "track_out", to=to)


def test_u02_move_out_to_scrapped_rejected() -> None:
    with pytest.raises(HTTPException):
        check(_lot("tracked_out"), "move_out", to="scrapped")


def test_u03_no_abort_action() -> None:
    with pytest.raises(KeyError):
        check(_lot("running"), "abort")


def test_u04_terminal() -> None:
    assert {str(x) for x in TERMINAL} == {
        "completed",
        "stored",
        "scrapped",
        "merged",
        "converted",  # B5 单位转换后的母批
    }
    assert set(TERMINAL) == set(LOTS_TERMINAL)


def test_u05_lot_status_matches_spec_enum() -> None:
    assert len(LotStatus) == 9  # B5 加 converted
    assert [str(x) for x in LotStatus] == list(lot_status_enum())


def test_lock_order_sorted_and_deduped() -> None:
    """K03 前提：加锁顺序 = 去重后 id 升序。"""
    ids = [uuid.uuid4() for _ in range(5)]
    assert lock_order([str(ids[3]), ids[0], ids[3], *ids]) == sorted(set(ids))
    assert lock_order(reversed(ids)) == lock_order(ids)


def test_h2_02_ship_stored_on_hold_rejected() -> None:
    """H2-02（D13）：stored 持 Hold 出货 → 422 on_hold（规则层；尚无出货接口）。"""
    assert allowed(_lot("stored"), "ship")
    with pytest.raises(HTTPException) as e:
        check(_lot("stored", True), "ship")
    assert e.value.status_code == 422 and e.value.detail["code"] == "on_hold"
    for st in ("completed", "scrapped", "merged", "waiting"):
        with pytest.raises(HTTPException) as e:
            check(_lot(st, True), "ship")
        assert e.value.detail["code"] == "lot_status"


def test_qt_06_no_qtime_scrap_write_path() -> None:
    """QT-06（D12）：qtime.py / qtime_actions.py 无超时直接报废路径。"""
    from pathlib import Path

    import app.mes.execution.qtime_actions as qa
    import app.mes.lot.qtime as lq

    for mod in (qa, lq):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        for bad in ('"scrapped"', "'scrapped'", '"qtime_scrap"', 'action == "scrap"'):
            assert bad not in src, (mod.__name__, bad)


@pytest.mark.parametrize("status", ["completed", "stored", "scrapped", "merged"])
def test_ah_auto_hold_rule(status: str) -> None:
    """D17：自动 Hold 只对在制批次；手动 Hold 按 HOLDABLE（completed/stored 允许）。"""
    assert not allowed(_lot(status), "auto_hold")
    assert allowed(_lot(status), "hold") is (status in ("completed", "stored"))
    for st in ("waiting", "moved_in", "running", "tracked_out"):
        assert allowed(_lot(st, True), "auto_hold")
