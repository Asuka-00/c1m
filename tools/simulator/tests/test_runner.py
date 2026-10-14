from fake import B9, B10, B11, BASE_PATHS, FakeClient

from sim.client import Resp
from sim.runner import FAILED, PASSED, SKIPPED, Runner, check_expect
from sim.scenario import parse


def run(data, **kw):
    c = FakeClient(**kw)
    return c, Runner(c).run(parse(data))


def test_state_change_no_source_and_tag():
    c, rep = run({"run_id": "r1", "steps": [{"state": {"eq": "EQ1", "to": "PRD"}}]})
    assert rep["status"] == PASSED
    m, path, body, headers, _ = [x for x in c.calls if x[0] == "POST"][0]
    assert path == "/mes/eqp/e-1/e10"
    assert body["to_state_id"] == "s-prd"
    assert "source" not in body  # D30
    assert "sim:r1:EQ1:1" in body["comment"]
    assert headers == {"Idempotency-Key": "sim:r1:EQ1:1"}


def test_wait_qual_blocked_passes():
    exp = {"status": 409, "code": "check_blocked", "check": {"check_type": "eqp_wait_qual", "overridable": False}}
    _, rep = run(
        {
            "run_id": "q",
            "steps": [
                {"precondition": {"eq": "EQ2", "qual_state": "wait_qual"}},
                {"move_in": {"eq": "EQ2", "lot": "L1", "expect": exp}},
            ],
        },
        qual="wait_qual",
    )
    assert rep["status"] == PASSED, rep


def test_precondition_unmet_is_skipped():
    _, rep = run(
        {
            "run_id": "q",
            "steps": [
                {"precondition": {"eq": "EQ2", "qual_state": "wait_qual"}},
                {"move_in": {"eq": "EQ2", "lot": "L1"}},
            ],
        }
    )
    assert rep["status"] == SKIPPED and "qual_state" in rep["reason"]


def test_unexpected_status_fails_and_stops():
    _, rep = run(
        {
            "run_id": "q",
            "steps": [
                {"move_in": {"eq": "EQ2", "lot": "L1", "expect": {"status": 409}}},
                {"state": {"eq": "EQ1", "to": "PRD"}},
            ],
        }
    )
    assert rep["status"] == FAILED and len(rep["steps"]) == 1


def test_missing_entity_fails():
    _, rep = run({"run_id": "q", "steps": [{"state": {"eq": "NOPE", "to": "PRD"}}]})
    assert rep["status"] == FAILED and "NOPE" in rep["reason"]


ALARM = {
    "run_id": "a",
    "steps": [
        {"alarm_set": {"eq": "EQ1", "alid": 1001, "lots": ["L1"], "save_as": "x"}},
        {"expect_hold": {"lot": "L1", "count": 1}},
        {"replay": {"eq": "EQ1", "seq": 1}},
        {"expect_hold": {"lot": "L1", "count": 1}},
        {"alarm_clear": {"eq": "EQ1", "alarm": "$x"}},
    ],
}


def test_alarm_skipped_without_b9():
    c, rep = run(ALARM)
    assert rep["status"] == SKIPPED and "B9" in rep["reason"]
    assert not [x for x in c.calls if x[0] == "POST"]  # 一个写请求都不发


def test_alarm_runs_with_b9_and_replay_is_idempotent():
    c, rep = run(ALARM, paths=BASE_PATHS | B9)
    assert rep["status"] == PASSED, rep
    sets = [x for x in c.calls if x[1].endswith("/alarms")]
    assert len(sets) == 2 and sets[0][2] == sets[1][2]
    assert sets[0][2]["external_event_id"] == "sim:a:EQ1:1"
    assert c.holds == 1
    clear = [x for x in c.calls if x[1].endswith("/clear")][0]
    assert clear[1] == "/mes/eqp/alarms/a-1/clear"


