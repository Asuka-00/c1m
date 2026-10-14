from pathlib import Path

import sim.cli as cli
from sim.cli import main

ROOT = Path(__file__).resolve().parents[1] / "scenarios"
E10 = str(ROOT / "e10-state-cycle.yaml")


def test_validate_bundled(monkeypatch):
    monkeypatch.delenv("SIM_TARGET", raising=False)
    assert main(["validate", *map(str, sorted(ROOT.glob("*.yaml")))]) == 0


def test_validate_checks_target_override(monkeypatch, capsys):
    monkeypatch.setenv("SIM_ALLOWED_PORTS", "8012")
    assert main(["validate", E10, "--target", "http://127.0.0.1:8012"]) == 0
    assert "target=http://127.0.0.1:8012" in capsys.readouterr().out
    assert main(["validate", E10, "--target", "http://127.0.0.1:8013"]) == 2


def test_validate_b11_mode_needs(capsys):
    assert main(["validate", str(ROOT / "alarm-udt-block.yaml"), "--mode", "b11"]) == 0
    out = capsys.readouterr().out
    assert "eap_events" in out and "alarm_set" not in out.split("needs=")[1]


def test_run_refuses_remote_and_unlisted_ports(capsys, monkeypatch):
    monkeypatch.setenv("SIM_TOKEN", "x")
    monkeypatch.delenv("SIM_TARGET", raising=False)
    monkeypatch.setenv("SIM_ALLOWED_PORTS", "8013")
    assert main(["run", E10, "--target", "http://192.168.1.2:8013"]) == 2
    assert main(["run", E10, "--target", "http://127.0.0.1:8011"]) == 2
    err = capsys.readouterr().err
    assert "拒绝" in err and "SIM_ALLOWED_PORTS" in err
    monkeypatch.delenv("SIM_ALLOWED_PORTS")
    assert main(["run", E10]) == 2  # 场景默认 8013，白名单为空也拒绝


def test_target_precedence(monkeypatch):
    monkeypatch.setenv("SIM_TARGET", "http://127.0.0.1:8014")
    assert cli.resolve_target(None, "http://127.0.0.1:8013") == "http://127.0.0.1:8014"
    assert cli.resolve_target("http://127.0.0.1:8012", "x") == "http://127.0.0.1:8012"
    monkeypatch.delenv("SIM_TARGET")
    assert cli.resolve_target(None, "http://127.0.0.1:8013") == "http://127.0.0.1:8013"


def test_run_uses_env_target(monkeypatch, capsys):
    seen = {}

    class Dummy:
        def __init__(self, client, mode):
            seen["mode"] = mode

        def run(self, sc):
            return {"status": "passed", "reason": None, "steps": []}

    monkeypatch.setattr(cli, "_client", lambda t: seen.setdefault("target", t))
    monkeypatch.setattr(cli, "Runner", Dummy)
    monkeypatch.setenv("SIM_TARGET", "http://127.0.0.1:8014")
    monkeypatch.setenv("SIM_ALLOWED_PORTS", "8014")
    assert main(["run", E10]) == 0
    assert seen == {"target": "http://127.0.0.1:8014", "mode": "manual"}
