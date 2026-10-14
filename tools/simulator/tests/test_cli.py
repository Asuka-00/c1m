from pathlib import Path

from sim.cli import main

ROOT = Path(__file__).resolve().parents[1] / "scenarios"


def test_validate_bundled():
    assert main(["validate", *map(str, sorted(ROOT.glob("*.yaml")))]) == 0


def test_run_refuses_remote_and_shared_ports(capsys, monkeypatch):
    monkeypatch.setenv("SIM_TOKEN", "x")
    f = str(ROOT / "e10-state-cycle.yaml")
    assert main(["run", f, "--target", "http://192.168.1.2:8013"]) == 2
    assert main(["run", f, "--target", "http://127.0.0.1:8011"]) == 2
    assert "拒绝" in capsys.readouterr().err
