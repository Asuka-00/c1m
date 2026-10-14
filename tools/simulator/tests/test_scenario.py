from pathlib import Path

import pytest

from sim.scenario import ScenarioError, load, parse

ROOT = Path(__file__).resolve().parents[1] / "scenarios"


@pytest.mark.parametrize("f", sorted(ROOT.glob("*.yaml")), ids=lambda p: p.name)
def test_bundled_scenarios_parse(f):
    sc = load(f)
    assert sc.run_id and sc.steps
    assert sc.target.startswith("http://127.0.0.1:")


def test_required_adapters():
    assert load(ROOT / "alarm-udt-block.yaml").required_adapters() == [
        "crud",
        "crud_item",
        "stage",
        "alarm_set",
        "alarm_get",
        "holds",
        "alarm_list",
        "alarm_clear_alid",
        "e10",
    ]
    assert load(ROOT / "alarm-udt-block.yaml").required_adapters("b11") == [
        "crud",
        "crud_item",
        "stage",
        "eap_events",
        "alarm_get",
        "holds",
        "alarm_list",
    ]
    assert "tool_usage" in load(ROOT / "tool-life-block.yaml").required_adapters()


def test_tool_life_expectation_follows_b10():
    sc = load(ROOT / "tool-life-block.yaml")
    ins = [s.args for s in sc.steps if s.kind == "track_in"]
    assert len(ins) == 4
    assert "expect" not in ins[0]  # 预警区间：Track In 照常 200（B10 只给 warn）
    for x in ins[1:]:  # 到上限 / 过期 / 不可用：硬拦，只在 track_in 判断；517b0a0 规则项也 block
        assert x["expect"] == {
            "status": 409,
            "code": "check_blocked",
            "check": {
                "check_type": "tool_life",
                "overridable": False,
                "result": "block",
                "all": True,
                "min_count": 2,
                "not_message": "tools available",
            },
            "body": {"detail.overridable": False},
        }
    assert all("expect" not in s.args for s in sc.steps if s.kind == "move_in")
    assert "tool_life_exceeded" not in (ROOT / "tool-life-block.yaml").read_text().split("#")[0]


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"run_id": "a:b", "steps": [{"state": {"eq": "E", "to": "PRD"}}]},
        {"run_id": "r", "steps": []},
        {"run_id": "r", "steps": [{"state": {"to": "PRD"}}]},
        {"run_id": "r", "steps": [{"bogus": {}}]},
        {"run_id": "r", "steps": [{"state": {"eq": "E"}, "mount": {"eq": "E"}}]},
    ],
)
def test_invalid(data):
    with pytest.raises(ScenarioError):
        parse(data)


def test_p3_draft_scenarios_parse_and_skip_without_backend():
    import glob

    from fake import FakeClient

    from sim.runner import SKIPPED, Runner
    from sim.scenario import load

    files = sorted(glob.glob("scenarios/p3-draft/*.yaml"))
    assert len(files) == 5
    for f in files:
        sc = load(f)
        assert sc.draft
        c = FakeClient()
        rep = Runner(c).run(sc)
        assert rep["status"] == SKIPPED and rep["reason"].startswith("草稿场景"), rep
        assert c.calls == []  # 草稿不连后端
        need = sc.required_adapters()
        assert {"reticle_mount", "reticle_incident", "alarm_track_in_action", "marking_create", "reticle_scrap"} & set(
            need
        )


def test_p3_steps_execute_when_paths_exist():
    """P3 执行器（eap/p3-sim）：接口在时真正发请求；编码查不到算失败，不再报「草稿步骤」。"""
    from fake import FakeClient

    from sim.runner import FAILED, Runner
    from sim.scenario import parse

    sc = parse(
        {
            "run_id": "d",
            "steps": [{"reticle_incident": {"eq": "EQ1", "reticle": "R1", "kind": "collision", "idem": "k1"}}],
        }
    )
    c = FakeClient(paths=None)
    c.paths |= {"/mes/reticle/{reticle_id}/incident"}
    rep = Runner(c).run(sc)
    assert rep["status"] == FAILED and "找不到 reticle 编码 R1" in rep["reason"]


