"""进站检查整体 overridable：任一阻断项不可放行即整体不可放行（全部检查类型）。"""

from app.mes.execution.checks.registry import overall_overridable, result


def _b(check: str, ov: bool) -> dict:
    return result(check, "fail", "x", severity="block", overridable=ov)


def test_overall_overridable() -> None:
    ok = result("spc", "pass", "ok")
    warn = result("recipe", "fail", "w", severity="warn", overridable=False)
    assert overall_overridable([]) is False
    assert overall_overridable([ok, warn]) is False  # 无阻断，无需放行
    assert overall_overridable([ok, _b("qtime", True), warn]) is True
    for check in ("qtime", "operator_qualified", "tool_life", "eqp_wait_qual"):
        mixed = [_b("spc", True), _b(check, False), ok]
        assert overall_overridable(mixed) is False, check