def test_tool_usage_skipped_without_b10():
    _, rep = run({"run_id": "t", "steps": [{"tool_usage": {"eq": "EQ1", "tool": "T1", "delta": 5}}]})
    assert rep["status"] == SKIPPED and "B10" in rep["reason"]
    c, rep = run(
        {"run_id": "t", "steps": [{"tool_usage": {"eq": "EQ1", "tool": "T1", "delta": 5}}]},
        paths=BASE_PATHS | B10,
    )
    assert c.calls[-1][2]["delta"] == "5"  # numeric 按字符串传（D50）


def test_mount_replay_same_record():
    c, rep = run(
        {
            "run_id": "m",
            "steps": [
                {"mount": {"eq": "EQ1", "port": "P1", "material_lot": "ML1", "save_as": "m"}},
                {"replay": {"eq": "EQ1", "seq": 1}},
                {"unmount": {"mount": "$m"}},
            ],
        }
    )
    assert rep["status"] == PASSED, rep
    assert len(c.mounts) == 1


def test_scenario_replay_gives_same_ids():
    data = {"run_id": "same", "steps": [{"state": {"eq": "EQ1", "to": "PRD"}}, {"state": {"eq": "EQ1", "to": "SBY"}}]}
    ids = [[s["external_event_id"] for s in run(data)[1]["steps"]] for _ in range(2)]
    assert ids[0] == ids[1] == ["sim:same:EQ1:1", "sim:same:EQ1:2"]


def test_report_has_no_token():
    import json

    _, rep = run({"run_id": "r1", "steps": [{"state": {"eq": "EQ1", "to": "PRD"}}]})
    assert "secret-token" not in json.dumps(rep)


def test_check_expect_messages():
    r = Resp(409, {"detail": {"code": "check_blocked", "results": [{"check_type": "tool_life", "overridable": True}]}})
    assert check_expect(r, {"status": 409, "code": "check_blocked"}) == []
    errs = check_expect(r, {"status": 409, "check": {"check_type": "tool_life", "overridable": False}})
    assert errs and "overridable" in errs[0]
    assert check_expect(r, {"check": {"check_type": "x"}})  # 200 != 409 与缺项


# ---- D54 / D55 ----
import yaml  # noqa: E402

from sim.scenario import load  # noqa: E402

SCN = __import__("pathlib").Path(__file__).resolve().parents[1] / "scenarios"


def test_bundled_alarm_hold_skipped_without_b9():
    c = FakeClient()
    rep = Runner(c).run(load(SCN / "alarm-hold.yaml"))
    assert rep["status"] == SKIPPED and "B9" in rep["reason"]
    assert not [x for x in c.calls if x[0] == "POST"]


def test_bundled_alarm_hold_d55_passes_with_b9():
    c = FakeClient(paths=BASE_PATHS | B9)
    rep = Runner(c).run(load(SCN / "alarm-hold.yaml"))
    assert rep["status"] == PASSED, rep
    assert c.holds == 1  # 未登记 ALID 不 Hold
    unreg = [r for r in c.alarm_rows.values() if r["unregistered"]]
    assert len(unreg) == 1 and unreg[0]["lots"] == [{"lot_id": "l-fx2"}]  # 仍写 mes_alarm_lot
    posts = [x for x in c.calls if x[0] == "POST"]
    assert all("source" not in (x[2] or {}) for x in posts)  # D30
    assert all(x[3] and x[3].get("Idempotency-Key") for x in posts)


def test_unregistered_alarm_changing_e10_fails():
    c = FakeClient(paths=BASE_PATHS | B9)
    data = {
        "run_id": "u",
        "steps": [
            {"expect_e10": {"eq": "EQ1", "save_as": "b"}},
            {"alarm_set": {"eq": "EQ1", "alid": "1001", "save_as": "x"}},  # 已登记 -> 改 E10
            {"expect_e10": {"eq": "EQ1", "same_as": "$b"}},
        ],
    }
    rep = Runner(c).run(parse(data))
    assert rep["status"] == FAILED and "E10" in rep["reason"]


