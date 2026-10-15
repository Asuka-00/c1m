import pytest

from sim.safety import UnsafeTarget, allowed_ports, check_target, redact


def test_localhost_only():
    assert check_target("http://127.0.0.1:8013/", {8013}) == "http://127.0.0.1:8013"
    assert check_target("http://localhost:8013", {8013}) == "http://localhost:8013"
    for bad in ("http://10.0.0.5:8013", "http://example.com:8013", "ftp://127.0.0.1:8013"):
        with pytest.raises(UnsafeTarget):
            check_target(bad, {8013})


def test_port_required():
    with pytest.raises(UnsafeTarget, match="端口"):
        check_target("http://127.0.0.1", {80})


@pytest.mark.parametrize("port", [8010, 8011, 8012, 8013, 5174, 5184])
def test_default_whitelist_refuses_everything(monkeypatch, port):
    monkeypatch.delenv("SIM_ALLOWED_PORTS", raising=False)
    with pytest.raises(UnsafeTarget, match="SIM_ALLOWED_PORTS"):
        check_target(f"http://127.0.0.1:{port}")


def test_env_whitelist(monkeypatch):
    monkeypatch.setenv("SIM_ALLOWED_PORTS", "8013, 8014")
    assert allowed_ports() == {8013, 8014}
    assert check_target("http://127.0.0.1:8014")
    with pytest.raises(UnsafeTarget, match="SIM_ALLOWED_PORTS=8013,8014"):
        check_target("http://127.0.0.1:8011")


def test_qa_whitelist_own_port_only(monkeypatch):
    monkeypatch.setenv("SIM_ALLOWED_PORTS", "8012")
    assert check_target("http://127.0.0.1:8012")
    with pytest.raises(UnsafeTarget):
        check_target("http://127.0.0.1:8011")


@pytest.mark.parametrize("raw", ["abc", "0", "70000", "80-90"])
def test_bad_port_values(raw):
    with pytest.raises(UnsafeTarget):
        allowed_ports(raw)


def test_redact():
    assert redact({"password": "x", "a": [{"Token": "y", "b": 1}]}) == {
        "password": "***",
        "a": [{"Token": "***", "b": 1}],
    }
