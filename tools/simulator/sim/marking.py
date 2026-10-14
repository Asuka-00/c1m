"""P3-B2 打标 trace_code 本地预校验（D78 补充三/四）：只做提示，不改写原值；以后端 422 为准。

配置取自 ``GET /mes/marking/config``：``trace_code_max_length``、``trace_code_pattern``（带 ``^…$`` 的完整正则，
只用字符类、``^``、``$``、``+``，无 flag）。
"""

from __future__ import annotations

import re
from typing import Any

# 补充四 2 + D79 补充二 4：^ 开头、$ 结尾，中间是若干「正向字符类[+]」；类里只能有大写字母、数字、区间（A-Z、0-9），
# 字面 - 只能放在类的最后；不允许 [^…]，不允许任何反斜杠
_ITEM = r"(?:[A-Z]-[A-Z]|[0-9]-[0-9]|[A-Z0-9])"
_CLASS = rf"\[{_ITEM}+-?\]|\[-\]"
_ALLOWED = re.compile(rf"\^(?:(?:{_CLASS})\+?)+\$")
# 补充五：「纯空白」只认这几种（含全角空格 U+3000）；不用 str.strip()（它还会吃掉 \x1c–\x1f 等）
_BLANK = re.compile("[ \t\r\n\u3000]*")


def pattern_allowed(pattern: str) -> bool:
    """config 返回的 pattern 是否符合补充四 2 / D79 补充二 4 的白名单语法。"""
    if not isinstance(pattern, str) or "\\" in pattern or _ALLOWED.fullmatch(pattern) is None:
        return False
    # 区间必须是升序（Z-A 这类 re 也会报错）
    return all(a <= b for a, b in re.findall(r"([A-Z0-9])-([A-Z0-9])", pattern))


READ_CODE_MAX = 128  # D79 补充二 3


def check_read_code(value: Any) -> list[dict[str, Any]]:
    """OCR 读回码：不校验格式（不合规也记录，按不一致强制 fail）；空值 missing；超过 128 码点 max_length。"""
    if value is None:
        return [{"type": "missing"}]
    if not isinstance(value, str):
        return [{"type": "string_type"}]
    if value == "":
        return [{"type": "missing"}]
    if len(value) > READ_CODE_MAX:
        return [{"type": "value_error", "ctx": {"reason": "max_length", "max_length": READ_CODE_MAX}}]
    return []


def check_trace_code(value: Any, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """按后端规则列出违规项（形状同 422 detail 的 ctx），空列表为通过。

    - ``None``：``missing``；其他非字符串（数字等）：``string_type``，同后端 pydantic（评审 E4）
    - 空串 / 纯空白（``re.fullmatch(r"[ \t\r\n\u3000]*")``）：只报一条 ``missing``（补充四 3、补充五）；
      U+FEFF、\x1f 等不算空白，落到 pattern
    - 超长：``value_error`` ctx ``{reason: max_length, max_length}``
    - 不匹配：``value_error`` ctx ``{reason: pattern, pattern}``，config 正则全串匹配
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
