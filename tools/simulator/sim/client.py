"""最小 HTTP 客户端（只用标准库）。令牌只放在内存的请求头里，不进报告。"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

API = "/api/v1"


@dataclass
class Resp:
    status: int
    body: Any
    elapsed_ms: int = 0

    @property
    def code(self) -> str | None:
        """取错误 code：后端放在 ``detail.code``，也兼容顶层 ``code``。"""
        b = self.body
        if isinstance(b, dict):
            d = b.get("detail")
            if isinstance(d, dict) and d.get("code"):
                return d["code"]
            # 422 校验错误是列表：取第一条的 code（如 time_in_future），没有则取 type
            if isinstance(d, list) and d and isinstance(d[0], dict):
                c = d[0].get("code") or d[0].get("type")
                if isinstance(c, str):
                    return c
            if isinstance(b.get("code"), str):
                return b["code"]
        return None

    @property
    def check_results(self) -> list[dict]:
        b = self.body if isinstance(self.body, dict) else {}
        d = b.get("detail") if isinstance(b.get("detail"), dict) else b
        res = d.get("results") or d.get("checks") or []
        return [x for x in res if isinstance(x, dict)]


@dataclass
class Client:
    base: str
    tenant: str | None = None
    token: str | None = None
    timeout: float = 30.0
    headers: dict[str, str] = field(default_factory=dict)

    def _h(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = {"Accept": "application/json", **self.headers}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if self.tenant:
            h["X-Tenant-ID"] = self.tenant
        h.update(extra or {})
        return h

    def request(
        self,
        method: str,
        path: str,
        json_body: Any = None,
        params: dict | None = None,
        headers: dict[str, str] | None = None,
        form: dict | None = None,
    ) -> Resp:
        url = self.base + (path if path.startswith(API) else API + path)
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        data = None
        h = self._h(headers)
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            h["Content-Type"] = "application/x-www-form-urlencoded"
        elif json_body is not None:
            data = json.dumps(json_body).encode()
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        ms = int((time.monotonic() - t0) * 1000)
        try:
            body = json.loads(raw) if raw else None
        except ValueError:
            body = raw.decode(errors="replace")[:500]
        return Resp(status, body, ms)

    def get(self, path: str, **params) -> Resp:
        return self.request("GET", path, params=params)

    def post(self, path: str, body: Any = None, idem: str | None = None) -> Resp:
        return self.request("POST", path, body, headers={"Idempotency-Key": idem} if idem else None)

    def login(self, user: str, password: str) -> None:
        r = self.request("POST", "/login/access-token", form={"username": user, "password": password})
        if r.status != 200 or not isinstance(r.body, dict) or "access_token" not in r.body:
            raise SystemExit(f"登录失败：HTTP {r.status}")
        self.token = r.body["access_token"]

    def openapi_paths(self) -> set[str]:
        r = self.get("/openapi.json")
        if r.status != 200 or not isinstance(r.body, dict):
            return set()
        return {p.removeprefix(API) for p in r.body.get("paths", {})}
