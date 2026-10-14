"""bom.md §12：所有接口输出的时间统一为 UTC ``Z``；输入仍接受带偏移的时间。"""

import json
import re
from datetime import datetime, timedelta, timezone

from fastapi.encoders import jsonable_encoder
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.config import settings
from app.core.models import UtcDateTime, iso_utc
from app.main import app

OFFSET_TS = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d(:\d\d(\.\d+)?)?[+-]\d\d:?\d\d\"")
TW = timezone(timedelta(hours=8))


def test_iso_utc() -> None:
    assert iso_utc(datetime(2026, 1, 1, 8, tzinfo=TW)) == "2026-01-01T00:00:00Z"
    assert iso_utc(datetime(2026, 1, 1, 8)) == "2026-01-01T08:00:00"


def test_dict_responses_encode_utc() -> None:
    """无 response_model 的接口（dict）经 jsonable_encoder 也输出 Z。"""
    out = jsonable_encoder({"at": datetime(2026, 1, 1, 8, 30, tzinfo=TW)})
    assert out == {"at": "2026-01-01T00:30:00Z"}


def test_utc_datetime_type_accepts_offset_input() -> None:
    class M(BaseModel):
        at: UtcDateTime

    m = M.model_validate({"at": "2026-01-01T08:00:00+08:00"})
    assert m.at.utcoffset() == timedelta(hours=8)
    assert m.model_dump(mode="json") == {"at": "2026-01-01T00:00:00Z"}
    assert m.model_dump()["at"] == m.at  # python 模式不变


def test_no_offset_timestamps_in_get_endpoints(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """扫描所有无路径参数的 GET 接口，响应中不得出现带非 Z 偏移的时间字符串。"""
    bad: list[str] = []
    for r in app.routes:
        if not isinstance(r, APIRoute) or "GET" not in r.methods or "{" in r.path:
            continue
        if not r.path.startswith(settings.API_V1_STR):
            continue
        resp = client.get(r.path, headers=superuser_token_headers)
        if resp.status_code != 200 or "json" not in resp.headers.get(
            "content-type", ""
        ):
            continue
        m = OFFSET_TS.search(json.dumps(resp.json()))
        if m:
            bad.append(f"{r.path}: {m.group(0)}")
    assert not bad, bad
