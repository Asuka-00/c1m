"""菜单接口：当前用户菜单树与菜单管理。"""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import select

from app.core.deps import SessionDep
from app.core.models import Message
from app.core.pagination import ListParamsDep, paginate
from app.platform.auth.deps import (
    CurrentUser,
    TokenPayloadDep,
    get_current_tenant,
    platform_api_router,
    require_permissions,
)
from app.platform.menus.layout import PLATFORM_REDIRECTS
from app.platform.menus.models import Menu
from app.platform.menus.schemas import (
    MenuCreate,
    MenuPublic,
    MenusPublic,
    MenuUpdate,
    MyMenus,
    PermNode,
)
from app.platform.menus.service import (
    build_tree,
    forbidden_paths,
    permission_tree,
    redirects,
)
from app.platform.rbac.service import user_permission_codes

router = APIRouter(prefix="/menus", tags=["menus"])
# 菜单管理（仅在平台空间 /platform/menus 下挂载）
admin_router = APIRouter(prefix="/menus", tags=["menus"])


@router.get("/me", response_model=MyMenus)
def my_menus(
    session: SessionDep,
    current_user: CurrentUser,
    token_data: TokenPayloadDep,
    x_tenant_id: Annotated[uuid.UUID | None, Header()] = None,
    space: Literal["workspace", "platform"] = "workspace",
) -> Any:
    """Menu/route tree filtered by the caller's effective permissions in the
    current tenant (X-Tenant-ID / `tid` claim / only membership). Without a
    resolvable tenant only platform permissions apply.

    `space=platform` returns the platform admin console menus (superusers only, 403 otherwise)."""
    if space == "platform":
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=403, detail="Platform console is for superusers only"
            )
        pmenus = list(session.exec(select(Menu).where(Menu.space == "platform")).all())
        ptree = build_tree(pmenus, set(), True)
        return MyMenus(
            menus=ptree,
            forbidden_paths=[],
            redirects={},
            permissions=sorted(user_permission_codes(current_user)),
            tenant_id=None,
            is_superuser=True,
            space="platform",
        )
    perms = user_permission_codes(current_user)
    tenant_id = None
    try:
        ctx = get_current_tenant(session, current_user, token_data, x_tenant_id)
        perms, tenant_id = ctx.permissions, ctx.id
    except HTTPException as e:
        if e.status_code != 400:
            raise
    menus = list(session.exec(select(Menu).where(Menu.space == "workspace")).all())
    tree = build_tree(menus, perms, current_user.is_superuser)
    redir = redirects(tree)
    forbidden = forbidden_paths(menus, tree)
    if current_user.is_superuser:  # 旧平台页面路径 -> 平台管理控制台
        redir.update(PLATFORM_REDIRECTS)
    else:  # 平台页面（含旧路径）对非超级用户显示 403 而非 404
        ppaths = session.exec(select(Menu.path).where(Menu.space == "platform")).all()
        forbidden = sorted(
            set(forbidden)
            | set(PLATFORM_REDIRECTS)
            | {"/platform"}
            | {p for p in ppaths if p}
        )
    return MyMenus(
        menus=tree,
        forbidden_paths=forbidden,
        redirects=redir,
        permissions=sorted(perms),
        tenant_id=tenant_id,
        is_superuser=current_user.is_superuser,
    )


@admin_router.get(
    "/",
    dependencies=[Depends(require_permissions("roles:read"))],
    response_model=MenusPublic,
)
def list_menus(
    session: SessionDep,
    params: ListParamsDep,
    parent_id: uuid.UUID | None = None,
    hidden: bool | None = None,
    space: Literal["workspace", "platform"] | None = None,
) -> Any:
    """Paginated; sort_by: key, title, path, component, permission, sort_order; q: key/title/path;
    filters: parent_id (children of a group), hidden, space."""
    stmt = select(Menu)
    if space is not None:
        stmt = stmt.where(Menu.space == space)
    if parent_id is not None:
        stmt = stmt.where(Menu.parent_id == parent_id)
    if hidden is not None:
        stmt = stmt.where(Menu.hidden == hidden)
    data, count = paginate(
        session,
        stmt,
        params,
        {
            "key": Menu.key,
            "title": Menu.title,
            "path": Menu.path,
            "component": Menu.component,
            "permission": Menu.permission,
            "sort_order": Menu.sort_order,
        },
        ("sort_order", "asc"),
        Menu.id,
        search=[Menu.key, Menu.title, Menu.path],
    )
    return MenusPublic(data=data, count=count)


@admin_router.post(
    "/",
    dependencies=[Depends(require_permissions("roles:write"))],
    response_model=MenuPublic,
)
def create_menu(session: SessionDep, menu_in: MenuCreate) -> Any:
    if session.exec(select(Menu).where(Menu.key == menu_in.key)).first():
        raise HTTPException(status_code=409, detail="Menu key already exists")
    if menu_in.parent_id and not session.get(Menu, menu_in.parent_id):
        raise HTTPException(status_code=404, detail="Parent menu not found")
    menu = Menu.model_validate(menu_in)
    session.add(menu)
    session.commit()
    session.refresh(menu)
    return menu


@admin_router.patch(
    "/{id}",
    dependencies=[Depends(require_permissions("roles:write"))],
    response_model=MenuPublic,
)
def update_menu(session: SessionDep, id: uuid.UUID, menu_in: MenuUpdate) -> Any:
    menu = session.get(Menu, id)
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    data = menu_in.model_dump(exclude_unset=True)
    if data.get("parent_id") == id:
        raise HTTPException(status_code=400, detail="Menu cannot be its own parent")
    menu.sqlmodel_update(data)
    session.add(menu)
    session.commit()
    session.refresh(menu)
    return menu


@admin_router.delete(
    "/{id}",
    dependencies=[Depends(require_permissions("roles:write"))],
    response_model=Message,
)
def delete_menu(session: SessionDep, id: uuid.UUID) -> Any:
    menu = session.get(Menu, id)
    if not menu:
        raise HTTPException(status_code=404, detail="Menu not found")
    session.delete(menu)
    session.commit()
    return Message(message="Menu deleted successfully")


# 平台空间：/platform/menus/...（仅超级用户）与统一权限树
platform_router = platform_api_router(admin_router)


@platform_router.get("/permission-tree", response_model=list[PermNode])
def read_permission_tree(
    session: SessionDep,
    space: Literal["workspace", "platform", "all"] = "all",
    scope: Literal["platform", "tenant"] | None = None,
) -> Any:
    """Unified permission tree: menus (MENU) -> attached permissions (MENU / BUTTON).
    `space=all` returns both spaces; `scope` keeps only that permission scope."""
    spaces: list[str] = ["platform", "workspace"] if space == "all" else [space]
    return permission_tree(session, spaces, scope)