def test_clear_already_cleared_alarm_expects_cleared_false():
    """D55 OQ-5 / B9：报警已不是 active 时 clear -> 200，顶层 cleared=false。"""
    c = FakeClient(paths=BASE_PATHS | B9)
    steps = [
        {"alarm_set": {"eq": "EQ1", "alid": "1001", "save_as": "x"}},
        {"alarm_clear": {"eq": "EQ1", "alarm": "$x", "expect": {"body": {"cleared": True}}}},
        {"alarm_clear": {"eq": "EQ1", "alarm": "$x", "expect": {"body": {"cleared": False, "duplicate": False}}}},
    ]
    rep = Runner(c).run(parse({"run_id": "c", "steps": steps}))
    assert rep["status"] == PASSED, rep
    assert c.calls[-1][1] == "/mes/eqp/alarms/a-1/clear"
    assert "cleared_at" in c.calls[-1][2] and "occurred_at" not in c.calls[-1][2]
    bad = steps[:2] + [{"alarm_clear": {"eq": "EQ1", "alarm": "$x", "expect": {"body": {"cleared": True}}}}]
    rep = Runner(FakeClient(paths=BASE_PATHS | B9)).run(parse({"run_id": "c", "steps": bad}))
    assert rep["status"] == FAILED and "body.cleared" in rep["reason"]


def test_alarm_set_uses_set_at_and_list_detail_code():
    c = FakeClient(paths=BASE_PATHS | B9)
    rep = Runner(c).run(parse({"run_id": "s", "steps": [{"alarm_set": {"eq": "EQ1", "alid": "1001"}}]}))
    assert rep["status"] == PASSED, rep
    body = [x for x in c.calls if x[0] == "POST"][0][2]
    assert "set_at" in body and "occurred_at" not in body and "source" not in body
    assert Resp(422, {"detail": [{"type": "time_in_future", "code": "time_in_future"}]}).code == "time_in_future"


def test_alarm_clear_by_alid_rejected():
    import pytest

    from sim.scenario import ScenarioError

    with pytest.raises(ScenarioError, match="ALID"):
        parse({"run_id": "x", "steps": [{"alarm_clear": {"eq": "EQ1", "alid": "1001"}}]})


def test_future_time_offset():
    c = FakeClient(paths=BASE_PATHS | B9)
    step = {"eq": "EQ1", "alid": "1001", "time_offset_s": 600, "expect": {"status": 422, "code": "time_in_future"}}
    rep = Runner(c).run(parse({"run_id": "f", "steps": [{"alarm_set": step}]}))
    assert rep["status"] == PASSED, rep
    assert c.holds == 0


def test_bundled_tool_life_warn_then_hard_block():
    c = FakeClient(paths=BASE_PATHS | B10)
    rep = Runner(c).run(load(SCN / "tool-life-block.yaml"))
    assert rep["status"] == PASSED, rep
    assert c.usage == 1000  # 等于上限即硬拦（>=）
    ins = [x for x in c.calls if x[1].endswith("/track_in")]
    assert len(ins) == 2 and all(x[2]["tool_ids"] == ["t-sim"] for x in ins)
    assert c.calls[0][0] == "GET"
    reset = [x for x in c.calls if x[1] == "/mes/eqp/tools/t-sim/reset"]
    assert reset and reset[0][2]["reason_id"] == "r-rw" and "external_event_id" not in reset[0][2]


def test_tool_life_below_warn_not_blocked():
    c = FakeClient(paths=BASE_PATHS | B10)
    data = {
        "run_id": "w",
        "steps": [
            {
                "tool_usage": {
                    "eq": "EQ1",
                    "tool": "T1",
                    "delta": 950,
                    "expect": {"body": {"tool.life_state": "warning"}},
                }
            },
            {"track_in": {"eq": "EQ1", "lot": "L1", "tools": ["T1"]}},  # 预警区间不拦
        ],
    }
    assert Runner(c).run(parse(data))["status"] == PASSED


