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


def test_rule_tool_life_not_overridable(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """P2-D3：规则产生的 tool_life 阻断与内置硬拦截一致，overridable=false。"""
    from app.mes.execution.checks import registry as reg

    def rule(ct: str) -> dict:
        return {
            "id": "1",
            "code": ct,
            "name": ct,
            "check_type": ct,
            "severity": "block",
        }

    plan = {"id": "2", "code": "P"}
    monkeypatch.setattr(
        reg, "resolve", lambda ctx: [(plan, rule("tool_life")), (plan, rule("spc"))]
    )
    monkeypatch.setitem(reg.CHECKS, "tool_life", lambda ctx, p: ("fail", "used up", {}))
    monkeypatch.setitem(reg.CHECKS, "spc", lambda ctx, p: ("fail", "ooc", {}))
    out = {r["check_type"]: r for r in reg.run(None)}  # type: ignore[arg-type]
    assert out["tool_life"]["overridable"] is False
    assert out["spc"]["overridable"] is True
    assert overall_overridable(list(out.values())) is False
