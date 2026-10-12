/** Backend-driven menus. */
import { del, get, patch, post, type ListQuery } from '../request'
import type { Menu, Message, MyMenus, Paged } from '../types'

export const myMenusApi = {
  myMenus: () => get<MyMenus>('/menus/me'),
}

export const menusApi = {
  list: (q: ListQuery) => get<Paged<Menu>>('/menus/', q),
  create: (b: Partial<Menu>) => post<Menu>('/menus/', b),
  update: (id: string, b: Partial<Menu>) => patch<Menu>(`/menus/${id}`, b),
  remove: (id: string) => del<Message>(`/menus/${id}`),
}
