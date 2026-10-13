"""RBAC 重构相关测试：权限树、用户角色设置、筛选与已移除的旧接口。"""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.testing.user import create_random_user
from app.testing.utils import random_lower_string

API = settings.API_V1_STR


def _walk(nodes):
    """深度遍历权限树节点。"""
    for n in nodes:
        yield n
        yield from _walk(n["children"])


def test_permission_tree(client: TestClient, superuser_token_headers: dict) -> None:
    """权限树包含 MENU 节点且已挂接按钮权限。"""
    r = client.get(f"{API}/platform/permission-tree", headers=superuser_token_headers)
    assert r.status_code == 200
    nodes = list(_walk(r.json()))
    assert any(n["type"] == "MENU" for n in nodes)
    assert any(n["type"] == "BUTTON" and n["code"] for n in nodes)


def test_set_user_roles_and_filters(
    client: TestClient, superuser_token_headers: dict, db: Session
) -> None:
    """设置用户角色后列表返回角色名与更新人，并支持按用户名筛选。"""
    h = superuser_token_headers
    code = f"r{random_lower_string()[:8]}"
    role = client.post(
        f"{API}/platform/roles/", headers=h, json={"name": code, "title": "测试角色"}
    ).json()
    user = create_random_user(db)
    r = client.put(
        f"{API}/platform/users/{user.id}/roles",
        headers=h,
        json={"role_ids": [role["id"]]},
    )
    assert r.status_code == 200
    rows = client.get(
        f"{API}/platform/users/", headers=h, params={"username": user.email}
    ).json()["data"]
    assert len(rows) == 1
    assert code in rows[0]["role_names"] or "测试角色" in rows[0]["role_names"]
    assert rows[0]["updated_by"]
    roles = client.get(
        f"{API}/platform/roles/", headers=h, params={"code": code, "status": "active"}
    ).json()["data"]
    assert [x["name"] for x in roles] == [code]


def test_removed_legacy_endpoints(
    client: TestClient, superuser_token_headers: dict
) -> None:
    """旧的兼容管理接口已删除。"""
    h = superuser_token_headers
    for path in ("/users/", "/roles/", "/permissions/", "/menus/", "/tenants/"):
        assert client.get(f"{API}{path}", headers=h).status_code in (404, 405), path
    assert client.get(f"{API}/menus/me", headers=h).status_code == 200
    assert client.get(f"{API}/users/me", headers=h).status_code == 200
