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


def test_d79s2_codepoints_and_read_code():
    from sim.marking import check_read_code

    assert reasons("A" * 31 + "\U0001f600") == ["pattern"]  # 32 码点，不超长
    assert reasons("A" * 32 + "\U0001f600") == ["max_length", "pattern"]
    assert check_read_code("ab_1 ") == [] and check_read_code("\U0001f600" * 128) == []
    assert check_read_code("") == [{"type": "missing"}] and check_read_code(None) == [{"type": "missing"}]
    assert check_read_code("A" * 129)[0]["ctx"] == {"reason": "max_length", "max_length": 128}


def test_d79s2_pattern_whitelist():
    for ok in ("^[A-Z0-9-]+$", "^[A-Z]+$", "^[A-Z][0-9]+$", "^[0-9A-F-]+$", "^[ABC123]+$", "^[A-Z][-]+$"):
        assert pattern_allowed(ok), ok
    for bad in (
        "^[^A-Z]+$",  # 否定类
        "^[A-Z\\-]+$",  # 反斜杠
        "^[-A-Z]+$",  # - 不在最后
        "^[A-Z-0-9]+$",  # - 在中间
        "^[a-z]+$",  # 小写
        "^[A-Z_]+$",  # 其他字符
        "^[Z-A]+$",  # 倒序区间
        "^[A-9]+$",  # 跨类区间
        "^[]+$",
        "^[A-Z]*$",
        "^[A-Z]{1,32}$",
        "[A-Z]+",
    ):
        assert not pattern_allowed(bad), bad
