import { http } from './client'
import type { ListQuery } from './index'
import type { Paged } from './types'

export type MesFieldType =
  | 'str'
  | 'text'
  | 'int'
  | 'float'
  | 'bool'
  | 'enum'
  | 'ref'
  | 'date'
  | 'time'
  | 'json'

export interface MesField {
  name: string
  /** API/DB column (`<name>_id` for refs) */
  column: string
  type: MesFieldType
  required: boolean
  enum: string | null
  ref: string | null
  list: boolean
  filter: boolean
  search: boolean
  default: unknown
  max_length: number | null
  help: boolean
}

export interface MesEntity {
  code: string
  module: string
  url: string
  has_code: boolean
  tree: boolean
  versioned: boolean
  readonly: boolean
  parent: string | null
  children: string[]
  label_field: string
  sort_default: string
  natural_key: string[]
  read: string
  write: string
  can_read: boolean
  can_write: boolean
  fields: MesField[]
}

export interface MesMeta {
  modules: { code: string; order: number }[]
  entities: MesEntity[]
  enums: Record<string, string[]>
}

export type MesRow = Record<string, unknown> & {
  id: string
  code?: string
  name?: string
  status?: string
  version?: number
  attrs?: Record<string, unknown> | null
}
export type MesTreeNode = MesRow & { children: MesTreeNode[] }

export interface MesAttrDef {
  code: string
  name: string
  data_type: 'string' | 'number' | 'boolean' | 'date' | 'select'
  required: boolean
  options: string[]
}

const seg = (code: string) => code.replace(/_/g, '-')
const base = (code: string) => `/mes/${seg(code)}`

/** Generic MES master-data client (/mes/<entity>). */
export const mesApi = {
  meta: () => http.get<MesMeta>('/mes/_meta').then((r) => r.data),
  attrs: (code: string) =>
    http.get<MesAttrDef[]>(`/mes/_attrs/${code}`).then((r) => r.data),
  list: (code: string, params?: ListQuery) =>
    http.get<Paged<MesRow>>(base(code), { params }).then((r) => r.data),
  tree: (code: string) =>
    http.get<MesTreeNode[]>(`${base(code)}/tree`).then((r) => r.data),
  get: (code: string, id: string) =>
    http.get<MesRow>(`${base(code)}/${id}`).then((r) => r.data),
  create: (code: string, body: Record<string, unknown>) =>
    http.post<MesRow>(base(code), body).then((r) => r.data),
  update: (code: string, id: string, body: Record<string, unknown>) =>
    http.patch<MesRow>(`${base(code)}/${id}`, body).then((r) => r.data),
  remove: (code: string, id: string) =>
    http.delete(`${base(code)}/${id}`).then((r) => r.data),
  setStatus: (code: string, id: string, status: string) =>
    http
      .post<MesRow>(`${base(code)}/${id}/status`, { status })
      .then((r) => r.data),
  newVersion: (code: string, id: string) =>
    http.post<MesRow>(`${base(code)}/${id}/new-version`).then((r) => r.data),
  exportXlsx: async (code: string) => {
    const r = await http.get<Blob>(`${base(code)}/export`, {
      responseType: 'blob',
    })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(r.data)
    a.download = `${code}.xlsx`
    a.click()
    URL.revokeObjectURL(a.href)
  },
  importXlsx: (code: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return http
      .post<{ created: number; updated: number }>(`${base(code)}/import`, fd)
      .then((r) => r.data)
  },
  convert: (from_uom: string, to_uom: string, value: number) =>
    http
      .get<{ value: number; path: string[] }>('/mes/_convert', {
        params: { from_uom, to_uom, value },
      })
      .then((r) => r.data),
  codePreview: (id: string, count = 3, context?: Record<string, unknown>) =>
    http
      .post<{ codes: string[] }>(`/mes/code-rule/${id}/preview`, {
        count,
        context,
      })
      .then((r) => r.data),
}
