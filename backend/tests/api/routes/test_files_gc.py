"""Orphan upload cleanup: on replace/remove/reset and by the periodic sweep."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.platform.files.models import UploadedFile
from app.platform.files.service import cleanup_unreferenced, upload_dir
from tests.api.routes.test_config import PNG, _owner

API = settings.API_V1_STR


def _up(client: TestClient, h: dict[str, str], scope: str = "tenant") -> dict:  # type: ignore[type-arg]
    r = client.post(
        f"{API}/files/upload",
        headers=h,
        params={"scope": scope},
        files={"file": ("l.png", PNG, "image/png")},
    )
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def _exists(db: Session, fid: str) -> bool:
    db.expire_all()
    f = db.get(UploadedFile, uuid.UUID(fid))
    on_disk = f is not None and (upload_dir() / f.stored_name).is_file()
    return f is not None and on_disk


def _logo(client: TestClient, h: dict[str, str], value: str | None) -> None:
    r = client.patch(
        f"{API}/tenants/current/config/branding",
        headers=h,
        json={"values": {"logo": value}},
    )
    assert r.status_code == 200, r.text


def test_tenant_replace_remove_reset_deletes_old_file(
    client: TestClient, db: Session
) -> None:
    h, _, _ = _owner(client, db)
    f1, f2, f3 = _up(client, h), _up(client, h), _up(client, h)
    _logo(client, h, f1["url"])
    # same file used twice in the tenant: replacing one use keeps it
    client.patch(
        f"{API}/tenants/current/config/branding",
        headers=h,
        json={"values": {"favicon": f1["url"]}},
    )
    _logo(client, h, f2["url"])  # replace
    assert _exists(db, f1["id"]) and _exists(db, f2["id"])
    _logo(client, h, "")  # remove f2
    assert not _exists(db, f2["id"])
    assert client.get(f2["url"]).status_code == 404
    client.delete(f"{API}/tenants/current/config/branding/favicon", headers=h)  # reset
    assert not _exists(db, f1["id"])
    assert _exists(db, f3["id"])  # never referenced: only the sweep removes it


def test_platform_file_kept_while_any_tenant_uses_it(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    su = superuser_token_headers
    hb, _, _ = _owner(client, db)
    p = _up(client, su, "platform")
    client.patch(
        f"{API}/config/groups/branding", headers=su, json={"values": {"logo": p["url"]}}
    )
    _logo(client, hb, p["url"])
    client.patch(
        f"{API}/config/groups/branding", headers=su, json={"values": {"logo": None}}
    )
    assert _exists(db, p["id"])  # tenant B still references it
    client.delete(f"{API}/tenants/current/config/branding/logo", headers=hb)
    assert not _exists(db, p["id"])


def test_cleanup_respects_grace_and_references(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    ha, ta, _ = _owner(client, db)
    hb, _, _ = _owner(client, db)
    old_orphan, used, fresh = _up(client, ha), _up(client, ha), _up(client, ha)
    other_tenant_orphan = _up(client, hb)
    _logo(client, ha, used["url"])
    past = datetime.now(UTC) - timedelta(hours=48)
    for f in (old_orphan, used, other_tenant_orphan):
        rec = db.get(UploadedFile, uuid.UUID(f["id"]))
        assert rec
        rec.created_at = past
        db.add(rec)
    db.commit()

    # tenant-scoped sweep (script path) only touches that tenant's files
    dry = cleanup_unreferenced(db, tenant_id=uuid.UUID(ta), dry_run=True)
    assert {str(f.id) for f in dry} == {old_orphan["id"]}
    assert _exists(db, old_orphan["id"])

    hm = {k: v for k, v in ha.items() if k != "X-Tenant-ID"}
    assert client.post(f"{API}/files/cleanup", headers=hm).status_code == 403
    r = client.post(f"{API}/files/cleanup", headers=superuser_token_headers)
    assert r.status_code == 200 and r.json()["message"].startswith("Deleted")
    assert not _exists(db, old_orphan["id"])
    assert not _exists(db, other_tenant_orphan["id"])
    assert _exists(db, used["id"]) and _exists(db, fresh["id"])
    assert (
        client.post(
            f"{API}/files/cleanup",
            headers=superuser_token_headers,
            params={"older_than_hours": 0},
        ).status_code
        == 422
    )
