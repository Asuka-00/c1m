"""菜单 key 清单导出（FE-02 / F2）：脚本与 GET /menus/keys（仅超级用户）。"""

import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.platform.menus.layout import MERGED
from app.platform.menus.models import Menu
from app.platform.menus.service import menu_keys
from app.scripts import export_menu_keys

URL = f"{settings.API_V1_STR}/menus/keys"


def test_menu_keys_cover_seeded_menus(db: Session) -> None:
    d = menu_keys()
    items = d["items"]
    assert isinstance(items, list) and d["count"] == len(items)
    keys = [r["key"] for r in items]
    assert len(keys) == len(set(keys))  # key 全局唯一
    seeded = {m.key for m in db.exec(select(Menu)) if not m.key.startswith("custom")}
    assert seeded <= set(keys)
    for r in items:
        assert r["i18n_key"] == f"menu.{r['key']}"
        assert all(r["titles"].values()), r["key"]
        assert r["space"] in ("workspace", "platform")
        if r["kind"] == "group":
            assert r["path"] is None
        else:
            assert r["path"] and r["path"].startswith("/"), r["key"]
    tabs = {r["key"]: r for r in items if r["kind"] == "tab"}
    for mk, (path, _i, _v, ts) in MERGED.items():
        for t in ts:
            assert tabs[t]["parent"] == mk and tabs[t]["path"] == path


def test_export_script(tmp_path: Path) -> None:
    out = tmp_path / "menu-keys.json"
    assert export_menu_keys.main(["--out", str(out)]) == 0
    assert json.loads(out.read_text()) == json.loads(json.dumps(menu_keys()))
    assert export_menu_keys.main(["--check", str(out)]) == 0
    out.write_text("{}")
    assert export_menu_keys.main(["--check", str(out)]) == 1
    r = subprocess.run(
        [sys.executable, "-m", "app.scripts.export_menu_keys"],
        cwd=Path(__file__).resolve().parents[4],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(r.stdout)["count"] == menu_keys()["count"]


def test_menu_keys_endpoint_superuser_only(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
) -> None:
    r = client.get(URL, headers=superuser_token_headers)
    assert r.status_code == 200, r.text
    assert r.json() == json.loads(json.dumps(menu_keys()))
    assert client.get(URL, headers=normal_user_token_headers).status_code == 403
    assert client.get(URL).status_code == 401