def test_reticle_replay_requires_saved_step():
    import pytest

    from sim.scenario import ScenarioError, parse

    ok = {
        "run_id": "r",
        "steps": [
            {"reticle_adjust": {"reticle": "R1", "delta": "-5", "reason": "RC", "save_as": "a1", "idem": "k1"}},
            {"reticle_replay": {"of": "a1"}},
        ],
    }
    assert parse(ok).steps[1].kind == "reticle_replay"
    with pytest.raises(ScenarioError):
        parse({"run_id": "r", "steps": [{"reticle_replay": {"of": "nope"}}]})
    with pytest.raises(ScenarioError):
        parse({"run_id": "r", "steps": [{"reticle_replay": {}}]})


def test_b8_draft_reuses_alarm_and_track_in_steps():
    from sim.scenario import load

    sc = load("scenarios/p3-draft/alarm-track-in-action.yaml")
    kinds = [s.kind for s in sc.steps]
    for k in ("seed_alarm_code", "alarm_set", "alarm_clear", "track_in", "expect_hold", "set_track_in_action"):
        assert k in kinds
    tis = [s for s in sc.steps if s.kind == "track_in"]
    # 每次进站前后都断言批次没有 Hold
    for t in tis:
        i = sc.steps.index(t)
        assert sc.steps[i + 1].kind == "expect_hold" and sc.steps[i + 1].args["present"] is False
    sets = [s.args for s in sc.steps if s.kind == "set_track_in_action"]
    assert {"off", "warn", "block"} <= {a.get("value") for a in sets}
    # D70 补充：非法值 422 enum + ctx.expected；eap_service 403；类型层 null 422、覆盖层 null 清空
    assert any(
        a["expect"].get("code") == "enum" and a["expect"]["ctx"]["expected"] == ["off", "warn", "block"] for a in sets
    )
    assert any(a.get("as") == "svc" and a["expect"]["status"] == 403 for a in sets)
    assert any(a.get("level") == "type" and a.get("value") is None and a["expect"]["status"] == 422 for a in sets)
    assert any(a.get("level") == "equipment" and a.get("value") is None and a["expect"]["status"] == 200 for a in sets)
    assert "expect_effective_track_in_action" in kinds
    # B8 补充：ctx.alarms[] 带 sub_unit_id；多腔体整机拦截后清除放行；已清除不再拦；覆盖层 null 继承类型层
    assert sc.run_id == "alarm-tia-04"
    blocks = [s.args["expect"] for s in tis if s.args["expect"].get("status") == 409 and "body" in s.args["expect"]]
    assert all(
        v.get("sub_unit_id", "missing") != "missing" for b in blocks for k, v in b["body"].items() if ".alarms." in k
    )
    mc = [s for s in tis if s.args["eq"] == "EAP-MC01"]
    assert [t.args["expect"]["status"] for t in mc] == [409, 200]
    assert any(s.kind == "alarm_set" and s.args.get("sub_unit_id") == "EAP-MC01-CH1" for s in sc.steps)
    assert any(s.kind == "expect_alarm" and s.args.get("alarm_status") == "cleared" for s in sc.steps)
    assert any(
        s.kind == "expect_effective_track_in_action"
        and s.args == {"eq": "EAP-DA01", "alid": "2105", "value": "block", "source": "equipment_type"}
        for s in sc.steps
    )


def test_b8_draft_asserts_effective_source_and_uses_sub_unit_id():
    import pathlib

    from sim.scenario import load

    text = pathlib.Path("scenarios/p3-draft/alarm-track-in-action.yaml").read_text()
    assert "source_level" not in text and "effective_track_in_action_source" in text
    sc = load("scenarios/p3-draft/alarm-track-in-action.yaml")
    eff = [s.args for s in sc.steps if s.kind == "expect_effective_track_in_action"]
    # D70 补充：覆盖层有值 → equipment；覆盖层 null 继承 → equipment_type；两种都覆盖
    assert {"equipment", "equipment_type"} <= {a.get("source") for a in eff}
    assert all(a.get("source") in (None, "equipment", "equipment_type") for a in eff)
    i = [
        n
        for n, s in enumerate(sc.steps)
        if s.kind == "set_track_in_action" and s.args.get("value") is None and s.args.get("level") == "equipment"
    ][0]
    nxt = next(s for s in sc.steps[i + 1 :] if s.kind == "expect_effective_track_in_action")
    assert nxt.args["source"] == "equipment_type"
    assert "sub_unit:" not in text and "sub_unit_id: EAP-MC01-CH1" in text


