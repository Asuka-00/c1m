"""目标地址与凭据的安全约束。"""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
PORTS_ENV = "SIM_ALLOWED_PORTS"


class UnsafeTarget(ValueError):
    pass


def allowed_ports(raw: str | None = None) -> set[int]:
    """解析 SIM_ALLOWED_PORTS（逗号分隔）。空 = 一个端口都不允许（D54 白名单，默认全拒）。"""
    raw = os.environ.get(PORTS_ENV, "") if raw is None else raw
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit() or not 0 < int(part) < 65536:
            raise UnsafeTarget(f"{PORTS_ENV} 里有无效端口：{part!r}")
        out.add(int(part))
    return out


def check_target(url: str, ports: set[int] | None = None) -> str:
    """只允许 127.0.0.1/localhost，且端口必须在 SIM_ALLOWED_PORTS 白名单里。"""
    try:
        u = urlparse(url)
        port = u.port
    except ValueError as e:
        raise UnsafeTarget(f"目标地址无效：{url}（{e}）") from None
    if u.scheme not in ("http", "https") or not u.hostname:
        raise UnsafeTarget(f"目标地址无效：{url}")
    if u.hostname not in ALLOWED_HOSTS:
        raise UnsafeTarget(f"只允许 127.0.0.1/localhost，拒绝 {u.hostname}")
    if port is None:
        raise UnsafeTarget(f"目标地址必须显式写端口：{url}")
    allow = allowed_ports() if ports is None else ports
    if port not in allow:
        shown = ",".join(map(str, sorted(allow))) or "空（默认全部拒绝）"
        raise UnsafeTarget(
            f"端口 {port} 不在白名单 {PORTS_ENV}={shown} 里；确认是自己的环境后设置，例如 {PORTS_ENV}={port}"
        )
    return url.rstrip("/")


SECRET_KEYS = re.compile(r"(password|passwd|token|secret|authorization)", re.I)


def redact(obj):
    """报告里去掉任何像凭据的字段。"""
    if isinstance(obj, dict):
        return {k: ("***" if SECRET_KEYS.search(str(k)) else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


# 失败时记录 response detail 用：键名按段匹配（snake/kebab/camel 拆段），避免误伤 monkey 之类
DETAIL_SECRET_SEGMENTS = {
    "pw",
    "pwd",
    "password",
    "passwd",
    "secret",
    "token",
    "key",
    "authorization",
    "auth",
    "cookie",
    "credential",
    "credentials",
    "apikey",
}
DETAIL_SECRET_SUBSTR = re.compile(r"(password|passwd|secret|token|authorization|cookie|credential)", re.I)
MASK = "***"


def is_secret_key(k) -> bool:
    s = str(k)
    if DETAIL_SECRET_SUBSTR.search(s):
        return True
    segs = re.split(r"[^0-9a-zA-Z]+|(?<=[a-z0-9])(?=[A-Z])", s)
    return any(seg.lower() in DETAIL_SECRET_SEGMENTS for seg in segs if seg)


def redact_detail(obj):
    """遮掉 response detail 里的凭据类键（pw/password/secret/token/key/authorization/cookie/credential）。

    FastAPI/pydantic 的错误项里，loc 末段是凭据字段时，input（原值回显）也一并遮掉。
    """
    if isinstance(obj, list):
        return [redact_detail(x) for x in obj]
    if not isinstance(obj, dict):
        return obj
    loc = obj.get("loc")
    loc_secret = isinstance(loc, (list, tuple)) and bool(loc) and is_secret_key(loc[-1])
    out = {}
    for k, v in obj.items():
        if is_secret_key(k) or (loc_secret and k == "input"):
            out[k] = MASK
        else:
            out[k] = redact_detail(v)
    return out


def env(name: str, required: bool = False) -> str | None:
    v = os.environ.get(name) or None
    if required and not v:
        raise SystemExit(f"缺少环境变量 {name}")
    return v
