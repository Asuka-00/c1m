"""D65 补充 4 / D38：通用增删改查对每个实体都拒绝未知字段（422 unknown_field）。"""

import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.spec.engine import ENTITIES
from app.testing.mes import API, Mes


def test_every_entity_rejects_unknown_fields(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    bad = []
    for e in ENTITIES.values():
        url = f"{API}/{e.url}"
        for method, u in (("post", url), ("patch", f"{url}/{uuid.uuid4()}")):
            r = getattr(client, method)(
                u,
                headers={**m.h, "Idempotency-Key": str(uuid.uuid4())},
                json={"__bogus__": 1},
            )
            if r.status_code == 404 and method == "post":
                break  # 不对外开放通用接口的内部实体（如 code_rule_counter）
            d = r.json().get("detail") if r.status_code == 422 else None
            if not (
                isinstance(d, list)
                and any(
                    x["loc"] == ["body", "__bogus__"] and x["code"] == "unknown_field"
                    for x in d
                )
            ):
                bad.append((e.code, method, r.status_code))
    assert len(ENTITIES) > 50
    skipped = [c for c in ENTITIES if c == "code_rule_counter"]
    assert len(skipped) <= 1
    assert not bad, bad


def test_old_entity_reason_code_strict(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    url = f"{API}/reason-code"
    r = client.post(url, headers=m.h, json={"code": "R1", "name": "r", "foo": 1})
    assert r.status_code == 422, r.text
    assert r.json()["detail"][0]["code"] == "unknown_field"
    # system fields too
    r = client.post(url, headers=m.h, json={"code": "R1", "name": "r", "id": "x"})
    assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body", "id"]
