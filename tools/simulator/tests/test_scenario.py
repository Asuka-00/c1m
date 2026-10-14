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
        "stage",
        "alarm_set",
        "alarm_get",
        "holds",
        "e10",
        "alarm_clear_alid",
    ]
    assert load(ROOT / "alarm-udt-block.yaml").required_adapters("b11") == ["stage", "eap_events", "alarm_get", "holds"]
    assert "tool_usage" in load(ROOT / "tool-life-block.yaml").required_adapters()


def test_tool_life_expectation_follows_b10():
    sc = load(ROOT / "tool-life-block.yaml")
    ins = [s.args for s in sc.steps if s.kind == "track_in"]
    assert len(ins) == 2
    assert "expect" not in ins[0]  # 预警区间：Track In 照常 200（B10 只给 warn）
    assert ins[1]["expect"] == {  # >= 上限硬拦，只在 track_in 判断
        "status": 409,
        "code": "check_blocked",
        "check": {"check_type": "tool_life", "overridable": False, "result": "block"},
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
