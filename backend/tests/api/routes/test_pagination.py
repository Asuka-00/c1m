from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.platform.users import service as crud
from app.platform.users.schemas import UserCreate
from tests.utils.utils import random_email, random_lower_string

API = settings.API_V1_STR


def _owner(client: TestClient, db: Session) -> dict[str, str]:
    email, pw = random_email(), random_lower_string()
    crud.create_user(session=db, user_create=UserCreate(email=email, password=pw))
    tok = client.post(
        f"{API}/login/access-token", data={"username": email, "password": pw}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _tid(client: TestClient, h: dict[str, str]) -> str:
    return client.get(f"{API}/tenants/me", headers=h).json()["data"][0]["tenant"]["id"]


def test_default_page_size_and_sorting(client: TestClient, db: Session) -> None:
    h = _owner(client, db)
    url = f"{API}/tenants/{_tid(client, h)}/roles"
    for i in range(25):
        assert (
            client.post(url, headers=h, json={"name": f"role-{i:02d}"}).status_code
            == 200
        )
    r = client.get(url, headers=h).json()
    assert (
        r["count"] == 28 and len(r["data"]) == 20
    )  # 25 + owner/admin/member; default page_size 20
    assert len(client.get(url, headers=h, params={"page": 2}).json()["data"]) == 8
    asc = client.get(url, headers=h, params={"sort_by": "name", "page_size": 5}).json()
    assert [x["name"] for x in asc["data"]] == [
        "admin",
        "member",
        "owner",
        "role-00",
        "role-01",
    ]
    desc = client.get(
        url, headers=h, params={"sort_by": "name", "sort_order": "desc", "page_size": 3}
    ).json()
    assert [x["name"] for x in desc["data"]] == ["role-24", "role-23", "role-22"]
    # legacy skip/limit still works
    assert (
        len(client.get(url, headers=h, params={"skip": 26, "limit": 10}).json()["data"])
        == 2
    )
    # whitelist + bounds
    assert client.get(url, headers=h, params={"sort_by": "id; drop"}).status_code == 422
    assert client.get(url, headers=h, params={"page_size": 101}).status_code == 422
    assert client.get(url, headers=h, params={"page": 0}).status_code == 422


def test_pagination_keeps_tenant_isolation(client: TestClient, db: Session) -> None:
    ha, hb = _owner(client, db), _owner(client, db)
    ta, tb = _tid(client, ha), _tid(client, hb)
    client.post(f"{API}/tenants/{ta}/roles", headers=ha, json={"name": "a-only"})
    r = client.get(
        f"{API}/tenants/{tb}/roles", headers=hb, params={"page_size": 100}
    ).json()
    assert r["count"] == 3 and "a-only" not in {x["name"] for x in r["data"]}
    assert client.get(f"{API}/tenants/{tb}/members", headers=hb).json()["count"] == 1


def test_all_list_endpoints_paginate_and_sort(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    h = superuser_token_headers
    for _ in range(3):
        crud.create_user(
            session=db,
            user_create=UserCreate(
                email=random_email(), password=random_lower_string()
            ),
        )
    tid = client.get(f"{API}/tenants/me", headers=h).json()["data"][0]["tenant"]["id"]
    cases = {
        "/users/": "email",
        "/roles/": "name",
        "/permissions/": "code",
        "/tenants/": "slug",
        f"/tenants/{tid}/members": "email",
        f"/tenants/{tid}/roles": "name",
        "/menus/": "title",
    }
    for url, field in cases.items():
        r = client.get(
            f"{API}{url}",
            headers=h,
            params={"page_size": 2, "sort_by": field, "sort_order": "desc"},
        )
        assert r.status_code == 200, (url, r.text)
        body = r.json()
        assert (
            set(body) == {"data", "count"}
            and len(body["data"]) <= 2
            and body["count"] >= len(body["data"])
        )
        vals = [x[field] for x in body["data"]]
        assert vals == sorted(vals, reverse=True), url
        assert (
            client.get(f"{API}{url}", headers=h, params={"sort_by": "nope"}).status_code
            == 422
        ), url
