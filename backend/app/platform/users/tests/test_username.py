"""Optional unique username; login with username OR email."""

from fastapi.testclient import TestClient

from app.core.config import settings
from app.testing.utils import random_email, random_lower_string

API = settings.API_V1_STR


def _login(client: TestClient, ident: str, pw: str) -> int:
    return client.post(
        f"{API}/login/access-token", data={"username": ident, "password": pw}
    ).status_code


def test_superuser_login_by_username_and_email(client: TestClient) -> None:
    pw = settings.FIRST_SUPERUSER_PASSWORD
    assert _login(client, settings.FIRST_SUPERUSER_USERNAME, pw) == 200
    assert _login(client, settings.FIRST_SUPERUSER_USERNAME.upper(), pw) == 200
    assert _login(client, settings.FIRST_SUPERUSER, pw) == 200
    r = client.post(
        f"{API}/login/access-token",
        data={"username": settings.FIRST_SUPERUSER_USERNAME, "password": "wrong-pw"},
    )
    assert r.status_code == 400


def test_username_create_unique_validate(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    h = superuser_token_headers
    name, pw = "U_" + random_lower_string()[:10], random_lower_string()
    r = client.post(
        f"{API}/platform/users/",
        headers=h,
        json={"email": random_email(), "username": name, "password": pw},
    )
    assert r.status_code == 200, r.text
    assert r.json()["username"] == name.lower()  # stored lower-case
    assert _login(client, name, pw) == 200
    dup = client.post(
        f"{API}/platform/users/",
        headers=h,
        json={"email": random_email(), "username": name.lower(), "password": pw},
    )
    assert dup.status_code == 409
    for bad in ("a@b", "x", "has space"):
        r = client.post(
            f"{API}/platform/users/",
            headers=h,
            json={"email": random_email(), "username": bad, "password": pw},
        )
        assert r.status_code == 422, bad
    uid = client.post(
        f"{API}/platform/users/",
        headers=h,
        json={"email": random_email(), "password": pw},
    ).json()["id"]
    assert (
        client.patch(
            f"{API}/platform/users/{uid}", headers=h, json={"username": name}
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"{API}/platform/users/{uid}", headers=h, json={"username": "other_" + name}
        ).status_code
        == 200
    )