def test_b8_draft_type_row_rules():
    from sim.scenario import load

    sc = load("scenarios/p3-draft/alarm-track-in-action.yaml")
    st = sc.steps
    seeds = [(n, s.args) for n, s in enumerate(st) if s.kind == "seed_alarm_code"]
    # 每个成功建的单台行之前，都已有同 (设备, ALID) 的类型行
    for n, a in seeds:
        if a.get("level") != "type" and "expect" not in a:
            assert any(
                m < n and b.get("level") == "type" and b["alid"] == a["alid"] and b["eq"] == a["eq"] for m, b in seeds
            ), a
    # 2104：类型行 off，单台行 null → 生效 off、来源 equipment_type
    assert any(
        s.kind == "expect_effective_track_in_action"
        and s.args == {"eq": "EAP-DA01", "alid": "2104", "value": "off", "source": "equipment_type"}
        for s in st
    )
    reasons = {
        a["expect"]["ctx"]["reason"]
        for _, a in seeds
        if a.get("expect", {}).get("status") == 422 and "ctx" in a["expect"]
    }
    assert reasons == {"type_row_missing", "equipment_type_missing"}
    assert all(
        a["expect"]["code"] == "value_error"
        for _, a in seeds
        if a.get("expect", {}).get("status") == 422 and "ctx" in a["expect"]
    )
    nt = [a for _, a in seeds if a["eq"] == "EAP-NT01"]
    assert nt and nt[0]["expect"]["ctx"]["reason"] == "equipment_type_missing"
    assert {"code": "EAP-NT01"} in [dict(e) for e in sc.equipment] or any(
        (e.get("code") if isinstance(e, dict) else getattr(e, "code", None)) == "EAP-NT01" for e in sc.equipment
    )
    dels = [s.args for s in st if s.kind == "delete_alarm_code"]
    assert dels == [
        {"eq": "EAP-DA01", "alid": "2101", "level": "type", "expect": {"status": 409, "code": "referenced"}}
    ]


