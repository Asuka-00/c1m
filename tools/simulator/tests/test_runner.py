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
        {"expect_hold": {"lot": "L1", "present": False}},  # D58：报警不 Hold
        {"replay": {"eq": "EQ1", "seq": 1}},
        {"expect_hold": {"lot": "L1", "present": False}},
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
    assert c.holds == 0
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


def test_bundled_alarm_udt_skipped_without_b9():
    c = FakeClient()
    rep = Runner(c).run(load(SCN / "alarm-udt-block.yaml"))
    assert rep["status"] == SKIPPED and "B9" in rep["reason"]
    assert not [x for x in c.calls if x[0] == "POST"]


def test_bundled_alarm_udt_block_d58_passes_with_b9_b11():
    c = FakeClient(paths=BASE_PATHS | B9 | B11)
    rep = Runner(c).run(load(SCN / "alarm-udt-block.yaml"))
    assert rep["status"] == PASSED, rep
    assert c.holds == 0  # D58：报警不 Hold
    blocked = [x for x in rep["steps"] if x["kind"] == "track_in"]
    assert [x["status"] for x in blocked] == [409, 200]  # UDT 拦，切回 SBY 后通过
    assert c.e10 == "SBY"
    unreg = [r for r in c.alarm_rows.values() if r["unregistered"]]
    assert len(unreg) == 1 and unreg[0]["lots"] == [{"lot_id": "l-fx2"}]  # 仍写 mes_alarm_lot
    posts = [x for x in c.calls if x[0] == "POST" and not x[1].startswith("/mes/alarm_code")]
    assert all("source" not in (x[2] or {}) for x in posts)  # D30
    assert all(x[3] and x[3].get("Idempotency-Key") for x in posts)
    # D59 种子：联动只有 none / set_state + target_state
    assert {k: (v["action"], v["target_state"]) for k, v in c.alarm_codes.items()} == {
        "1001": ("set_state", "UDT"),
        "1002": ("set_state", "PRD"),
        "1003": ("none", None),
    }
    # D58 补充：报警切 UDT 的履历 trigger=equipment；手工切回 SBY 是 trigger=manual
    assert [(h["to_state_id"], h["trigger"], h["source"]) for h in c.e10_hist] == [
        ("s-sby", "manual", "manual"),
        ("s-udt", "equipment", "manual"),
    ]


