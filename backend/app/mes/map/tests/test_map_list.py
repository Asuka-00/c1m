"""P2 坐标图列表：分页（page_size ≤ 100）、筛选、排序、只看最新版本、UTC Z（D45）、
只读成员可查（mes.map:read）。"""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.mes.map.tests.test_map_import import MAP, _bins, _fx, _post
from app.testing.mes import Mes


def test_map_list(client: TestClient, db: Session) -> None:
    m = Mes(client, db)
    _bins(m)
    _post(m, "/import", _fx("map_ok.csv"), file_name="a.csv")
    _post(m, "/import", _fx("map_ok.csv"), file_name="b.csv")  # 两片各 v2

    def get(status: int = 200, **p: object) -> dict:
        r = client.get(f"{MAP}/maps", headers=m.h, params=p)
        assert r.status_code == status, r.text
        return r.json()

    r = get()
    assert r["count"] == 4 and len(r["data"]) == 4
    x = r["data"][0]
    assert x["imported_at"].endswith("Z") and x["created_at"].endswith("Z")
    assert x["bin_set_code"] == "BINSET-DEMO" and x["bin_set_version"] == 1
    assert x["source"] == "manual" and "cells" not in x
    # 默认按导入时间倒序：最新导入（b.csv，v2）在前
    assert x["file_name"] == "b.csv" and x["map_version"] == 2 and x["is_latest"]
    r = get(substrate_id="WF001-01", sort_by="map_version", sort_order="asc")
    assert [d["map_version"] for d in r["data"]] == [1, 2]
    assert [d["is_latest"] for d in r["data"]] == [False, True]
    assert get(latest_only=True)["count"] == 2
    assert get(q="a.cs")["count"] == 2
    assert get(substrate_type="strip")["count"] == 0
    p = get(page_size=1, page=2, sort_by="substrate_id")
    assert p["count"] == 4 and len(p["data"]) == 1
    assert get(imported_from="2000-01-01T08:00:00+08:00")["count"] == 4
    assert get(imported_to="2000-01-01T00:00:00Z")["count"] == 0
    get(422, page_size=101)
    get(422, sort_by="bogus")
    get(422, substrate_type="die")
    # 只读成员有 mes.map:read
    from app.mes.product.tests.test_bom import _member

    h = _member(client, db, m)
    assert client.get(f"{MAP}/maps", headers=h).status_code == 200
