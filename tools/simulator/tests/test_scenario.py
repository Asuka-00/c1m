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
    assert len(files) == 3
    for f in files:
        sc = load(f)
        assert sc.draft
        c = FakeClient()
        rep = Runner(c).run(sc)
        assert rep["status"] == SKIPPED and rep["reason"].startswith("草稿场景"), rep
        assert c.calls == []  # 草稿不连后端
        need = sc.required_adapters()
        assert "reticle_mount" in need or "reticle_incident" in need or "alarm_track_in_action" in need


def test_p3_draft_steps_not_runnable_even_if_paths_exist():
    from fake import FakeClient

    from sim.runner import FAILED, Runner
    from sim.scenario import parse

    sc = parse({"run_id": "d", "steps": [{"reticle_incident": {"eq": "EQ1", "reticle": "R1", "kind": "collision"}}]})
    c = FakeClient(paths=None)
    c.paths |= {"/mes/reticle/{reticle_id}/incident"}
    rep = Runner(c).run(sc)
    assert rep["status"] == FAILED and "草稿步骤" in rep["reason"]


def test_reticle_replay_requires_saved_step():
    import pytest

    from sim.scenario import ScenarioError, parse

    ok = {
        "run_id": "r",
        "steps": [
            {"reticle_adjust": {"reticle": "R1", "delta": "-5", "reason": "RC", "save_as": "a1"}},
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
    assert sc.run_id == "alarm-tia-03"
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
