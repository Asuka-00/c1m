/** 后端驱动的菜单接口。 */
import { del, get, patch, post, type ListQuery } from '../request'
import type { Menu, Message, MyMenus, Paged } from '../types'

/** 当前用户的菜单树与权限。 */
export const myMenusApi = {
  myMenus: () => get<MyMenus>('/menus/me'),
}

/** 菜单管理接口。 */
export const menusApi = {
  list: (q: ListQuery) => get<Paged<Menu>>('/menus/', q),
  create: (b: Partial<Menu>) => post<Menu>('/menus/', b),
  update: (id: string, b: Partial<Menu>) => patch<Menu>(`/menus/${id}`, b),
  remove: (id: string) => del<Message>(`/menus/${id}`),
}