def test_marking_draft_follows_d78():
    import pytest

    from sim.runner import P3_DRAFT_STEPS
    from sim.scenario import ScenarioError, load, parse

    sc = load("scenarios/p3-draft/marking-report.yaml")
    assert sc.draft and "P3-B2" in sc.draft and "/void" in sc.draft
    assert {s.kind for s in sc.steps if "marking" in s.kind or s.kind == "lot_scrap"} <= P3_DRAFT_STEPS
    exp = [s.args.get("expect") or {} for s in sc.steps]
    codes = [e.get("code") for e in exp]
    assert (
        codes.count("invalid_transition") == 7
    )  # 作废后上报改为 no_active_marking（D79 补充 2） and "trace_code_mismatch" in codes
    assert codes.count("check_blocked") == 7 and "idempotency_key_reused" in codes
    assert (
        sum(1 for e in exp if e.get("loc") == ["header", "Idempotency-Key"]) == 4
    )  # 打印、检验、作废，D81 不存在主记录作废
    # 补充三 4：逐条列出，值取 config；手工和 EAP 两个入口各有单条和双条
    errs = [e["errors"] for e in exp if "errors" in e and e["errors"][0]["loc"][-1] == "trace_code"]
    assert len(errs) == 15 and sum(1 for x in errs if len(x) == 2) == 2
    miss = [x for x in errs if x[0]["type"] == "missing"]
    assert len(miss) == 3 and all(len(x) == 1 for x in miss)  # 空串 / 纯空白只一条
    for x in errs:
        for it in x:
            if it["type"] == "missing":
                continue
            want = {"max_length": "$cfg.trace_code_max_length", "pattern": "$cfg.trace_code_pattern"}[
                it["ctx"]["reason"]
            ]
            assert it["type"] == "value_error" and it["ctx"][it["ctx"]["reason"]] == want
    assert next(s for s in sc.steps if s.kind == "marking_config").args["save_as"] == "cfg"
    bad = next(s for s in sc.steps if s.args.get("save_as") == "bad8")
    nxt = sc.steps[sc.steps.index(bad) + 1]
    assert nxt.kind == "expect_marking_events" and nxt.args["audit_count"] == {"trace_code_mismatch": 1}
    voids = [s for s in sc.steps if s.kind == "marking_void" and s.args.get("marking") != "MK-NOT-EXIST"]
    assert [v.args["expect"]["status"] for v in voids] == [422, 403, 422, 422, 422, 200, 409]
    assert voids[0].args["no_idem"] and voids[0].args["expect"]["loc"] == ["header", "Idempotency-Key"]
    evs = [(s.args.get("latest") or {}).get("event") for s in sc.steps if s.kind == "expect_marking_events"]
    assert {"lot.marked", "lot.marking_inspected", "lot.marking_voided", "lot.marking_mismatched"} <= set(evs)
    assert not any("qty" in (s.args.get("payload") or {}) for s in sc.steps)
    seqs = [s.args["seqs"] for s in sc.steps if s.kind == "expect_marking_prints" and "seqs" in s.args]
    assert all(q == list(range(1, len(q) + 1)) for q in seqs) and [1, 2] in seqs
    # 出站：pending / fail / 重打后 pending → 409，pass → 200
    outs = [s.args["expect"]["status"] for s in sc.steps if s.kind == "track_out" and s.args["lot"] == "MK0001"]
    assert outs == [409, 409, 409, 409, 200]  # pending / fail / 重打后 pending / 复检 fail / pass
    lis = [
        s.args["fields"]["latest_inspection_status"]
        for s in sc.steps
        if s.kind == "expect_marking" and "latest_inspection_status" in s.args.get("fields", {})
    ]
    # 第 3 个是 pass 被强制成 fail（D79-4），第 4 个是出站前复检 pass；最后一个是作废旧主记录保留
    assert lis == ["fail", "pass", "fail", "pass", "fail", "fail"]
    # 手工重放不带 duplicate；EAP 重发 duplicate=true
    for s in sc.steps:
        if s.kind == "marking_replay":
            of = next(x for x in sc.steps if x.args.get("save_as") == s.args["of"])
            if of.kind == "marking_report":
                assert s.args["expect"]["body"]["duplicate"] is True
            else:
                assert "duplicate" in s.args["expect"]["absent"]
    text = open("scenarios/p3-draft/marking-report.yaml").read()
    assert "lot.marking_mismatched" in text and "label_marking_mismatch" not in text and "待核对" not in text
    with pytest.raises(ScenarioError):
        parse({"run_id": "m", "steps": [{"marking_inspect": {"result": "pass"}}]})  # 缺 lot
    with pytest.raises(ScenarioError):
        parse({"run_id": "m", "steps": [{"marking_replay": {"of": "nope"}}]})


def test_marking_draft_supplement4_trace_code_cases_match_precheck():
    from sim.marking import check_trace_code
    from sim.scenario import load

    sc = load("scenarios/p3-draft/marking-report.yaml")
    cfg = {"trace_code_max_length": 32, "trace_code_pattern": "^[A-Z0-9-]+$"}
    n = 0
    for s in sc.steps:
        if s.kind == "marking_print" and "trace_code" in s.args:
            want = [(it["type"], (it.get("ctx") or {}).get("reason")) for it in s.args["expect"]["errors"]]
            got = [
                (it["type"], (it.get("ctx") or {}).get("reason")) for it in check_trace_code(s.args["trace_code"], cfg)
            ]
            assert got == want, s.args["trace_code"]
            n += 1
    assert n == 12
    seq1 = next(
        s
        for s in sc.steps
        if s.kind == "expect_marking_events" and (s.args.get("latest") or {}).get("payload.seq") == 1
    )
    assert "payload.reason_id" in seq1.args["latest"] and seq1.args["latest"]["payload.reason_id"] is None


