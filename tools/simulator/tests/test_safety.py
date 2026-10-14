import pytest

from sim.safety import UnsafeTarget, check_target, redact


def test_localhost_only():
    assert check_target("http://127.0.0.1:8013/") == "http://127.0.0.1:8013"
    for bad in ("http://10.0.0.5:8013", "http://localhost:8013", "http://example.com"):
        with pytest.raises(UnsafeTarget):
            check_target(bad)
    assert check_target("http://10.0.0.5:8013", allow_remote=True)


@pytest.mark.parametrize("port", [8010, 8011, 8012, 5174, 5184])
def test_forbidden_ports(port):
    with pytest.raises(UnsafeTarget):
        check_target(f"http://127.0.0.1:{port}")


def test_redact():
    assert redact({"password": "x", "a": [{"Token": "y", "b": 1}]}) == {
        "password": "***",
        "a": [{"Token": "***", "b": 1}],
    }
