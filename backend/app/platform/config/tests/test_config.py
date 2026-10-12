"""System configuration: platform defaults, tenant overrides (RLS), validation,
permissions, uploads and the public branding endpoint."""

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.core.tenant import set_tenant
from app.platform.users import service as crud
from app.platform.users.schemas import UserCreate
from app.testing.utils import random_email, random_lower_string

API = settings.API_V1_STR
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _owner(client: TestClient, db: Session) -> tuple[dict[str, str], str, str]:
    email, pw = random_email(), random_lower_string()
    crud.create_user(session=db, user_create=UserCreate(email=email, password=pw))
    tok = client.post(
        f"{API}/login/access-token", data={"username": email, "password": pw}
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    t = client.get(f"{API}/tenants/me", headers=h).json()["data"][0]["tenant"]
    return {**h, "X-Tenant-ID": t["id"]}, t["id"], t["slug"]


@pytest.fixture
def restore_platform(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> Generator[None]:
    yield
    client.patch(
        f"{API}/config/groups/branding",
        headers=superuser_token_headers,
        json={
            "values": {
                "app_name": None,
                "footer_copyright": None,
                "logo": None,
                "primary_color": None,
            }
        },
    )


def _item(groups: list[dict], group: str, code: str) -> dict:  # type: ignore[type-arg]
    g = next(g for g in groups if g["code"] == group)
    return next(i for i in g["items"] if i["code"] == code)


@pytest.mark.usefixtures("restore_platform")
def test_platform_config_read_update_validate(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    h = superuser_token_headers
    groups = client.get(f"{API}/config/groups", headers=h).json()["data"]
    assert [g["code"] for g in groups][:2] == ["branding", "security"]
    name = _item(groups, "branding", "app_name")
    assert (
        name["value"] == "FastAPI Admin"
        and name["is_public"]
        and name["tenant_overridable"]
    )
    assert not _item(groups, "security", "allow_signup")["tenant_overridable"]

    r = client.patch(
        f"{API}/config/groups/branding",
        headers=h,
        json={"values": {"app_name": "Acme", "primary_color": "#ff0000"}},
    )
    assert (
        r.status_code == 200
        and _item([r.json()], "branding", "app_name")["value"] == "Acme"
    )
    # every type is validated; all-or-nothing with one error per item
    bad = client.patch(
        f"{API}/config/groups/branding",
        headers=h,
        json={
            "values": {
                "app_name": "",
                "primary_color": "red",
                "support_url": "javascript:x",
                "nope": 1,
            }
        },
    )
    assert bad.status_code == 422 and len(bad.json()["detail"]) == 4
    assert (
        _item(
            client.get(f"{API}/config/groups", headers=h).json()["data"],
            "branding",
            "primary_color",
        )["value"]
        == "#ff0000"
    )
    sec = client.patch(
        f"{API}/config/groups/security",
        headers=h,
        json={
            "values": {
                "session_minutes": "x",
                "allow_signup": "yes",
                "password_policy": "nope",
                "extra": "{bad",
            }
        },
    )
    assert sec.status_code == 422 and len(sec.json()["detail"]) == 4
    ok = client.patch(
        f"{API}/config/groups/security",
        headers=h,
        json={
            "values": {
                "session_minutes": 60,
                "allow_signup": False,
                "password_policy": "strict",
                "extra": '{"a": 1}',
            }
        },
    )
    assert {i["code"]: i["value"] for i in ok.json()["items"]}["extra"] == {"a": 1}
    reset = client.patch(
        f"{API}/config/groups/security",
        headers=h,
        json={
            "values": dict.fromkeys(
                ("session_minutes", "allow_signup", "password_policy", "extra")
            )
        },
    )
    assert {i["code"]: i["value"] for i in reset.json()["items"]}[
        "allow_signup"
    ] is True  # back to default
    assert (
        client.patch(
            f"{API}/config/groups/nope", headers=h, json={"values": {}}
        ).status_code
        == 404
    )


def test_platform_config_requires_platform_permission(
    client: TestClient, db: Session
) -> None:
    h, _, _ = _owner(
        client, db
    )  # tenant owner: has tenant config:* but no platform role
    assert client.get(f"{API}/config/groups", headers=h).status_code == 403
    assert (
        client.patch(
            f"{API}/config/groups/branding",
            headers=h,
            json={"values": {"app_name": "x"}},
        ).status_code
        == 403
    )


@pytest.mark.usefixtures("restore_platform")
def test_tenant_overrides_inherit_and_reset(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    ha, ta, slug_a = _owner(client, db)
    hb, _, slug_b = _owner(client, db)
    client.patch(
        f"{API}/config/groups/branding",
        headers=superuser_token_headers,
        json={"values": {"app_name": "Platform"}},
    )

    cfg = client.get(f"{API}/tenants/current/config", headers=ha).json()["data"]
    assert [g["code"] for g in cfg] == ["branding"]  # only overridable groups
    it = _item(cfg, "branding", "app_name")
    assert (
        it["value"] == "Platform"
        and it["platform_value"] == "Platform"
        and it["overridden"] is False
    )

    r = client.patch(
        f"{API}/tenants/current/config/branding",
        headers=ha,
        json={"values": {"app_name": "Acme", "footer_copyright": "© Acme"}},
    )
    assert r.status_code == 200
    it = _item([r.json()], "branding", "app_name")
    assert (
        it["value"] == "Acme"
        and it["overridden"]
        and it["platform_value"] == "Platform"
    )
    # B unaffected; platform change still flows to B but not to A's override
    client.patch(
        f"{API}/config/groups/branding",
        headers=superuser_token_headers,
        json={"values": {"app_name": "Platform 2"}},
    )
    assert (
        _item(
            client.get(f"{API}/tenants/current/config", headers=hb).json()["data"],
            "branding",
            "app_name",
        )["value"]
        == "Platform 2"
    )
    assert (
        _item(
            client.get(f"{API}/tenants/current/config", headers=ha).json()["data"],
            "branding",
            "app_name",
        )["value"]
        == "Acme"
    )
    # tenants cannot touch platform-only items
    assert (
        client.patch(
            f"{API}/tenants/current/config/security",
            headers=ha,
            json={"values": {"allow_signup": False}},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{API}/tenants/current/config/branding",
            headers=ha,
            json={"values": {"primary_color": "nope"}},
        ).status_code
        == 422
    )

    # public endpoint: per-tenant effective branding; unknown slug -> platform
    pa = client.get(f"{API}/config/public", params={"tenant": slug_a}).json()[
        "branding"
    ]
    assert pa["app_name"] == "Acme" and pa["footer_copyright"] == "© Acme"
    assert (
        client.get(f"{API}/config/public", params={"tenant": slug_b}).json()[
            "branding"
        ]["app_name"]
        == "Platform 2"
    )
    assert (
        client.get(f"{API}/config/public", params={"tenant": "no-such-tenant"}).json()[
            "branding"
        ]["app_name"]
        == "Platform 2"
    )
    pub = client.get(f"{API}/config/public").json()
    assert "security" not in pub and "app_name" in pub["branding"]

    # reset single item -> inherits again
    r = client.delete(f"{API}/tenants/current/config/branding/app_name", headers=ha)
    it = _item([r.json()], "branding", "app_name")
    assert it["overridden"] is False and it["value"] == "Platform 2"
    assert _item([r.json()], "branding", "footer_copyright")["overridden"] is True

    # overrides are RLS-protected: unfiltered SQL only sees the current tenant's rows
    with Session(engine) as s:
        assert (
            s.execute(text("SELECT count(*) FROM tenantconfigvalue")).scalar_one() == 0
        )
        set_tenant(s, uuid.UUID(ta))
        assert (
            s.execute(text("SELECT count(*) FROM tenantconfigvalue")).scalar_one() == 1
        )


def test_tenant_config_permissions(client: TestClient, db: Session) -> None:
    ho, tid, _ = _owner(client, db)
    email, pw = random_email(), random_lower_string()
    crud.create_user(session=db, user_create=UserCreate(email=email, password=pw))
    client.post(
        f"{API}/tenants/{tid}/members",
        headers=ho,
        json={"email": email, "roles": ["member"]},
    )
    tok = client.post(
        f"{API}/login/access-token", data={"username": email, "password": pw}
    ).json()["access_token"]
    hm = {"Authorization": f"Bearer {tok}", "X-Tenant-ID": tid}
    assert (
        client.get(f"{API}/tenants/current/config", headers=hm).status_code == 403
    )  # member
    client.put(
        f"{API}/tenants/{tid}/members/{crud.get_user_by_email(session=db, email=email).id}/roles",
        headers=ho,
        json={"roles": ["admin"]},
    )  # type: ignore[union-attr]
    assert client.get(f"{API}/tenants/current/config", headers=hm).status_code == 200
    assert (
        client.patch(
            f"{API}/tenants/current/config/branding",
            headers=hm,
            json={"values": {"app_name": "By admin"}},
        ).status_code
        == 200
    )


@pytest.mark.usefixtures("restore_platform")
def test_upload_ownership_and_serving(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    ha, _, slug_a = _owner(client, db)
    hb, _, _ = _owner(client, db)
    r = client.post(
        f"{API}/files/upload",
        headers=ha,
        files={"file": ("logo.png", PNG, "image/png")},
    )
    assert r.status_code == 200, r.text
    up = r.json()
    assert (
        up["url"] == f"{API}/files/{up['id']}"
        and up["size"] == len(PNG)
        and up["tenant_id"]
    )
    got = client.get(up["url"])  # public, for the sign-in page
    assert (
        got.status_code == 200
        and got.content == PNG
        and got.headers["content-type"] == "image/png"
    )
    assert "sandbox" in got.headers["content-security-policy"]

    assert (
        client.patch(
            f"{API}/tenants/current/config/branding",
            headers=ha,
            json={"values": {"logo": up["url"]}},
        ).status_code
        == 200
    )
    assert (
        client.get(f"{API}/config/public", params={"tenant": slug_a}).json()[
            "branding"
        ]["logo"]
        == up["url"]
    )
    # another tenant cannot use A's file, nor can the platform defaults
    assert (
        client.patch(
            f"{API}/tenants/current/config/branding",
            headers=hb,
            json={"values": {"logo": up["url"]}},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"{API}/config/groups/branding",
            headers=superuser_token_headers,
            json={"values": {"logo": up["url"]}},
        ).status_code
        == 422
    )
    # platform-owned files are usable by the platform and by tenants
    p = client.post(
        f"{API}/files/upload",
        headers=superuser_token_headers,
        params={"scope": "platform"},
        files={"file": ("p.png", PNG, "image/png")},
    ).json()
    assert p["tenant_id"] is None
    assert (
        client.patch(
            f"{API}/config/groups/branding",
            headers=superuser_token_headers,
            json={"values": {"logo": p["url"]}},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"{API}/tenants/current/config/branding",
            headers=hb,
            json={"values": {"logo": p["url"]}},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"{API}/tenants/current/config/branding",
            headers=hb,
            json={"values": {"logo": f"{API}/files/{uuid.uuid4()}"}},
        ).status_code
        == 422
    )

    # type / size / auth / permission checks
    assert (
        client.post(
            f"{API}/files/upload",
            headers=ha,
            files={"file": ("x.txt", b"hi", "text/plain")},
        ).status_code
        == 415
    )
    big = b"0" * (settings.MAX_UPLOAD_BYTES + 1)
    assert (
        client.post(
            f"{API}/files/upload",
            headers=ha,
            files={"file": ("big.png", big, "image/png")},
        ).status_code
        == 413
    )
    assert (
        client.post(
            f"{API}/files/upload", files={"file": ("a.png", PNG, "image/png")}
        ).status_code
        == 401
    )
    assert (
        client.post(
            f"{API}/files/upload",
            headers=ha,
            params={"scope": "platform"},
            files={"file": ("a.png", PNG, "image/png")},
        ).status_code
        == 403
    )
    assert client.get(f"{API}/files/{uuid.uuid4()}").status_code == 404
