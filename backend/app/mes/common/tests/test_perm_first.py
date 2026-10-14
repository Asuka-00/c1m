"""D34：P1 新接口先查权限、再校验请求体。无权限成员发错误请求体 → 403，不带字段明细。"""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.execution.tests.test_exec import EXEC, Line
from app.mes.product.tests.test_bom import _member

API = EXEC[: -len("/exec")]
EQP = f"{API}/eqp"


def _403(r: Any) -> None:
    assert r.status_code == 403, r.text
    d = r.json()["detail"]
    assert isinstance(d, str) and "body" not in r.text and "loc" not in r.text, r.text


def test_no_permission_bad_body_is_403(client: TestClient, db: Session) -> None:
    f = Line(client, db)
    h = _member(client, db, f.m)
    rid = uuid.uuid4()
    bad: list[tuple[str, Any]] = [
        ("{not json", None),  # 非法 JSON
        ("[1, 2]", None),  # 不是对象
        (None, {"unknown": 1, "status": "active"}),  # 未知 / 只读字段
    ]
    urls = [
        f"{API}/bom/{rid}/activate",
        f"{API}/bom/{rid}/void",
        f"{API}/bom/{rid}/copy",
        f"{API}/bom",
        f"{API}/bom-line",
        f"{API}/bom-line-substitute",
        f"{API}/customer",
        f"{EQP}/{f.eq['id']}/mount",
        f"{EQP}/mount/{rid}/unmount",
        f"{EQP}/qual/{rid}/result",  # 不存在的 Qual 任务：仍是 403，不是 404
    ]
    for url in urls:
        for raw, js in bad:
            if raw is not None:
                r = client.post(
                    url, headers={**h, "Content-Type": "application/json"}, content=raw
                )
            else:
                r = client.post(url, headers=h, json=js)
            _403(r)
    for ent in ("bom", "customer"):
        r = client.patch(
            f"{API}/{ent}/{rid}",
            headers={**h, "Content-Type": "application/json"},
            content="{bad",
        )
        _403(r)
    # 有权限时同样的错误请求体才拿到 422 字段明细
    r = client.post(
        f"{EQP}/qual/{rid}/result", headers=f.m.h, json={"result": "x", "foo": 1}
    )
    assert r.status_code == 422 and r.json()["detail"][0]["loc"][0] == "body"
    r = client.post(f"{EQP}/qual/{rid}/result", headers=f.m.h, json={"result": "pass"})
    assert r.status_code == 404


def test_qual_unknown_task_without_permission_is_403(
    client: TestClient, db: Session
) -> None:
    """D34 补充：无权限的人拿不存在的 Qual 任务 ID 登记结果 → 403（先查权限再查任务）。"""
    f = Line(client, db)
    h = _member(client, db, f.m)
    r = client.post(
        f"{EQP}/qual/{uuid.uuid4()}/result", headers=h, json={"result": "pass"}
    )
    _403(r)