def test_marking_draft_follows_d79():
    from sim.scenario import load

    sc = load("scenarios/p3-draft/marking-report.yaml")
    kinds = [s.kind for s in sc.steps]
    assert "marking_manual" not in kinds and "marking_reprint" not in kinds
    # 每个批次先建主记录再打印
    for lot in ("MK0001", "MK0002", "MK0003"):
        idx = [i for i, s in enumerate(sc.steps) if s.args.get("lot") == lot]
        first = next(i for i in idx if sc.steps[i].kind in ("marking_create", "marking_print", "marking_report"))
        assert sc.steps[first].kind == "marking_create", lot
    exp = [s.args.get("expect") or {} for s in sc.steps]
    assert sum(1 for e in exp if e.get("code") == "already_marked") == 2
    ov = next(s for s in sc.steps if s.args.get("idem") == "mk-insp-ov")
    assert ov.args["result"] == "pass" and ov.args["expect"]["status"] == 200
    assert (
        ov.args["expect"]["body"]["data.result"] == "fail"
        and ov.args["expect"]["body"]["data.result_overridden"] is True
    )
    tr = [s.args for s in sc.steps if s.kind == "expect_marking_trace"]
    assert [t.get("include_voided", False) for t in tr] == [False, True, False]
    assert set(tr[1]["first"]) == {"marking_id", "lot_id", "trace_code", "voided", "prints"}
    assert set(tr[1]["first"]["prints"][0]) == {"print_id", "seq", "marked_at", "latest_inspection_result"}
    ls = [s.args for s in sc.steps if s.kind == "expect_marking_list"]
    assert {"marked_at_from", "marked_at_to"} <= {k for a in ls for k in a} and [a["count"] for a in ls] == [1, 0, 0, 1]
    ro = next(s for s in sc.steps if s.args.get("as") == "read_only")
    assert ro.kind == "marking_print" and ro.args["expect"]["status"] == 403
    assert "qty" not in open("scenarios/p3-draft/marking-report.yaml").read()


def test_marking_draft_follows_d79_supplement():
    from sim.marking import check_trace_code
    from sim.scenario import load

    sc = load("scenarios/p3-draft/marking-report.yaml")
    st = sc.steps
    # a. no_active_marking：无主记录 / 只有已作废主记录，各一次，且不写打印
    nam = [i for i, s in enumerate(st) if (s.args.get("expect") or {}).get("code") == "no_active_marking"]
    assert [st[i].args["lot"] for i in nam] == ["MK0004", "MK0002"]
    assert all(st[i].kind == "marking_report" for i in nam)
    assert st[nam[0] + 1].kind == "expect_marking_prints" and st[nam[0] + 1].args["count"] == 0
    void_i = next(i for i, s in enumerate(st) if s.args.get("save_as") == "void1")
    recreate_i = next(i for i, s in enumerate(st) if s.args.get("save_as") == "c2b")
    assert void_i < nam[1] < recreate_i
    # b. 出站
    outs = [
        (s.args["lot"], s.args["expect"]["status"], (s.args["expect"].get("ctx") or {}).get("reason"))
        for s in st
        if s.kind == "track_out"
    ]
    assert ("MK0009", 200, None) in outs and ("MK0004", 409, "not_marked") in outs
    assert {r for _, c, r in outs if c == 409} == {"not_marked", "pending", "fail"}
    for s in st:
        if s.kind == "track_out" and s.args["expect"]["status"] == 409:
            ctx = s.args["expect"]["ctx"]
            assert ctx["check"] == "marking_inspection" and s.args["expect"]["overridable"] is False
            if ctx["reason"] == "not_marked":
                assert "marking_id" not in ctx and s.args["expect"]["absent_ctx"] == ["marking_id"]
            else:
                assert "marking_id" in ctx
    mk2 = [o for o in outs if o[0] == "MK0002"]
    assert mk2 == [("MK0002", 409, "not_marked"), ("MK0002", 409, "pending"), ("MK0002", 200, None)]
    tpl = [s.args for s in st if s.kind == "marking_template_ready"]
    assert [t["approved"] for t in tpl] == [True, False] and "MK0009" in tpl[1]["lots"]
    # E4：None → missing，非字符串 → string_type
    cfg = {"trace_code_max_length": 32, "trace_code_pattern": "^[A-Z0-9-]+$"}
    assert check_trace_code(None, cfg) == [{"type": "missing"}]
    assert check_trace_code(123, cfg) == [{"type": "string_type"}]