def test_expect_e10_same_as_detects_change():
    c = FakeClient(paths=BASE_PATHS | B9)
    data = {
        "run_id": "u",
        "steps": [
            {"expect_e10": {"eq": "EQ1", "save_as": "b"}},
            {"state": {"eq": "EQ1", "to": "PRD"}},
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


def test_alarm_clear_needs_exactly_one_of_alarm_or_alid():
    import pytest

    from sim.scenario import ScenarioError

    with pytest.raises(ScenarioError, match="ALID"):
        parse({"run_id": "x", "steps": [{"alarm_clear": {"eq": "EQ1", "alid": "1001", "alarm": "$a"}}]})
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
    assert c.usage == 0 and c.tool_status == "available" and c.expiry is None  # 场景结束已恢复
    ins = [x for x in c.calls if x[1].endswith("/track_in")]
    # 预警放行 1 次 + P2-D3 三种不可用（到上限 / 过期 / retired）各被拦 1 次
    assert len(ins) == 4 and all(x[2]["tool_ids"] == ["t-sim"] for x in ins)
    st = [x["status"] for x in rep["steps"] if x["kind"] == "track_in"]
    assert st == [200, 409, 409, 409]
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


def test_b11_mode_disabled_by_default():
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
    assert headers is None  # B11 幂等靠信封里的 external_event_id
    assert set(body) == {"source", "external_event_id", "event_type", "equipment_id", "payload"}


def test_scenario_rejects_bad_new_steps():
    import pytest

    from sim.scenario import ScenarioError

    with pytest.raises(ScenarioError):
        parse({"run_id": "x", "steps": [{"alarm_clear": {"eq": "EQ1"}}]})
    with pytest.raises(ScenarioError):
        parse({"run_id": "x", "steps": [{"expect_alarm": {}}]})
    assert yaml  # 保持导入使用


# ---- B11 8294b63 / D57 ----
from fake import REGISTERED_ALIDS  # noqa: E402,F401

ALL = BASE_PATHS | B9 | B10 | B11


def posts(c, path=None):
    return [x for x in c.calls if x[0] == "POST" and (path is None or x[1] == path)]


def test_b11_tool_usage_payload_has_tool_id_not_equipment():
    c = FakeClient(paths=ALL)
    data = {"run_id": "u", "steps": [{"tool_usage": {"eq": "EQ1", "tool": "T1", "delta": 5}}]}
    rep = Runner(c, mode="b11").run(parse(data))
    assert rep["status"] == PASSED, rep
    body = posts(c, "/mes/eap/events")[0][2]
    assert body["equipment_id"] == "e-1" and body["event_type"] == "tool_usage"
    assert body["payload"] == {"delta": "5", "tool_id": "t-1"}


def test_b11_alarm_clear_sends_alid_never_alarm_id():
    c = FakeClient(paths=ALL)
    data = {
        "run_id": "c",
        "steps": [
            {"alarm_set": {"eq": "EQ1", "alid": "1001", "save_as": "a"}},
            {"alarm_clear": {"eq": "EQ1", "alarm": "$a", "expect": {"body": {"cleared": True}}}},
            {"alarm_clear": {"eq": "EQ1", "alid": "1001", "expect": {"body": {"cleared": False, "data": None}}}},
        ],
    }
    rep = Runner(c, mode="b11").run(parse(data))
    assert rep["status"] == PASSED, rep
    clears = [b for _, _, b, _, _ in posts(c, "/mes/eap/events") if b["event_type"] == "alarm_clear"]
    assert len(clears) == 2
    for b in clears:
        assert b["payload"]["alid"] == "1001" and "alarm_id" not in b["payload"]
        assert set(b["payload"]) <= {"alid", "cleared_at", "comment"}


def test_b11_save_as_uses_result_id_and_duplicate_from_envelope():
    c = FakeClient(paths=ALL)
    data = {
        "run_id": "d",
        "steps": [
            {"alarm_set": {"eq": "EQ1", "alid": "1001", "save_as": "a", "expect": {"body": {"duplicate": False}}}},
            {"replay": {"eq": "EQ1", "seq": 1, "expect": {"body": {"duplicate": True, "data.alid": "1001"}}}},
            {"expect_alarm": {"alarm": "$a", "alarm_status": "active"}},
        ],
    }
    rep = Runner(c, mode="b11").run(parse(data))
    assert rep["status"] == PASSED, rep


def test_b11_forbidden_without_eap_service():
    c = FakeClient(paths=ALL)
    c.service = False
    rep = Runner(c, mode="b11").run(parse({"run_id": "f", "steps": [{"state": {"eq": "EQ1", "to": "PRD"}}]}))
    assert rep["status"] == FAILED and "403" in rep["reason"]


def test_manual_alarm_clear_by_alid_endpoint():
    c = FakeClient(paths=ALL)
    data = {
        "run_id": "m",
        "steps": [
            {"alarm_set": {"eq": "EQ1", "alid": "1001"}},
            {"alarm_clear": {"eq": "EQ1", "alid": "1001", "expect": {"body": {"cleared": True}}}},
            {"alarm_clear": {"eq": "EQ1", "alid": "1001", "expect": {"body": {"cleared": False, "data": None}}}},
        ],
    }
    rep = Runner(c).run(parse(data))
    assert rep["status"] == PASSED, rep
    m, path, body, headers, _ = posts(c, "/mes/eqp/alarms/clear")[0]
    assert body["equipment_id"] == "e-1" and body["alid"] == "1001" and "source" not in body
    assert headers == {"Idempotency-Key": "sim:m:EQ1:2"}


def test_alarm_clear_by_alid_skipped_without_b11_manual_endpoint():
    rep = Runner(FakeClient(paths=BASE_PATHS | B9)).run(
        parse({"run_id": "s", "steps": [{"alarm_clear": {"eq": "EQ1", "alid": "1001"}}]})
    )
    assert rep["status"] == SKIPPED and "B11" in rep["reason"]


def test_manual_e10_and_stage_carry_idempotency_key():
    c = FakeClient(paths=ALL)
    data = {"run_id": "k", "steps": [{"state": {"eq": "EQ1", "to": "PRD"}}, {"move_in": {"eq": "EQ1", "lot": "L1"}}]}
    assert Runner(c).run(parse(data))["status"] == PASSED
    keys = [h for _, _, _, h, _ in posts(c)]
    assert keys == [{"Idempotency-Key": "sim:k:EQ1:1"}, {"Idempotency-Key": "sim:k:EQ1:2"}]


D57 = {
    "run_id": "d57",
    "steps": [
        {"state": {"eq": "EQ1", "to": "PRD"}},
        {"reuse": {"eq": "EQ1", "seq": 1, "change": {"to": "SBY"}}},
        {"expect_e10": {"eq": "EQ1", "state": "PRD"}},
        {"replay": {"eq": "EQ1", "seq": 1, "expect": "idempotent"}},
        {"tool_usage": {"eq": "EQ1", "tool": "T1", "delta": 10}},
        {"reuse": {"eq": "EQ1", "seq": 2, "change": {"delta": 20}}},
        {"replay": {"eq": "EQ1", "seq": 2, "expect": {"body": {"duplicate": True, "tool.usage_count": "10"}}}},
        {"expect_tool_log": {"tool": "T1", "count": 1, "last": {"delta": "10"}}},
    ],
}


def test_d57_reuse_manual():
    c = FakeClient(paths=ALL)
    rep = Runner(c).run(parse(D57))
    assert rep["status"] == PASSED, rep
    assert c.e10_writes == 1  # 重放不写、换内容不写
    reuse = [x for x in posts(c, "/mes/eqp/e-1/e10")]
    assert reuse[1][3] == {"Idempotency-Key": "sim:d57:EQ1:1"} and reuse[1][2]["to_state_id"] == "s-sby"


def test_d57_reuse_b11():
    c = FakeClient(paths=ALL)
    rep = Runner(c, mode="b11").run(parse(D57))
    assert rep["status"] == PASSED, rep
    assert c.e10_writes == 1 and len(c.events) == 2
    ev = posts(c, "/mes/eap/events")
    assert ev[1][2]["external_event_id"] == ev[0][2]["external_event_id"]
    assert ev[1][2]["payload"]["to_state_id"] == "s-sby"


def test_reuse_detects_silent_acceptance():
    c = FakeClient(paths=ALL)
    orig = c.request

    def lax(method, path, *a, **k):  # 后端没按 D57 拒绝：同键换内容也 200
        if method == "POST" and path.endswith("/e10") and c.e10_writes:
            return Resp(200, {"data": {"id": "x"}})
        return orig(method, path, *a, **k)

    c.request = lax
    rep = Runner(c).run(parse({"run_id": "z", "steps": D57["steps"][:2]}))
    assert rep["status"] == FAILED and "idempotency_key_reused" in rep["reason"]


def test_reuse_validation():
    import pytest

    from sim.scenario import ScenarioError

    with pytest.raises(ScenarioError):
        parse({"run_id": "x", "steps": [{"reuse": {"eq": "EQ1", "seq": 1}}]})


def test_bundled_scenarios_pass_in_both_modes():
    from sim.scenario import load

    for mode in ("manual", "b11"):
        for name in ("alarm-udt-block", "tool-life-block", "idempotency-d57"):
            c = FakeClient(paths=ALL)
            rep = Runner(c, mode=mode).run(load(f"scenarios/{name}.yaml"))
            assert rep["status"] == PASSED, (mode, name, rep)


def test_alarm_udt_block_fails_if_backend_holds_on_alarm():
    """D58 回归：后端若仍因报警 Hold 批次，场景要失败。"""
    c = FakeClient(paths=ALL)
    orig = c._dispatch

    def holding(method, path, body, params):
        r = orig(method, path, body, params)
        if method == "POST" and path.endswith("/alarms") and r.status == 200:
            c.holds = 1
        return r

    c._dispatch = holding
    rep = Runner(c).run(load(SCN / "alarm-udt-block.yaml"))
    assert rep["status"] == FAILED and "Hold" in rep["reason"]


def _alarm_steps(extra, **kw):
    c = FakeClient(paths=ALL, **kw)
    c.alarm_codes["1001"].update(action="set_state", target_state="UDT")
    return c, Runner(c).run(parse({"run_id": "a", "steps": extra}))


def test_alarm_set_state_records_trigger_equipment_and_no_hold():
    c, rep = _alarm_steps(
        [
            {
                "alarm_set": {
                    "eq": "EAP-DA01",
                    "alid": "1001",
                    "lots": ["FX0002"],
                    "save_as": "a",
                    "expect": {"body": {"state_changed": True}},
                }
            },
            {"expect_alarm": {"alarm": "$a", "source": {"manual": "manual", "b11": "simulator"}}},
            {"expect_e10_history": {"eq": "EAP-DA01", "last": {"to": "UDT", "trigger": "equipment"}}},
            {"expect_hold": {"lot": "FX0002", "present": False}},
        ]
    )
    assert rep["status"] == PASSED, rep
    assert c.e10 == "UDT"


def test_b11_alarm_source_is_simulator():
    c = FakeClient(paths=ALL)
    c.alarm_codes["1001"].update(action="set_state", target_state="UDT")
    steps = [
        {"alarm_set": {"eq": "EAP-DA01", "alid": "1001", "save_as": "a"}},
        {"expect_alarm": {"alarm": "$a", "source": {"manual": "manual", "b11": "simulator"}}},
        {"expect_e10_history": {"eq": "EAP-DA01", "last": {"trigger": "equipment", "source": "simulator"}}},
    ]
    rep = Runner(c, mode="b11").run(parse({"run_id": "a", "steps": steps}))
    assert rep["status"] == PASSED, rep


def test_expect_e10_history_fails_on_wrong_trigger():
    _, rep = _alarm_steps(
        [
            {"state": {"eq": "EAP-DA01", "to": "PRD"}},
            {"expect_e10_history": {"eq": "EAP-DA01", "last": {"trigger": "equipment"}}},
        ]
    )
    assert rep["status"] == FAILED and "trigger" in rep["reason"]


def test_alarm_state_skip_returns_200_with_reason():
    c, rep = _alarm_steps(
        [
            {"seed_alarm_code": {"eq": "EAP-DA01", "alid": "1002", "action": "set_state", "target_state": "PRD"}},
            {"alarm_set": {"eq": "EAP-DA01", "alid": "1001"}},
            {
                "alarm_set": {
                    "eq": "EAP-DA01",
                    "alid": "1002",
                    "expect": {
                        "status": 200,
                        "body": {"state_changed": False, "state_skip_reason": "$nonempty"},
                    },
                }
            },
            {"expect_e10": {"eq": "EAP-DA01", "state": "UDT"}},
        ]
    )
    assert rep["status"] == PASSED, rep


def test_manual_alarm_reuse_changed_body_422():
    c, rep = _alarm_steps(
        [
            {"alarm_set": {"eq": "EAP-DA01", "alid": "1001"}},
            {"reuse": {"eq": "EAP-DA01", "seq": 1, "change": {"alid": "1003"}}},
            {"reuse": {"eq": "EAP-DA01", "seq": 1, "change": {"set_at": "2026-01-01T00:00:00.000Z"}}},
        ]
    )
    assert rep["status"] == PASSED, rep
    assert len(c.alarm_rows) == 1  # 没写入


def test_seed_alarm_code_d59_validation():
    c, rep = _alarm_steps(
        [
            {"seed_alarm_code": {"eq": "EAP-DA01", "alid": "7", "action": "set_state", "expect": {"status": 422}}},
            {
                "seed_alarm_code": {
                    "eq": "EAP-DA01",
                    "alid": "7",
                    "action": "none",
                    "target_state": "UDT",
                    "expect": {"status": 422},
                }
            },
            {"seed_alarm_code": {"eq": "EAP-DA01", "alid": "7", "action": "set_state", "target_state": "UDT"}},
        ]
    )
    assert rep["status"] == PASSED, rep
    assert c.alarm_codes["7"]["target_state"] == "UDT"
    import pytest

    from sim.scenario import ScenarioError

    with pytest.raises(ScenarioError):
        parse({"run_id": "x", "steps": [{"seed_alarm_code": {"eq": "EQ1", "alid": "1", "action": "hold_lot"}}]})


def test_tool_life_block_all_items_agree():
    """517b0a0 P2-D3：一旦有一条 tool_life 不是 block 或写着 tools available，断言要失败。"""
    c = FakeClient(paths=ALL)
    c.usage = 1000.0
    orig = c._dispatch

    def legacy(method, path, body, params):
        r = orig(method, path, body, params)
        if r.status == 409 and path.endswith("/track_in"):
            res = r.body["detail"]["results"]
            res[1] = dict(res[1], result="pass", message="tools available")
        return r

    c._dispatch = legacy
    exp = {
        "status": 409,
        "check": {"check_type": "tool_life", "result": "block", "all": True, "not_message": "tools available"},
    }
    rep = Runner(c).run(
        parse(
            {
                "run_id": "t",
                "steps": [{"track_in": {"eq": "EAP-DA01", "lot": "FX0003", "tools": ["T-SIM-01"], "expect": exp}}],
            }
        )
    )
    assert rep["status"] == FAILED and "tools available" in rep["reason"]


def test_tool_set_expired_and_unavailable_block():
    c = FakeClient(paths=ALL)
    exp = {
        "status": 409,
        "code": "check_blocked",
        "check": {"check_type": "tool_life", "result": "block", "all": True, "min_count": 2},
    }
    rep = Runner(c).run(
        parse(
            {
                "run_id": "t",
                "steps": [
                    {"tool_set": {"tool": "T-SIM-01", "fields": {"expiry_date": -1}}},
                    {"track_in": {"eq": "EAP-DA01", "lot": "FX0003", "tools": ["T-SIM-01"], "expect": exp}},
                    {"tool_set": {"tool": "T-SIM-01", "fields": {"expiry_date": None, "tool_status": "retired"}}},
                    {"track_in": {"eq": "EAP-DA01", "lot": "FX0003", "tools": ["T-SIM-01"], "expect": exp}},
                    {"tool_set": {"tool": "T-SIM-01", "fields": {"tool_status": "available"}}},
                    {"track_in": {"eq": "EAP-DA01", "lot": "FX0003", "tools": ["T-SIM-01"]}},
                ],
            }
        )
    )
    assert rep["status"] == PASSED, rep


def test_check_all_fields_list():
    """all: [result] 只要求 result 每条都满足，overridable 任一条满足即可（内置硬拦截给 false）。"""
    hits = [
        {"check_type": "tool_life", "result": "block", "overridable": False},
        {"check_type": "tool_life", "result": "block", "overridable": True},
    ]
    r = Resp(409, {"detail": {"code": "check_blocked", "results": hits}})
    ok = {
        "status": 409,
        "check": {"check_type": "tool_life", "result": "block", "overridable": False, "all": ["result"]},
    }
    assert check_expect(r, ok) == []
    strict = {"status": 409, "check": {"check_type": "tool_life", "overridable": False, "all": True}}
    assert check_expect(r, strict)


def test_pending_step_is_skipped_not_failed_and_nonempty():
    c, rep = _alarm_steps(
        [
            {"alarm_set": {"eq": "EAP-DA01", "alid": "1001", "expect": {"body": {"state_skip_reason": "$nonempty"}}}},
        ]
    )
    assert rep["status"] == FAILED and "非空" in rep["reason"]  # 切换成功时 reason 为空
    c, rep = _alarm_steps(
        [
            {"expect_alarm": {"alarm": "$none", "state_skip_reason": "transition_not_allowed", "pending": "等后端"}},
        ]
    )
    assert rep["status"] == PASSED and rep["pending"] == [1]


@__import__("pytest").mark.skip(
    reason="等后端 D59 补充提交：state_skip_reason 改错误码，报警履历带 state_changed/state_skip_reason"
)
def test_d59_skip_reason_error_codes():
    cases = {"NOPE": "unknown_state", "UDT": "already_in_state", "PRD": "transition_not_allowed"}
    for target, code in cases.items():
        c = FakeClient(paths=ALL)
        c.e10 = "UDT"
        c.alarm_codes["1001"].update(action="set_state", target_state=target)
        steps = [
            {
                "alarm_set": {
                    "eq": "EAP-DA01",
                    "alid": "1001",
                    "save_as": "a",
                    "expect": {"body": {"state_changed": False, "state_skip_reason": code}},
                }
            },
            {"expect_alarm": {"alarm": "$a", "state_changed": False, "state_skip_reason": code}},
        ]
        rep = Runner(c).run(parse({"run_id": "a", "steps": steps}))
        assert rep["status"] == PASSED, (target, rep)
