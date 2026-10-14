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
    assert len(files) == 2
    for f in files:
        sc = load(f)
        assert sc.draft
        c = FakeClient()
        rep = Runner(c).run(sc)
        assert rep["status"] == SKIPPED and rep["reason"].startswith("草稿场景"), rep
        assert c.calls == []  # 草稿不连后端
        assert "reticle_mount" in sc.required_adapters() or "reticle_incident" in sc.required_adapters()


def test_p3_draft_steps_not_runnable_even_if_paths_exist():
    from fake import FakeClient

    from sim.runner import FAILED, Runner
    from sim.scenario import parse

    sc = parse({"run_id": "d", "steps": [{"reticle_incident": {"eq": "EQ1", "reticle": "R1", "kind": "collision"}}]})
    c = FakeClient(paths=None)
    c.paths |= {"/mes/reticle/{reticle_id}/incident"}
    rep = Runner(c).run(sc)
    assert rep["status"] == FAILED and "草稿步骤" in rep["reason"]