def test_marking_draft_follows_d79_supplement2():
    from sim.marking import check_read_code
    from sim.scenario import load

    st = load("scenarios/p3-draft/marking-report.yaml").steps
    mk1 = [(i, s) for i, s in enumerate(st) if s.args.get("lot") == "MK0001"]
    out_ok = next(i for i, s in mk1 if s.kind == "track_out" and s.args["expect"]["status"] == 200)
    insp = [(i, s) for i, s in mk1 if s.kind == "marking_inspect" and s.args.get("idem", "").startswith("mk-insp")]
    # 复检都在出站前；出站后只有一次，且 409
    after = [s for i, s in insp if i > out_ok]
    assert len(after) == 1 and after[0].args["expect"] == {"status": 409, "code": "invalid_transition"}
    ov = next(s for i, s in insp if s.args["idem"] == "mk-insp-ov")
    ok = next(s for i, s in insp if s.args["idem"] == "mk-insp-ok")
    assert st.index(ov) < st.index(ok) < out_ok
    # 以最新为准：复检 fail 后出站 409 reason=fail，再 pass 后放行
    between = [s for s in st[st.index(ov) : st.index(ok)] if s.kind == "track_out"]
    assert len(between) == 1 and between[0].args["expect"]["ctx"]["reason"] == "fail"
    # read_code：不校验格式、空 missing、>128 码点 max_length，与预校验一致
    for s in st:
        if s.kind == "marking_inspect" and "read_code" in s.args and not str(s.args["read_code"]).startswith("$"):
            e = s.args["expect"]
            if e["status"] == 409 or s.args["idem"].startswith("mk-ord"):  # 状态 / 顺序用例，read_code 只是占位
                continue
            got = check_read_code(s.args["read_code"])
            if e["status"] == 200:
                assert got == [] and e["body"]["data.result"] == "fail"
            else:
                assert [x["type"] for x in got] == [x["type"] for x in e["errors"]]
    # emoji：31 个 A + 1 个 emoji 只报 pattern
    emo = next(s for s in st if s.args.get("idem") == "mk-tc-12")
    assert len(emo.args["trace_code"]) == 32 and [x["ctx"]["reason"] for x in emo.args["expect"]["errors"]] == [
        "pattern"
    ]
    # 未检验就重打：MK0003 首打后、无检验，带原因 → 200 seq=2
    rep = next(s for s in st if s.args.get("idem") == "mk-rep-3b")
    i = st.index(rep)
    assert not any(s.kind == "marking_inspect" and s.args.get("lot") == "MK0003" for s in st[:i])
    assert rep.args["reason"] and rep.args["comment"] and rep.args["expect"]["body"]["data.seq"] == 2
    text = open("scenarios/p3-draft/marking-report.yaml").read()
    assert "待定" not in text and "PEND-MK" not in text


def test_marking_draft_e7_marked_at_is_first_print():
    from sim.scenario import load

    st = load("scenarios/p3-draft/marking-report.yaml").steps
    rep = next(i for i, s in enumerate(st) if s.args.get("idem") == "mk-rep-3b")
    em = st[rep + 1]
    assert em.kind == "expect_marking" and em.args["fields"] == {
        "marked_at": "$print_seq_1.printed_at",
        "last_printed_at": "$print_seq_2.printed_at",
    }
    after = [s.args for s in st[rep + 1 : rep + 4] if s.kind == "expect_marking_list"]
    assert after == [
        {"lot": "MK0003", "marked_at_from": "$print_seq_2.printed_at", "count": 0},
        {"lot": "MK0003", "marked_at_to": "$print_seq_2.printed_at", "count": 1},
    ]