def test_tool_mount_replace_unmount_and_logs():
    c = FakeClient(paths=BASE_PATHS | B10)
    steps = [
        {"tool_mount": {"eq": "EQ1", "tool": "T1", "port": "P1"}},
        {"tool_mount": {"eq": "EQ1", "tool": "T1", "expect": {"status": 409, "code": "tool_already_mounted"}}},
        {
            "tool_replace": {
                "tool": "T1",
                "new_tool": "T2",
                "reason": "broken",
                "expect": {"body": {"unmounted.unmount_reason": "broken", "mounted.port_code": "P1"}},
            }
        },
        {"tool_unmount": {"tool": "T1", "reason": "pm", "expect": {"status": 409, "code": "tool_not_mounted"}}},
        {"tool_unmount": {"tool": "T2", "reason": "pm"}},
        {"expect_tool_log": {"tool": "T2", "log": "mounts", "count": 1, "last": {"unmount_reason": "pm"}}},
        {"tool_usage": {"eq": "EQ1", "tool": "T1", "delta": -1, "expect": {"status": 422, "code": "reason_required"}}},
        {"tool_usage": {"eq": "EQ1", "tool": "T1", "delta": 3}},
        {"tool_usage": {"eq": "EQ1", "tool": "T1", "delta": -1, "reason": "REWORK"}},
        {"expect_tool_log": {"tool": "T1", "count": 2, "last": {"kind": "adjust", "count_after": "2"}}},
    ]
    rep = Runner(c).run(parse({"run_id": "tm", "steps": steps}))
    assert rep["status"] == PASSED, rep
    posts = [x for x in c.calls if x[0] == "POST"]
    assert posts[0][1] == "/mes/eqp/tools/t-1/mount" and posts[0][2]["equipment_id"] == "e-1"
    assert all("source" not in x[2] for x in posts)  # D30
    assert all(x[3] and x[3].get("Idempotency-Key") for x in posts)
    gets = [x[1] for x in c.calls if x[0] == "GET" and "/tools/" in x[1]]
    assert gets == ["/mes/eqp/tools/t-2/mounts", "/mes/eqp/tools/t-1/usage"]


def test_tool_steps_validation():
    import pytest

    from sim.scenario import ScenarioError

    for bad in (
        {"tool_reset": {"tool": "T1"}},
        {"tool_unmount": {"tool": "T1"}},
        {"tool_replace": {"tool": "T1", "reason": "pm"}},
        {"tool_mount": {"tool": "T1"}},
        {"expect_tool_log": {}},
    ):
        with pytest.raises(ScenarioError):
            parse({"run_id": "x", "steps": [bad]})


def test_b11_mode_disabled_by_default_and_placeholder():
    data = {"run_id": "b", "steps": [{"state": {"eq": "EQ1", "to": "PRD"}}]}
    assert Runner(FakeClient()).mode == "manual"
    rep = Runner(FakeClient(), mode="b11").run(parse(data))
    assert rep["status"] == SKIPPED and "B11" in rep["reason"]
    c = FakeClient(paths=BASE_PATHS | B11)
    rep = Runner(c, mode="b11").run(parse(data))
    assert rep["status"] == PASSED, rep
    m, path, body, headers, _ = [x for x in c.calls if x[0] == "POST"][0]
    assert path == "/mes/eap/events"
    assert body["source"] == "simulator" and body["external_event_id"] == "sim:b:EQ1:1"
    assert body["event_type"] == "state" and body["payload"]["to_state_id"] == "s-prd"
    assert headers == {"Idempotency-Key": "sim:b:EQ1:1"}


def test_scenario_rejects_bad_new_steps():
    import pytest

    from sim.scenario import ScenarioError

    with pytest.raises(ScenarioError):
        parse({"run_id": "x", "steps": [{"alarm_clear": {"eq": "EQ1"}}]})
    with pytest.raises(ScenarioError):
        parse({"run_id": "x", "steps": [{"expect_alarm": {}}]})
    assert yaml  # 保持导入使用
