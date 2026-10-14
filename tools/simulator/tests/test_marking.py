from sim.marking import check_pattern_config, check_read_code, check_trace_code, pattern_allowed

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
    assert pattern_allowed("^[A-Z0-9-]+$") and not pattern_allowed("^[A-Z][A-Z0-9-]+$")
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
    for ok in ("^[A-Z0-9-]+$", "^[A-Z]+$", "^[0-9A-F-]+$", "^[ABC123]+$", "^[A-C3-7X]+$", "^[A-A]+$"):
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


def test_d79s4_ctx_fields():
    cfg = {"trace_code_max_length": 20, "trace_code_pattern": "^[0-9]+$"}
    assert check_trace_code("1" * 21, cfg) == [
        {"type": "value_error", "ctx": {"reason": "max_length", "max_length": 20}}
    ]
    assert check_trace_code("A1", cfg) == [{"type": "value_error", "ctx": {"reason": "pattern", "pattern": "^[0-9]+$"}}]
    # read_code：N 固定 128，不看 config；无格式校验（不带 pattern）
    assert check_read_code("a" * 129) == [{"type": "value_error", "ctx": {"reason": "max_length", "max_length": 128}}]
    assert check_read_code("a" * 128) == [] and check_read_code("lower_!") == []
    for blank in ("", " ", "\t\n", "\u3000"):
        assert check_read_code(blank) == [{"type": "missing"}], repr(blank)
    assert check_read_code("\ufeff") == [] and check_read_code(5) == [{"type": "string_type"}]


def test_d79s5_pattern_unsupported():
    ok = ["^[A-Z0-9-]+$", "^[A-Z]+$", "^[0-9]+$", "^[0-]+$", "^[B-DX2-5-]+$"]
    for p in ok:
        assert check_pattern_config(p) == [], p
    bad = {
        "^[A-Z][0-9]+$": "多类串联",
        "^[A-Z]+[0-9]+$": "多类串联（各带 +）",
        "^[A-Z][A-Z0-9-]+$": "前缀类",
        "^[A-Z]{1,32}$": "{m,n} 量词",
        "^[A-Z]{4}$": "{m} 量词",
        "^[A-Z]{2,}$": "{m,} 量词",
        "^[A-Z]*$": "* 量词",
        "^[A-Z]?$": "? 量词",
        "^[A-Z]$": "缺 +",
        "^[A-Z]++$": "占有量词",
        "^[^A-Z]+$": "否定类",
        "^[^]+$": "否定空类",
        "^[A-Z\\-]+$": "类内反斜杠",
        "^\\d+$": "反斜杠简写",
        "^[\\d]+$": "类内 \\d",
        "^[A-Z]+\\Z": "反斜杠锚",
        "^[Z-A]+$": "降序区间",
        "^[9-0]+$": "降序数字区间",
        "^[A-Z0-9Z-B]+$": "后段降序",
        "^[]+$": "空类",
        "^[-]+$": "只有 -",
        "^[-A-Z]+$": "- 在开头",
        "^[A-Z-0-9]+$": "- 在中间",
        "^[A-9]+$": "跨类区间",
        "^[a-z]+$": "小写",
        "^[A-Z_]+$": "其他字符",
        "^[A-Z ]+$": "空格",
        "[A-Z]+": "缺 ^$",
        "^[A-Z]+": "缺 $",
        "(?i)^[A-Z]+$": "flag",
        "^([A-Z])+$": "分组",
        "^[A-Z]+|[0-9]+$": "或",
        "^.+$": "点",
        "": "空串",
        None: "null",
        123: "非字符串",
    }
    for p, why in bad.items():
        assert check_pattern_config(p) == [{"type": "value_error", "ctx": {"reason": "pattern_unsupported"}}], why
