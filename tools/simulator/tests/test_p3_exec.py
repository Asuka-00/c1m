"""P3 打标 / 光罩执行器：对 mock HTTP 服务（真实 socket）跑。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from mock_http import MARKING_PATHS, RETICLE_PATHS, MockServer

from sim.client import Client
from sim.p3 import check_p3_expect, match, route_missing
from sim.runner import FAILED, PASSED, Runner
from sim.scenario import load, parse


def run(steps, enabled=None, run_id="t1"):
    with MockServer(enabled) as m:
        rep = Runner(Client(m.url, tenant="t"), stop_on_fail=False).run(parse({"run_id": run_id, "steps": steps}))
        return rep, m.state


def oks(rep):
    return [s.get("ok") for s in rep["steps"]]


# ---------------------------------------------------------------- 光罩
def test_idem_header_sent_and_no_idem_omits_it():
    rep, st = run(
        [
            {
                "reticle_hold": {
                    "reticle": "R-SIM-04",
                    "reason": "x",
                    "no_idem": True,
                    "expect": {"status": 422, "code": "missing", "loc": ["header", "Idempotency-Key"]},
                }
            },
            {"reticle_hold": {"reticle": "R-SIM-04", "reason": "x", "idem": "h1"}},
        ]
    )
    assert rep["status"] == PASSED, rep
    posts = [r for r in st.requests if r["method"] == "POST"]
    assert posts[0]["idem"] is None and posts[1]["idem"] == "t1:h1"
    assert posts[0]["body"] == {"reason": "x"}


def test_relative_time_and_d82_boundaries():
    rep, st = run(
        [
            {
                "reticle_mount": {
                    "idem": "a",
                    "eq": "EAP-LT01",
                    "reticle": "R-NOT-EXIST",
                    "slot": "S1",
                    "mounted_at": "$now+301s",
                    "expect": {
                        "status": 422,
                        "type": "value_error",
                        "loc": ["body", "mounted_at"],
                        "ctx": {"reason": "future_time"},
                    },
                }
            },
            {
                "reticle_mount": {
                    "idem": "b",
                    "eq": "EAP-LT01",
                    "reticle": "R-NOT-EXIST",
                    "slot": "S1",
                    "mounted_at": "2026-10-15T01:00:00",
                    "expect": {"status": 422, "type": "timezone_required"},
                }
            },
            {
                "reticle_mount": {
                    "idem": "c",
                    "eq": "EAP-LT01",
                    "reticle": "R-NOT-EXIST",
                    "slot": "S1",
                    "mounted_at": "$now+299s",
                    "expect": {"status": 404},
                }
            },
            {
                "reticle_mount": {
                    "idem": "d",
                    "eq": "EAP-LT01",
                    "reticle": "R-SIM-07",
                    "slot": "S7",
                    "mounted_at": "$now+200s",
                    "save_as": "bm7",
                }
            },
            {
                "reticle_unmount": {
                    "idem": "e",
                    "reticle": "R-SIM-07",
                    "unmounted_at": "$now-1h",
                    "expect": {"status": 409, "code": "time_out_of_order"},
                }
            },
            {"reticle_unmount": {"idem": "f", "reticle": "R-SIM-07", "unmounted_at": "$bm7.mounted_at"}},
            {
                "expect_reticle_history": {
                    "reticle": "R-SIM-07",
                    "latest_of": "mount",
                    "fields": {"mounted_at": "$bm7.mounted_at", "unmounted_at": "$utc_z"},
                }
            },
        ]
    )
    assert rep["status"] == PASSED, rep
    mount = next(r for r in st.requests if r["idem"] == "t1:d")
    t = datetime.fromisoformat(mount["body"]["mounted_at"].replace("Z", "+00:00"))
    assert timedelta(seconds=190) < t - datetime.now(timezone.utc) < timedelta(seconds=201)
    assert mount["body"]["equipment_id"] == "eq-lt01" and mount["body"]["slot_code"] == "S7"


def test_replay_reused_detail_object_and_absent():
    rep, _ = run(
        [
            {
                "reticle_mount": {
                    "idem": "m4",
                    "eq": "EAP-LT01",
                    "reticle": "R-SIM-04",
                    "slot": "S9",
                    "save_as": "mm4",
                    "expect": {"status": 200, "absent": ["duplicate"]},
                }
            },
            {"reticle_replay": {"of": "mm4", "expect": {"status": 200, "absent": ["duplicate"]}}},
            {
                "reticle_mount": {
                    "idem": "m4",
                    "eq": "EAP-LT01",
                    "reticle": "R-SIM-04",
                    "slot": "S8",
                    "expect": {"status": 422, "code": "idempotency_key_reused", "detail_object": True},
                }
            },
            {
                "reticle_replay": {
                    "of": "mm4",
                    "change": {"slot_code": "S7"},
                    "expect": {"status": 422, "code": "idempotency_key_reused"},
                }
            },
            {"expect_reticle": {"reticle": "R-SIM-04", "fields": {"status_code": "in_use", "mount_count": 1}}},
            {
                "expect_reticle_events": {
                    "reticle": "R-SIM-04",
                    "count": {"reticle.mounted": 1},
                    "latest": {
                        "event": "reticle.mounted",
                        "payload.source": "manual",
                        "payload.external_event_id": None,
                    },
                }
            },
        ]
    )
    assert rep["status"] == PASSED, rep


def test_wrong_expectation_fails_with_message():
    rep, _ = run(
        [
            {
                "reticle_hold": {
                    "reticle": "R-SIM-04",
                    "reason": "x",
                    "no_idem": True,
                    "expect": {"status": 422, "loc": ["body", "reason"]},
                }
            }
        ]
    )
    assert rep["status"] == FAILED and "loc" in rep["reason"]


def test_eap_report_ext_duplicate_and_ref():
    rep, st = run(
        [
            {
                "reticle_report": {
                    "eq": "EAP-LT01",
                    "reticle": "R-SIM-03",
                    "kind": "mount",
                    "seq": 1,
                    "payload": {"slot_code": "S1"},
                    "save_as": "m1",
                    "expect": {"status": 200, "body": {"duplicate": False}},
                }
            },
            {"reticle_replay": {"of": "m1", "expect": {"status": 200, "body": {"duplicate": True}}}},
            {
                "reticle_report": {
                    "eq": "EAP-LT01",
                    "reticle": "R-SIM-03",
                    "kind": "mount",
                    "seq": 1,
                    "payload": {"slot_code": "S2"},
                    "expect": {"status": 422, "code": "idempotency_key_reused", "detail_object": True},
                }
            },
            {
                "expect_reticle_history": {
                    "reticle": "R-SIM-03",
                    "latest_of": "mount",
                    "count_of": {"mount": 1},
                    "fields": {"source": "simulator", "external_event_id": "$ext.m1"},
                }
            },
        ]
    )
    assert rep["status"] == PASSED, rep
    ev = next(r for r in st.requests if r["path"] == "/mes/eap/events")
    assert ev["idem"] is None and ev["body"]["external_event_id"] == "sim:t1:EAP-LT01:1"
    assert ev["body"]["event_type"] == "reticle_mount" and ev["body"]["source"] == "simulator"


def test_unimplemented_route_is_not_failure():
    enabled = RETICLE_PATHS - {"/mes/reticle/{reticle_id}/clean-start"}
    rep, _ = run(
        [
            {"reticle_clean_start": {"idem": "c", "reticle": "R-SIM-04"}},  # openapi 没有 -> 未实现
            {"reticle_hold": {"reticle": "R-SIM-04", "reason": "x", "idem": "h"}},
        ],
        enabled=enabled,
    )
    assert rep["status"] == PASSED and rep["unimplemented"] == [1], rep
    assert rep["steps"][0]["unimplemented"] and "未实现" in rep["steps"][0]["message"]


def test_route_404_at_runtime_and_unknown_event_type_are_unimplemented():
    rep, _ = run(
        [
            {
                "marking_report": {
                    "eq": "EAP-MK01",
                    "lot": "MK0001",
                    "seq": 20,
                    "kind": "print",
                    "save_as": "r1",
                    "payload": {"trace_code": "A"},
                    "expect": {"status": 409},
                }
            },
            {"marking_replay": {"of": "r1", "expect": {"status": 200}}},
        ]
    )
    assert rep["status"] == PASSED and rep["unimplemented"] == [1, 2], rep


def test_scenario_does_not_skip_when_p3_adapters_missing():
    rep, _ = run([{"marking_create": {"lot": "MK0001", "idem": "c"}}], enabled=set())
    assert rep["status"] == PASSED and rep["unimplemented"] == [1], rep


# ---------------------------------------------------------------- 打标
def test_marking_flow_cfg_issued_print_seq_errors():
    rep, st = run(
        [
            {
                "marking_create": {
                    "lot": "MK0001",
                    "idem": "c1",
                    "save_as": "c1",
                    "expect": {"body": {"data.voided": False}},
                }
            },
            {"marking_replay": {"of": "c1", "expect": {"status": 200, "absent": ["duplicate"]}}},
            {
                "marking_config": {
                    "save_as": "cfg",
                    "pattern_allowed": True,
                    "expect": {"body": {"trace_code_max_length": 32, "trace_code_pattern": "$nonempty"}},
                }
            },
            {
                "marking_config": {
                    "set": {"trace_code_pattern": "^[A-Z]{1,3}$"},
                    "idem": "cf",
                    "expect": {
                        "status": 422,
                        "errors": [
                            {
                                "type": "value_error",
                                "loc": ["body", "trace_code_pattern"],
                                "ctx": {"reason": "pattern_unsupported"},
                            }
                        ],
                    },
                }
            },
            {
                "marking_print": {
                    "lot": "MK0001",
                    "eq": "EAP-MK01",
                    "idem": "tc",
                    "trace_code": "ab_1" + "x" * 40,
                    "expect": {
                        "status": 422,
                        "errors": [
                            {
                                "type": "value_error",
                                "loc": ["body", "trace_code"],
                                "ctx": {"reason": "max_length", "max_length": "$cfg.trace_code_max_length"},
                            },
                            {
                                "type": "value_error",
                                "loc": ["body", "trace_code"],
                                "ctx": {"reason": "pattern", "pattern": "$cfg.trace_code_pattern"},
                            },
                        ],
                    },
                }
            },
            {
                "marking_print": {
                    "lot": "MK0001",
                    "eq": "EAP-MK01",
                    "no_idem": True,
                    "expect": {"status": 422, "code": "missing", "loc": ["header", "Idempotency-Key"]},
                }
            },
            {
                "marking_print": {
                    "lot": "MK0001",
                    "eq": "EAP-MK01",
                    "idem": "p1",
                    "save_as": "p1",
                    "expect": {"body": {"data.reprint_count": 0, "data.trace_code": "$nonempty"}},
                }
            },
            {"marking_print": {"lot": "MK0001", "eq": "EAP-MK01", "idem": "p2", "expect": {"status": 422}}},
            {
                "marking_print": {
                    "lot": "MK0001",
                    "eq": "EAP-MK01",
                    "idem": "p3",
                    "reason": "R-MKREPRINT",
                    "comment": "c",
                    "expect": {"body": {"data.seq": 2}},
                }
            },
            {"expect_marking_prints": {"lot": "MK0001", "seqs": [1, 2], "last": {"printed_at": "$utc_z"}}},
            {
                "marking_inspect": {
                    "lot": "MK0001",
                    "result": "pass",
                    "read_code": "WRONG",
                    "idem": "i1",
                    "expect": {
                        "body": {"data.result": "fail", "data.result_overridden": True, "data.print_id": "$print_seq_2"}
                    },
                }
            },
            {
                "marking_inspect": {
                    "lot": "MK0001",
                    "result": "pass",
                    "read_code": "$issued",
                    "idem": "i2",
                    "expect": {"body": {"data.result": "pass", "data.result_overridden": False}},
                }
            },
            {
                "marking_inspect": {
                    "lot": "MK0001",
                    "result": "pass",
                    "omit": ["read_code"],
                    "idem": "i3",
                    "expect": {"status": 422, "errors": [{"type": "missing", "loc": ["body", "read_code"]}]},
                }
            },
            {
                "marking_inspect": {
                    "lot": "MK0001",
                    "result": "pass",
                    "read_code": None,
                    "idem": "i4",
                    "expect": {"status": 422},
                }
            },
            {"expect_marking_inspections": {"lot": "MK0001", "count": 2, "last": {"result": "pass", "seq": 2}}},
            {"expect_marking": {"lot": "MK0001", "fields": {"latest_inspection_status": "pass", "reprint_count": 1}}},
            {
                "marking_void": {
                    "marking": "MK-NOT-EXIST",
                    "reason": "R-MKREPRINT",
                    "idem": "v",
                    "expect": {"status": 404},
                }
            },
        ]
    )
    assert rep["status"] == PASSED, rep
    i3 = next(r for r in st.requests if r["idem"] == "t1:i3")
    i4 = next(r for r in st.requests if r["idem"] == "t1:i4")
    assert "read_code" not in i3["body"] and i4["body"]["read_code"] is None  # omit vs null
    p3 = next(r for r in st.requests if r["idem"] == "t1:p3")
    assert p3["body"]["reason_id"] == "rs-rep" and p3["body"]["equipment_id"] == "eq-mk01"


def test_marking_as_role_without_account_is_skipped(monkeypatch):
    monkeypatch.delenv("SIM_AS_READ_ONLY_TOKEN", raising=False)
    rep, _ = run(
        [
            {"marking_create": {"lot": "MK0001", "idem": "c"}},
            {
                "marking_print": {
                    "lot": "MK0001",
                    "eq": "EAP-MK01",
                    "idem": "ro",
                    "as": "read_only",
                    "expect": {"status": 403},
                }
            },
        ],
        enabled=MARKING_PATHS | {"/mes/{entity}"},
    )
    assert rep["status"] == PASSED and oks(rep) == [True, None], rep


# ---------------------------------------------------------------- 纯函数
def test_match_and_helpers():
    from sim.client import Resp

    assert match("2026-10-15T01:00:00.123Z", "$utc_z") and not match("2026-10-15T01:00:00+08:00", "$utc_z")
    assert match({"a": {"b": "130.000000"}}, {"a.b": "130"})
    assert not match([1, 2], [1])
    r = Resp(
        409,
        {
            "detail": {
                "code": "check_blocked",
                "ctx": {"check": "marking_inspection", "reason": "pending"},
                "overridable": False,
            }
        },
    )
    assert check_p3_expect(r, {"ctx": {"reason": "pending"}, "absent_ctx": ["marking_id"], "overridable": False}) == []
    assert check_p3_expect(r, {"ctx": {"reason": "fail"}})
    assert route_missing(Resp(404, {"detail": "Not Found"})) and not route_missing(Resp(404, {"detail": {"code": "x"}}))


@pytest.mark.parametrize("name", ["marking-report.yaml", "reticle-report.yaml"])
def test_p3_scenarios_stay_draft_and_all_steps_have_executor(name):
    from sim.p3 import P3_EXEC_STEPS

    sc = load(f"scenarios/p3-draft/{name}")
    # marking 仍是草稿；reticle-report 自 ret-report-08（be/p3 f9e9dda 联调）起去掉 draft
    assert bool(sc.draft) == (name == "marking-report.yaml")
    kinds = {s.kind for s in sc.steps} - {
        "precondition",
        "track_out",
        "expect_query_422",
        "expect_datetime_eq_match",
    }  # 通用步骤（1ef2eff 日期探测）
    assert kinds <= P3_EXEC_STEPS, kinds - P3_EXEC_STEPS


def test_seed_guard_only_app_it_eap(monkeypatch):
    from sim.seed_p3 import SeedRefused, guard

    monkeypatch.setenv("SIM_SEED_DB", "app_it_eap")
    guard("http://127.0.0.1:8013")
    for bad in ("http://127.0.0.1:8012", "http://127.0.0.1:8010"):
        with pytest.raises(SeedRefused):
            guard(bad)
    monkeypatch.setenv("SIM_SEED_DB", "app")
    with pytest.raises(SeedRefused):
        guard("http://127.0.0.1:8013")


def test_seed_is_idempotent_against_mock():
    from sim.seed_p3 import Seeder

    with MockServer() as m:
        log = Seeder(Client(m.url, tenant="t")).run()
    assert any(x.startswith("有  equipment EAP-LT01") for x in log)
    assert any(x.startswith("有  reticle R-SIM-03") for x in log)


def test_needs_marks_dependent_step_unimplemented_and_events_unwrap():
    """f9e9dda 联调：needs 依赖未实现步骤 → 未实现；audit changes.payload 为 [旧, 新] 时取新值；page_size<=100。"""
    from sim.p3 import P3Exec, Unimplemented

    ex = P3Exec.__new__(P3Exec)
    ex.unimpl = {"m1"}
    ex.lot = None
    with pytest.raises(Unimplemented):
        ex.step("expect_reticle", {"needs": ["m1"], "reticle": "R"}, {})
    seen = {}

    class _R:
        status = 200
        body = {
            "data": [
                {"action": "reticle.mounted", "changes": {"payload": [None, {"source": "manual"}]}, "created_at": "1"}
            ]
        }

    def _get(path, **kw):
        seen.update(kw)
        return _R()

    ex._get = _get
    ex.path = lambda *a, **k: "/mes/audit_log"
    rows = ex._events("reticle", "x")
    assert seen["page_size"] == 100 and rows[0]["payload"] == {"source": "manual"}


# ---------------------------------------------------------------- D79 补充七
def test_template_call_idem_only_on_writes():
    from sim.p3 import template_call

    def path(adapter, **kw):
        return f"{adapter}:{kw.get('id', '')}"

    def idem(a):
        return None if a.get("no_idem") else f"run:{a.get('idem')}"

    def ident(v):
        return v

    for act in ("create", "update", "new_version", "approve"):
        c = template_call({"action": act, "template": "t1", "idem": "k"}, ident, path, idem)
        assert c.idem == "run:k", act
        assert template_call({"action": act, "template": "t1", "no_idem": True}, ident, path, idem).idem is None
    assert template_call({"action": "update", "template": "t1", "idem": "k"}, ident, path, idem).method == "PATCH"
    for act in ("preview", "validate"):
        c = template_call({"action": act, "idem": "k"}, ident, path, idem)
        assert c.idem is None and c.method == "POST", act


def test_scenario_template_key_rules():
    from sim.scenario import ScenarioError, parse

    def one(step):
        return parse({"name": "t", "run_id": "r", "steps": [step]})

    with pytest.raises(ScenarioError, match="Idempotency-Key"):
        one({"marking_template": {"action": "approve", "template": "$t.id"}})
    with pytest.raises(ScenarioError, match="只读"):
        one({"marking_template": {"action": "preview", "idem": "x"}})
    with pytest.raises(ScenarioError, match="action"):
        one({"marking_template": {"action": "delete", "idem": "x"}})
    with pytest.raises(ScenarioError, match="template"):
        one({"marking_template": {"action": "update", "idem": "x"}})
    one({"marking_template": {"action": "validate"}})


def test_check_results_items_have_check_type_result_ctx():
    from sim.client import Resp
    from sim.p3 import check_p3_expect

    body = {
        "detail": {
            "code": "check_blocked",
            "ctx": {"check": "marking_inspection", "reason": "not_marked", "marking_id": "m1"},
            "results": [
                {
                    "check_type": "marking_inspection",
                    "result": "blocked",
                    "ctx": {"reason": "not_marked", "marking_id": "m1", "trace_code": None},
                },
                {"check_type": "qtime", "result": "pass", "ctx": {}},
            ],
        }
    }
    r = Resp(409, body)
    want = [
        {"check_type": "marking_inspection", "result": "$nonempty", "ctx": {"marking_id": "m1", "trace_code": None}}
    ]
    assert check_p3_expect(r, {"results": want}) == []
    assert check_p3_expect(r, {"results": [{"check_type": "marking_inspection", "ctx": {"trace_code": "X"}}]})
    assert check_p3_expect(r, {"results": [{"check_type": "marking_inspection", "absent_ctx": ["trace_code"]}]})
    bad = Resp(409, {"detail": {"code": "check_blocked", "results": [{"check_type": "marking_inspection", "ctx": {}}]}})
    assert any("缺" in e for e in check_p3_expect(bad, {"results": []}))
    assert check_p3_expect(Resp(409, {"detail": {"code": "check_blocked"}}), {"results": []})


def test_marking_scenario_d79_supp7():
    sc = load("scenarios/p3-draft/marking-report.yaml")
    assert sc.draft  # B1/B2 未合入
    st = sc.steps
    tpl = [s.args for s in st if s.kind == "marking_template"]
    writes = [a for a in tpl if a["action"] in ("create", "update", "new_version", "approve")]
    assert all(a.get("idem") or a.get("no_idem") for a in writes)
    assert {a["action"] for a in tpl if a.get("no_idem")} == {"create", "update", "new_version", "approve"}
    assert all(not a.get("idem") and not a.get("no_idem") for a in tpl if a["action"] in ("preview", "validate"))
    appr = [
        (a.get("as"), a["expect"]["status"], a["expect"].get("code"))
        for a in tpl
        if a["action"] == "approve" and a.get("idem")
    ]
    assert appr == [
        (None, 422, "self_approval"),
        ("approver", 200, None),
        (None, 422, "self_approval"),
        ("approver", 409, "invalid_transition"),
    ]
    exp = [s.args.get("expect") or {} for s in st]
    assert any(e.get("code") == "idempotency_key_reused" and e.get("detail_object") for e in exp if e)
    cl = [e for e in exp if any((x.get("loc") == ["body", "comment"]) for x in e.get("errors") or [])]
    assert len(cl) == 2 and all(e["errors"][0]["ctx"] == {"reason": "max_length", "max_length": 300} for e in cl)
    blocked = [e for e in exp if e.get("code") == "check_blocked"]
    assert blocked and all(e.get("results") for e in blocked)
    assert any(r["ctx"].get("trace_code", "x") is None for e in blocked for r in e["results"])
    # 作废后重打：缺原因 422 在 409 之前
    mk2 = [
        (s.args.get("expect") or {}).get("code")
        for s in st
        if s.kind == "marking_print" and s.args.get("lot") == "MK0002"
    ]
    i = mk2.index("invalid_transition")
    assert mk2[i - 3 : i - 1] == ["missing", "missing"]


def test_marking_scenario_d79_supp7_note():
    """补充七附注（04:28）：创建 / 新版本 201，编辑 / 审批 200；comment 上限 300；results 用 check_type / result。"""
    from sim.adapters import default_adapters

    AD = default_adapters()

    sc = load("scenarios/p3-draft/marking-report.yaml")
    ok = {}
    for s in sc.steps:
        if s.kind == "marking_template" and (s.args.get("idem")) and s.args["expect"]["status"] < 400:
            ok.setdefault(s.args["action"], set()).add(s.args["expect"]["status"])
    assert ok["create"] == {201} and ok["new_version"] == {201} and ok["update"] == {200} and ok["approve"] == {200}
    for s in sc.steps:
        for r in (s.args.get("expect") or {}).get("results") or []:
            assert "check_type" in r and "result" in r and "check" not in r and "status" not in r
    assert AD["marking_template_item"].candidates == ["/mes/marking-template/{id}"]
    assert AD["marking_template_version"].candidates == ["/mes/marking-template/{id}/versions"]
    assert AD["marking_template_preview"].candidates == ["/mes/marking-template/preview"]
    assert AD["marking_template_validate"].candidates == ["/mes/marking-template/validate"]


def test_template_preview_validate_note2():
    """D79 补充七附注二：预览 / 校验 POST 不带 {id}、不带 key；二选一 422、404、返回字段。"""
    from sim.adapters import default_adapters
    from sim.p3 import template_call

    ad = default_adapters()
    for act in ("preview", "validate"):
        assert "{id}" not in ad[f"marking_template_{act}"].candidates[0]
        c = template_call(
            {"action": act, "template": "t1", "body": {"template_id": "t1"}},
            lambda v: v,
            lambda adapter, **kw: adapter + ":" + kw.get("id", ""),
            lambda a: "k",
        )
        assert c.idem is None and c.path.endswith(":") and c.body == {"template_id": "t1"}
    sc = load("scenarios/p3-draft/marking-report.yaml")
    assert sc.draft
    ro = [s.args for s in sc.steps if s.kind == "marking_template" and s.args["action"] in ("preview", "validate")]
    for act in ("preview", "validate"):
        rows = [a for a in ro if a["action"] == act]
        assert all(not a.get("idem") and not a.get("no_idem") for a in rows)
        both = [a for a in rows if {"template_id", "lines"} <= set(a["body"])]
        none = [a for a in rows if not a["body"]]
        assert [a["expect"] for a in both] == [{"status": 422, "type": "value_error"}]
        assert [a["expect"] for a in none] == [{"status": 422, "type": "value_error"}]
        assert any(a["expect"]["status"] == 404 for a in rows)
        assert all(a["expect"]["status"] in (200, 404, 422) for a in rows)
    prev = [a["expect"]["body"] for a in ro if a["action"] == "preview" and a["expect"]["status"] == 200]
    assert {"template_id", "lines"} <= set(prev[0]) and prev[1]["template_id"] is None
    val = [a["expect"]["body"] for a in ro if a["action"] == "validate" and a["expect"]["status"] == 200]
    assert all({"valid", "unknown_placeholders"} <= set(b) for b in val)
