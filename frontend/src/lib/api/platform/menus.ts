/** 后端驱动的菜单接口。 */
import { del, get, patch, post, type ListQuery } from '../request'
import type { Menu, MenuSpace, Message, MyMenus, Paged } from '../types'

/** 当前用户的菜单树与权限。 */
export const myMenusApi = {
  myMenus: (space: MenuSpace = 'workspace') =>
    get<MyMenus>('/menus/me', space === 'platform' ? { space } : undefined),
}

/** 菜单管理接口。 */
export const menusApi = {
  list: (q: ListQuery) => get<Paged<Menu>>('/platform/menus/', q),
  create: (b: Partial<Menu>) => post<Menu>('/platform/menus/', b),
  update: (id: string, b: Partial<Menu>) =>
    patch<Menu>(`/platform/menus/${id}`, b),
  remove: (id: string) => del<Message>(`/platform/menus/${id}`),
}
