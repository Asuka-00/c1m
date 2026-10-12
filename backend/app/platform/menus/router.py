"""菜单接口：当前用户菜单树与菜单管理。"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import select

from app.core.deps import SessionDep
from app.core.models import Message
from app.core.pagination import ListParamsDep, paginate
from app.platform.auth.deps import (
    CurrentUser,
    TokenPayloadDep,
    get_current_tenant,
    require_permissions,
)
from app.platform.menus.models import Menu
from app.platform.menus.schemas import (
    MenuCreate,
    MenuPublic,
    MenusPublic,
    MenuUpdate,
    MyMenus,
)
from app.platform.menus.service import build_tree, forbidden_paths
from app.platform.rbac.service import user_permission_codes

router = APIRouter(prefix="/menus", tags=["menus"])


@router.get("/me", response_model=MyMenus)
def my_menus(
    session: SessionDep,
    current_user: CurrentUser,
    token_data: TokenPayloadDep,
    x_tenant_id: Annotated[uuid.UUID | None, Header()] = None,
) -> Any:
    """Menu/route tree filtered by the caller's effective permissions in the
    current tenant (X-Tenant-ID / `tid` claim / only membership). Without a
    resolvable tenant only platform permissions apply."""
    perms = user_permission_codes(current_user)
    tenant_id = None
    try:
        ctx = get_current_tenant(session, current_user, token_data, x_tenant_id)
        perms, tenant_id = ctx.permissions, ctx.id
    except HTTPException as e:
        if e.status_code != 400:
            raise
    menus = list(session.exec(select(Menu)).all())
    tree = build_tree(menus, perms, current_user.is_superuser)
    return MyMenus(
        menus=tree,
        forbidden_paths=forbidden_paths(menus, tree),
        permissions=sorted(perms),
        tenant_id=tenant_id,
        is_superuser=current_user.is_superuser,
    )


@router.get(
    "/",
    dependencies=[Depends(require_permissions("roles:read"))],
    response_model=MenusPublic,
)
def list_menus(
    session: SessionDep,
    params: ListParamsDep,
    parent_id: uuid.UUID | None = None,
    hidden: bool | None = None,
) -> Any:
    """Paginated; sort_by: key, title, path, component, permission, sort_order; q: key/title/path;
    filters: parent_id (children of a group), hidden."""
    stmt = select(Menu)
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


@router.post(
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


@router.patch(
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


@router.delete(
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
