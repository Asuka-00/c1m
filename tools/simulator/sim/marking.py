"""P3-B2 打标 trace_code 本地预校验（D78 补充三/四）：只做提示，不改写原值；以后端 422 为准。

配置取自 ``GET /mes/marking/config``：``trace_code_max_length``、``trace_code_pattern``（带 ``^…$`` 的完整正则，
只用字符类、``^``、``$``、``+``，无 flag）。
"""

from __future__ import annotations

import re
from typing import Any

# 补充四 2：允许的正则语法——^ 开头、$ 结尾，中间是若干「字符类[+]」；字符类里不能有 \\d、\\w 等转义类
_CLASS = r"\[(?:[^\]\\]|\\[-\]\\^])+\]"
_ALLOWED = re.compile(rf"\^(?:{_CLASS}\+?)+\$")
# 补充五：「纯空白」只认这几种（含全角空格 U+3000）；不用 str.strip()（它还会吃掉 \x1c–\x1f 等）
_BLANK = re.compile("[ \t\r\n\u3000]*")


def pattern_allowed(pattern: str) -> bool:
    """config 返回的 pattern 是否符合补充四 2 的受限语法。"""
    return isinstance(pattern, str) and _ALLOWED.fullmatch(pattern) is not None


def check_trace_code(value: Any, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """按后端规则列出违规项（形状同 422 detail 的 ctx），空列表为通过。

    - 空串 / 纯空白（``re.fullmatch(r"[ \t\r\n\u3000]*")``）/ 非字符串：只报一条 ``missing``（补充四 3、补充五）；
      U+FEFF、\x1f 等不算空白，落到 pattern
    - 超长：``value_error`` ctx ``{reason: max_length, max_length}``
    - 不匹配：``value_error`` ctx ``{reason: pattern, pattern}``，config 正则全串匹配
      （不去空格、不转大小写，补充四 4）
    """
    if not isinstance(value, str) or _BLANK.fullmatch(value):
        return [{"type": "missing"}]
    out: list[dict[str, Any]] = []
    mx = int(cfg["trace_code_max_length"])
    if len(value) > mx:
        out.append({"type": "value_error", "ctx": {"reason": "max_length", "max_length": mx}})
    pat = cfg["trace_code_pattern"]
    if re.fullmatch(pat, value) is None:
        out.append({"type": "value_error", "ctx": {"reason": "pattern", "pattern": pat}})
    return out
