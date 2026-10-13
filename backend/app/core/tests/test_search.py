"""`q` search (ILIKE over whitelisted text columns) + simple filters on list endpoints."""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.platform.rbac.permissions import TENANT_PERMISSIONS
from app.platform.users import service as crud
from app.platform.users.schemas import UserCreate, UserUpdate
from app.testing.user import create_owned_tenant
from app.testing.utils import login_name, random_lower_string, username_for

API = settings.API_V1_STR


def _login(client: TestClient, email: str, pw: str) -> dict[str, str]:
    tok = client.post(
        f"{API}/login/access-token",
        data={"username": login_name(email), "password": pw},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_users_search_paginates_sorts_and_counts(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    tag = random_lower_string()[:8]
    for i in range(23):
        _u = crud.create_user(
            session=db,
            user_create=UserCreate(
                email=f"{tag}-{i:02d}@example.com",
                username=username_for(f"{tag}-{i:02d}@example.com"),
                password=random_lower_string(),
                full_name=f"Zed {i}",
            ),
        )
        create_owned_tenant(db, _u)
    _u = crud.create_user(
        session=db,
        user_create=UserCreate(
            email=f"other-{tag[:4]}x@example.com",
            username=username_for(f"other-{tag[:4]}x@example.com"),
            password=random_lower_string(),
            full_name=f"Name {tag.upper()}",
        ),
    )
    create_owned_tenant(db, _u)
    h = superuser_token_headers
    r = client.get(
        f"{API}/platform/users/", headers=h, params={"q": tag.upper()}
    ).json()  # case-insensitive
    assert r["count"] == 24 and len(r["data"]) == 20  # also matches full_name
    p2 = client.get(
        f"{API}/platform/users/", headers=h, params={"q": tag, "page": 2}
    ).json()
    assert len(p2["data"]) == 4
    s = client.get(
        f"{API}/platform/users/",
        headers=h,
        params={
            "q": f"{tag}-",
            "sort_by": "email",
            "sort_order": "desc",
            "page_size": 2,
        },
    ).json()
    assert s["count"] == 23 and [u["email"] for u in s["data"]] == [
        f"{tag}-22@example.com",
        f"{tag}-21@example.com",
    ]
    assert (
        client.get(f"{API}/platform/users/", headers=h, params={"q": "   "}).json()[
            "count"
        ]
        >= 25
    )  # blank = no filter
    assert client.get(
        f"{API}/platform/users/", headers=h, params={"q": "zz-no-such-user-zz"}
    ).json() == {"data": [], "count": 0}
    # LIKE wildcards are literal
    assert (
        client.get(f"{API}/platform/users/", headers=h, params={"q": "%"}).json()[
            "count"
        ]
        == 0
    )
    assert (
        client.get(
            f"{API}/platform/users/", headers=h, params={"q": "x" * 101}
        ).status_code
        == 422
    )
    # is_active filter combines with q
    u = crud.get_user_by_email(session=db, email=f"{tag}-00@example.com")
    assert u
    crud.update_user(session=db, db_user=u, user_in=UserUpdate(is_active=False))
    assert (
        client.get(
            f"{API}/platform/users/",
            headers=h,
            params={"q": f"{tag}-", "is_active": False},
        ).json()["count"]
        == 1
    )
    assert (
        client.get(
            f"{API}/platform/users/",
            headers=h,
            params={"q": f"{tag}-", "is_active": True},
        ).json()["count"]
        == 22
    )


def test_search_respects_tenant_scope(client: TestClient, db: Session) -> None:
    tag = random_lower_string()[:8]
    hs = []
    for _ in range(2):
        email, pw = f"{random_lower_string()[:8]}@example.com", random_lower_string()
        _u = crud.create_user(
            session=db,
            user_create=UserCreate(
                email=email, username=username_for(email), password=pw
            ),
        )
        create_owned_tenant(db, _u)
        hs.append(_login(client, email, pw))
    ha, hb = hs
    ta = client.get(f"{API}/tenants/me", headers=ha).json()["data"][0]["tenant"]["id"]
    tb = client.get(f"{API}/tenants/me", headers=hb).json()["data"][0]["tenant"]["id"]
    client.post(
        f"{API}/tenants/{ta}/roles",
        headers=ha,
        json={"name": f"{tag}-r", "description": "Alpha"},
    )
    assert (
        client.get(f"{API}/tenants/{ta}/roles", headers=ha, params={"q": tag}).json()[
            "count"
        ]
        == 1
    )
    assert (
        client.get(
            f"{API}/tenants/{ta}/roles", headers=ha, params={"q": "alpha"}
        ).json()["count"]
        == 1
    )  # description
    assert (
        client.get(f"{API}/tenants/{tb}/roles", headers=hb, params={"q": tag}).json()[
            "count"
        ]
        == 0
    )
    # 非超级用户无法使用平台租户列表；只能看到自己的租户
    assert (
        client.get(f"{API}/platform/tenants", headers=hb, params={"q": "x"}).status_code
        == 403
    )
    assert len(client.get(f"{API}/tenants/me", headers=hb).json()["data"]) == 1
    members = client.get(
        f"{API}/tenants/{ta}/members", headers=ha, params={"q": "@example"}
    ).json()
    assert members["count"] == 1
    assert (
        client.get(
            f"{API}/tenants/{ta}/members", headers=ha, params={"q": "nobody"}
        ).json()["count"]
        == 0
    )


def test_search_other_endpoints(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    h = superuser_token_headers
    perms = client.get(
        f"{API}/platform/permissions/", headers=h, params={"q": "MEMBERS"}
    ).json()
    assert perms["count"] == 2 and {p["code"] for p in perms["data"]} == {
        "members:read",
        "members:write",
    }
    assert (
        client.get(
            f"{API}/platform/permissions/", headers=h, params={"q": "any user"}
        ).json()["count"]
        >= 2
    )  # description
    assert [
        r["name"]
        for r in client.get(
            f"{API}/platform/roles/", headers=h, params={"q": "admin"}
        ).json()["data"]
    ] == ["admin"]
    menus = client.get(
        f"{API}/platform/menus/", headers=h, params={"q": "/ten"}
    ).json()  # path
    assert {m["key"] for m in menus["data"]} >= {"p-tenants"}
    assert (
        client.get(
            f"{API}/platform/menus/",
            headers=h,
            params={"q": "Settings", "space": "workspace"},
        ).json()["count"]
        == 2  # Settings + Tenant Settings
    )
    t = client.get(f"{API}/platform/tenants", headers=h, params={"q": "DEFAULT"}).json()
    assert "default" in {x["slug"] for x in t["data"]}
    assert (
        client.get(
            f"{API}/platform/tenants",
            headers=h,
            params={"q": "default", "status": "suspended"},
        ).json()["count"]
        == 0
    )
    assert (
        client.get(
            f"{API}/platform/tenants", headers=h, params={"status": "bogus"}
        ).status_code
        == 422
    )


def test_enumerable_filters(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    h = superuser_token_headers
    tag = random_lower_string()[:8]
    # users: role_id (platform role), is_superuser — combined with q
    role = client.post(
        f"{API}/platform/roles/", headers=h, json={"name": f"r-{tag}"}
    ).json()
    users = [
        crud.create_user(
            session=db,
            user_create=UserCreate(
                email=f"{tag}-{i}@example.com",
                username=username_for(f"{tag}-{i}@example.com"),
                password=random_lower_string(),
            ),
        )
        for i in range(3)
    ]
    client.post(f"{API}/platform/users/{users[0].id}/roles/{role['id']}", headers=h)
    r = client.get(
        f"{API}/platform/users/", headers=h, params={"role_id": role["id"]}
    ).json()
    assert r["count"] == 1 and r["data"][0]["email"] == users[0].email
    assert (
        client.get(
            f"{API}/platform/users/",
            headers=h,
            params={"role_id": role["id"], "q": f"{tag}-1"},
        ).json()["count"]
        == 0
    )
    admin_id = next(
        x["id"]
        for x in client.get(f"{API}/platform/roles/", headers=h).json()["data"]
        if x["name"] == "admin"
    )
    assert settings.FIRST_SUPERUSER in {
        u["email"]
        for u in client.get(
            f"{API}/platform/users/", headers=h, params={"role_id": admin_id}
        ).json()["data"]
    }
    sup = client.get(
        f"{API}/platform/users/",
        headers=h,
        params={"is_superuser": True, "page_size": 100},
    ).json()
    assert sup["count"] >= 1 and all(u["is_superuser"] for u in sup["data"])
    assert (
        client.get(
            f"{API}/platform/users/", headers=h, params={"role_id": "nope"}
        ).status_code
        == 422
    )
    # permissions: scope
    p = client.get(
        f"{API}/platform/permissions/",
        headers=h,
        params={"scope": "tenant", "page_size": 100},
    ).json()
    assert p["count"] == len(TENANT_PERMISSIONS) and {
        x["scope"] for x in p["data"]
    } == {"tenant"}
    assert (
        client.get(
            f"{API}/platform/permissions/",
            headers=h,
            params={"scope": "tenant", "q": "members"},
        ).json()["count"]
        == 2
    )
    # menus: parent_id / hidden
    menus = client.get(
        f"{API}/platform/menus/", headers=h, params={"page_size": 100}
    ).json()["data"]
    admin_group = next(m["id"] for m in menus if m["key"] == "g-system")
    kids = client.get(
        f"{API}/platform/menus/", headers=h, params={"parent_id": admin_group}
    ).json()
    assert {m["key"] for m in kids["data"]} == {
        "user-permissions",  # 成员 / 租户角色 / 角色权限 合并为页签
        "config",
        "mes-audit_log",
        "notify-subscriptions",
    }
    assert (
        client.get(
            f"{API}/platform/menus/",
            headers=h,
            params={"parent_id": admin_group, "q": "perm"},
        ).json()["count"]
        == 1
    )
    assert (
        client.get(f"{API}/platform/menus/", headers=h, params={"hidden": True}).json()[
            "count"
        ]
        == 0
    )
    # members: role_id (tenant role)
    tid = client.get(f"{API}/tenants/me", headers=h).json()["data"][0]["tenant"]["id"]
    troles = {
        x["name"]: x["id"]
        for x in client.get(f"{API}/tenants/{tid}/roles", headers=h).json()["data"]
    }
    client.post(
        f"{API}/tenants/{tid}/members",
        headers=h,
        json={"username": users[1].username, "roles": ["member"]},
    )
    m = client.get(
        f"{API}/tenants/{tid}/members",
        headers=h,
        params={"role_id": troles["member"], "page_size": 100},
    ).json()
    assert users[1].email in {x["email"] for x in m["data"]} and all(
        "member" in x["roles"] for x in m["data"]
    )
    o = client.get(
        f"{API}/tenants/{tid}/members", headers=h, params={"role_id": troles["owner"]}
    ).json()
    assert settings.FIRST_SUPERUSER in {x["email"] for x in o["data"]} and users[
        1
    ].email not in {x["email"] for x in o["data"]}
