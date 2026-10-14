from sim.marking import check_trace_code, pattern_allowed

CFG = {"trace_code_max_length": 32, "trace_code_pattern": "^[A-Z0-9-]+$"}


def reasons(v):
    return [x.get("ctx", {}).get("reason", x["type"]) for x in check_trace_code(v, CFG)]


def test_ok_and_boundary():
    assert reasons("AB-12") == [] and reasons("A" * 32) == []
    assert reasons("A" * 33) == ["max_length"]


def test_missing_only_once():
    assert reasons("") == ["missing"] and reasons("   ") == ["missing"] and reasons("\t\n") == ["missing"]
    assert reasons(None) == ["missing"]


def test_no_normalization_full_match():
    assert reasons("ab12") == ["pattern"]  # 小写不转大写
    assert reasons(" AB12") == ["pattern"] and reasons("AB12 ") == ["pattern"]  # 首尾空格不去
    assert reasons("AB12\n") == ["pattern"]  # fullmatch：$ 不放过结尾换行
    both = check_trace_code("a" * 33, CFG)
    assert [x["ctx"] for x in both] == [
        {"reason": "max_length", "max_length": 32},
        {"reason": "pattern", "pattern": "^[A-Z0-9-]+$"},
    ]


def test_pattern_syntax_rule():
    assert pattern_allowed("^[A-Z0-9-]+$") and pattern_allowed("^[A-Z][A-Z0-9-]+$")
    for bad in ("[A-Z]+", "^[A-Z]+", "^\\d+$", "^\\w+$", "(?i)^[A-Z]+$", "^[A-Z]{4}$", "^.+$", "^[\\d]+$"):
        assert not pattern_allowed(bad), bad


def test_supplement5_cases():
    cases = {
        "AB12\n": ["pattern"],
        "\nAB12": ["pattern"],
        "AB 12": ["pattern"],
        "ＡＢＣ": ["pattern"],
        "A" * 32: [],
        "A" * 33: ["max_length"],
        "A" * 32 + "a": ["max_length", "pattern"],
        "-": [],
        "\n": ["missing"],
        "\u3000": ["missing"],
        " \t": ["missing"],
        "\r\n \u3000": ["missing"],
        "\ufeff": ["pattern"],
        "\x1f": ["pattern"],
    }
    for v, want in cases.items():
        assert reasons(v) == want, repr(v)
    assert len(check_trace_code("A" * 32 + "a", CFG)) == 2
