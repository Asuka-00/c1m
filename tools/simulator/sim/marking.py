"""P3-B2 打标 trace_code 本地预校验（D78 补充三/四）：只做提示，不改写原值；以后端 422 为准。

配置取自 ``GET /mes/marking/config``：``trace_code_max_length``、``trace_code_pattern``（带 ``^…$`` 的完整正则，
只用字符类、``^``、``$``、``+``，无 flag）。
"""

from __future__ import annotations

import re
from typing import Any

# D79 补充五（N-X1）：只允许单个正向字符类 ^[...]+$；类里只能有大写字母、数字和同类升序区间，- 只能放最后。
# 不允许：多个字符类串联、{m,n} 等量词、[^…]、反斜杠、降序区间、空类。与前端 isAllowedTracePattern
# （POSITIVE_CLASS_RE，fsft-fe 245a721）同一写法；后端写 config 不合规 → 422 value_error ctx.reason=pattern_unsupported
_ALLOWED = re.compile(r"\^\[(?:[A-Z](?:-[A-Z])?|[0-9](?:-[0-9])?)+-?\]\+\$")
PATTERN_UNSUPPORTED = {"type": "value_error", "ctx": {"reason": "pattern_unsupported"}}
# 补充五：「纯空白」只认这几种（含全角空格 U+3000）；不用 str.strip()（它还会吃掉 \x1c–\x1f 等）
_BLANK = re.compile("[ \t\r\n\u3000]*")


def pattern_allowed(pattern: str) -> bool:
    """config 的 pattern 是否符合 D79 补充二 4 / 补充五 的白名单（单个 ^[...]+$）。"""
    if not isinstance(pattern, str) or _ALLOWED.fullmatch(pattern) is None:
        return False
    # 区间必须是升序（Z-A、9-0 不收）
    return all(a <= b for a, b in re.findall(r"([A-Z0-9])-([A-Z0-9])", pattern[2:-3]))


def check_pattern_config(pattern: Any) -> list[dict[str, Any]]:
    """写 config 时的本地预检（D79 补充五）：不合规 → value_error ctx.reason=pattern_unsupported。"""
    return [] if pattern_allowed(pattern) else [PATTERN_UNSUPPORTED]


READ_CODE_MAX = 128  # D79 补充二 3


ABSENT = object()  # 请求体里完全没有 read_code 字段


def check_inspect_body(body: dict[str, Any]) -> list[dict[str, Any]]:
    """检验请求体的 read_code 预校验：缺字段也算 missing（D81 补记）。"""
    return check_read_code(body.get("read_code", ABSENT))


def check_read_code(value: Any = ABSENT) -> list[dict[str, Any]]:
    """OCR 读回码：不校验格式（不合规也记录，按不一致强制 fail）；缺字段 / null / 空白 missing（D79 补充三、D81）；
    超过 128 码点 max_length。"""
    if value is ABSENT or value is None:
        return [{"type": "missing"}]
    if not isinstance(value, str):
        return [{"type": "string_type"}]
    if _BLANK.fullmatch(value):  # D79 补充三：空串 / 纯空白一律 missing
        return [{"type": "missing"}]
    if len(value) > READ_CODE_MAX:  # D79 补充四：ctx {reason: max_length, max_length: 128}
        return [{"type": "value_error", "ctx": {"reason": "max_length", "max_length": READ_CODE_MAX}}]
    return []


def check_trace_code(value: Any, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """按后端规则列出违规项（形状同 422 detail 的 ctx），空列表为通过。

    - ``None``：``missing``；其他非字符串（数字等）：``string_type``，同后端 pydantic（评审 E4）
    - 空串 / 纯空白（``re.fullmatch(r"[ \t\r\n\u3000]*")``）：只报一条 ``missing``（补充四 3、补充五）；
      U+FEFF、\x1f 等不算空白，落到 pattern
    - 超长（D79 补充四）：``value_error`` ctx ``{reason: max_length, max_length: <config 值>}``
    - 不匹配（D79 补充四）：``value_error`` ctx ``{reason: pattern, pattern: <config 原样正则>}``，config 正则全串匹配
      （不去空格、不转大小写，补充四 4）
    """
    if value is None:
        return [{"type": "missing"}]
    if not isinstance(value, str):
        return [{"type": "string_type"}]
    if _BLANK.fullmatch(value):
        return [{"type": "missing"}]
    out: list[dict[str, Any]] = []
    # 长度按 Unicode 码点（D79 补充二 2：后端 len()，前端 [...s].length）
    mx = int(cfg["trace_code_max_length"])
    if len(value) > mx:
        out.append({"type": "value_error", "ctx": {"reason": "max_length", "max_length": mx}})
    pat = cfg["trace_code_pattern"]
    if re.fullmatch(pat, value) is None:
        out.append({"type": "value_error", "ctx": {"reason": "pattern", "pattern": pat}})
    return out