def test_reticle_report_draft_e2():
    import pytest

    from sim.runner import P3_DRAFT_STEPS
    from sim.scenario import ScenarioError, load, parse

    sc = load("scenarios/p3-draft/reticle-report.yaml")
    assert sc.draft and "D80" in sc.draft and "reticle_report" in P3_DRAFT_STEPS
    st = sc.steps
    rep = [s for s in st if s.kind == "reticle_report"]
    assert {s.args["kind"] for s in rep} == {"mount", "unmount", "usage"}
    exp = [s.args.get("expect") or {} for s in st]
    codes = [e.get("code") for e in exp]
    assert codes.count("idempotency_key_reused") == 4 and codes.count("invalid_transition") == 2
    assert any((e.get("ctx") or {}).get("max_places") == 6 for e in exp)
    # EAP 重放 duplicate=true；手工重放无 duplicate
    for s in st:
        if s.kind == "reticle_replay":
            of = next(x for x in st if x.args.get("save_as") == s.args["of"])
            if of.kind == "reticle_report":
                assert s.args["expect"]["body"]["duplicate"] is True
            else:
                assert "duplicate" in s.args["expect"]["absent"]
    # D80 G1：下机单独一行事件，上机行不写下机事件号
    hist = [s for s in st if s.kind == "expect_reticle_history"]
    assert not any("unmount_source" in s.args.get("fields", {}) for s in hist)
    assert not any("unmount_external_event_id" in s.args.get("fields", {}) for s in hist)
    assert any(
        s.args.get("latest_of") == "unmount" and s.args["fields"].get("external_event_id") == "$ext.um1" for s in hist
    )
    assert sum(1 for s in hist if s.args.get("count_of", {}).get("unmount") == 1) >= 3
    assert any(s.args.get("fields", {}).get("unmounted_at") == "$mrow1.unmounted_at" for s in hist)
    dup = [s for s in st if s.kind == "reticle_report" and s.args["kind"] == "unmount"]
    assert [d.args["expect"]["body"]["duplicate"] for d in dup] == [False, True]
    # D80 补充一：10 个接口缺 key 422 missing
    from sim.scenario import RETICLE_IDEM_STEPS

    miss = {s.kind for s in st if s.args.get("no_idem")}
    assert miss == RETICLE_IDEM_STEPS and len(miss) == 14
    for s in st:
        if s.args.get("no_idem"):
            assert s.args["expect"]["loc"] == ["header", "Idempotency-Key"]
    assert sum(1 for s in st if s.args.get("expect", {}).get("code") == "idempotency_key_reused") == 4
    with pytest.raises(ScenarioError):
        parse({"run_id": "r", "steps": [{"reticle_report": {"eq": "E", "reticle": "R", "kind": "inspect"}}]})


def test_reticle_write_requires_idem():
    from sim.scenario import ScenarioError, parse

    base = {"name": "x", "run_id": "x1", "draft": "d", "steps": [{"reticle_hold": {"reticle": "R", "reason": "x"}}]}
    with pytest.raises(ScenarioError, match="idem"):
        parse(base)
    base["steps"] = [{"reticle_hold": {"reticle": "R", "reason": "x", "no_idem": True}}]
    parse(base)
    base["steps"] = [{"reticle_hold": {"reticle": "R", "reason": "x", "idem": "k"}}]
    parse(base)


def test_marking_draft_d79_s4_s5():
    from sim.marking import check_pattern_config
    from sim.scenario import load

    sc = load("scenarios/p3-draft/marking-report.yaml")
    bad = [s for s in sc.steps if s.kind == "marking_config" and "set" in s.args]
    assert len(bad) == 11  # 含 D81 补记 ^[-]+$
    for s in bad:
        assert check_pattern_config(s.args["set"]["trace_code_pattern"]), s.args["set"]
        assert s.args["expect"]["errors"][0]["ctx"] == {"reason": "pattern_unsupported"}
    ctxs = [e["ctx"] for s in sc.steps for e in (s.args.get("expect") or {}).get("errors", []) if "ctx" in e]
    for c in ctxs:
        if c["reason"] == "max_length":
            assert c["max_length"] in ("$cfg.trace_code_max_length", 128)
        if c["reason"] == "pattern":
            assert c["pattern"] == "$cfg.trace_code_pattern"


