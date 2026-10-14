"""目标地址与凭据的安全约束。"""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

ALLOWED_HOSTS = {"127.0.0.1"}
# 团队共享/他人占用的端口：模拟器一律拒绝（工作区规则）
FORBIDDEN_PORTS = {8010, 8011, 8012, 5174, 5184}


class UnsafeTarget(ValueError):
    pass


def check_target(url: str, allow_remote: bool = False) -> str:
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise UnsafeTarget(f"目标地址无效：{url}")
    if not allow_remote and u.hostname not in ALLOWED_HOSTS:
        raise UnsafeTarget(f"默认只允许 127.0.0.1，拒绝 {u.hostname}（需要时加 --allow-remote）")
    if u.port in FORBIDDEN_PORTS:
        raise UnsafeTarget(f"端口 {u.port} 是共享/他人端口，模拟器拒绝连接")
    return url.rstrip("/")


SECRET_KEYS = re.compile(r"(password|passwd|token|secret|authorization)", re.I)


def redact(obj):
    """报告里去掉任何像凭据的字段。"""
    if isinstance(obj, dict):
        return {k: ("***" if SECRET_KEYS.search(str(k)) else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


def env(name: str, required: bool = False) -> str | None:
    v = os.environ.get(name) or None
    if required and not v:
        raise SystemExit(f"缺少环境变量 {name}")
    return v