def test_d80_s2_flow_idem_and_reused_object():
    from sim.client import Resp
    from sim.runner import check_expect
    from sim.scenario import RETICLE_IDEM_STEPS, load

    flow = {"reticle_clean_start", "reticle_clean_complete", "reticle_repair_complete", "reticle_inspect_start"}
    assert flow <= RETICLE_IDEM_STEPS and len(RETICLE_IDEM_STEPS) == 14
    st = load("scenarios/p3-draft/reticle-report.yaml").steps
    cc = next(s for s in st if s.kind == "reticle_clean_complete" and s.args.get("save_as") == "cc6")
    rp = next(s for s in st if s.kind == "reticle_replay" and s.args["of"] == "cc6")
    assert cc.args["idem"] and rp.args["expect"]["status"] == 200
    for f in ("reticle-report", "reticle-exposure-count", "reticle-collision-hold", "marking-report"):
        for s in load(f"scenarios/p3-draft/{f}.yaml").steps:
            e = s.args.get("expect") or {}
            if e.get("code") == "idempotency_key_reused":
                assert e["status"] == 422 and e.get("detail_object") is True, (f, s.kind)
    obj = Resp(422, {"detail": {"code": "idempotency_key_reused", "message": "x"}})
    arr = Resp(422, {"detail": [{"type": "value_error", "code": "idempotency_key_reused", "msg": "x"}]})
    want = {"status": 422, "code": "idempotency_key_reused", "detail_object": True}
    assert check_expect(obj, want) == [] and check_expect(arr, want)


def test_marking_draft_read_code_n_e4():
    from sim.marking import check_read_code
    from sim.scenario import load

    st = [s for s in load("scenarios/p3-draft/marking-report.yaml").steps if s.kind == "marking_inspect"]
    rc = {repr(s.args["read_code"]): s.args["expect"] for s in st if "read_code" in s.args}
    for v, typ in ((" \t\u3000\r\n", "missing"), (None, "missing"), (12345, "string_type"), (["ABC"], "string_type")):
        e = rc[repr(v)]
        assert e["status"] == 422 and e["errors"] == [{"type": typ, "loc": ["body", "read_code"]}], v
        assert check_read_code(v) == [{"type": typ}], v
    fe = rc[repr("\ufeff")]
    assert check_read_code("\ufeff") == []
    assert fe["status"] == 200 and fe["body"]["data.result"] == "fail" and fe["body"]["data.result_overridden"] is True
    txt = open("scenarios/p3-draft/reticle-report.yaml").read()
    assert "N-E6" in txt and "D81 已定" in txt


def test_d81_order_and_read_code_absent():
    from sim.marking import check_inspect_body, check_pattern_config, check_read_code
    from sim.scenario import load

    assert check_read_code() == [{"type": "missing"}] and check_inspect_body({"result": "pass"}) == [
        {"type": "missing"}
    ]
    assert check_inspect_body({"read_code": "A"}) == []
    assert check_pattern_config("^[-]+$")
    st = load("scenarios/p3-draft/marking-report.yaml").steps
    ins = [s for s in st if s.kind == "marking_inspect"]
    for s in ins:  # 不带 read_code 的检验只能是 422 用例（缺 key 或缺字段）
        if "read_code" not in s.args:
            assert s.args["expect"]["status"] == 422 and "read_code" in s.args.get("omit", []), s.args
    absent = [s for s in ins if "read_code" in s.args.get("omit", []) and not s.args.get("no_idem")]
    assert all(s.args["expect"]["errors"] == [{"type": "missing", "loc": ["body", "read_code"]}] for s in absent)
    assert len(absent) >= 2
    cfg = [s.args["set"]["trace_code_pattern"] for s in st if s.kind == "marking_config" and "set" in s.args]
    assert "^[-]+$" in cfg
    mv = [s for s in st if s.kind == "marking_void" and s.args.get("marking") == "MK-NOT-EXIST"]
    assert [s.args["expect"]["status"] for s in mv] == [422, 404]
    rt = load("scenarios/p3-draft/reticle-report.yaml").steps
    nx = [s for s in rt if s.args.get("reticle") == "R-NOT-EXIST" and s.kind == "reticle_hold"]
    assert [s.args["expect"]["status"] for s in nx] == [422, 404]
    od = [s.args["expect"]["status"] for s in rt if str(s.args.get("idem", "")).startswith("ret-rep-ord")]
    assert od == [404, 422, 409]
    txt = open("scenarios/p3-draft/reticle-report.yaml").read()
    assert "待后端确认" not in txt and "等后端定顺序" not in txt
