/** MES 规格驱动的主数据：实体元数据 + 通用 CRUD 客户端（/mes/<entity>）。 */
import { http } from '../client'
import type { ListQuery } from '../request'
import type { Paged } from '../types'

/** MES 字段类型（与后端规格引擎一致）。 */
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
  | 'datetime'
  | 'json'

/** MES 字段元数据。 */
export interface MesField {
  name: string
  /** API / 数据库列名（引用字段为 `<name>_id`） */
  column: string
  type: MesFieldType
  required: boolean
  /** 条件必填：{同级字段名: 取值}；'*' 表示任意值 */
  required_when: Record<string, unknown[]> | null
  /** 为空时后端复制该同级字段（如 code） */
  default_from: string | null
  /** 为空时由后端生成 */
  auto?: boolean
  /** 仅由后端维护（不可编辑） */
  system?: boolean
  enum: string | null
  ref: string | null
  list: boolean
  filter: boolean
  search: boolean
  default: unknown
  max_length: number | null
  help: boolean
  /** 引用选项按该同级引用字段过滤（如 route） */
  depends: string | null
}

/** MES 实体元数据。 */
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

/** `GET /mes/_meta` 的返回：全部实体、枚举与当前用户的 MES 权限。 */
export interface MesMeta {
  modules: { code: string; order: number }[]
  entities: MesEntity[]
  enums: Record<string, string[]>
  /** 当前用户的额外 MES 权限（如 mes.wo:release） */
  perms: string[]
}

/** MES 实体行（列名 -> 值，引用字段附带 `<name>` 显示标签）。 */
export type MesRow = Record<string, unknown> & {
  id: string
  code?: string
  name?: string
  status?: string
  version?: number
  attrs?: Record<string, unknown> | null
}
/** 树形实体节点（含 children）。 */
export type MesTreeNode = MesRow & { children: MesTreeNode[] }

/** 租户自定义属性定义。 */
export interface MesAttrDef {
  code: string
  name: string
  data_type: 'string' | 'number' | 'boolean' | 'date' | 'select'
  required: boolean
  options: string[]
}

const seg = (code: string) => code.replace(/_/g, '-')
const base = (code: string) => `/mes/${seg(code)}`

/** 通用 MES 主数据客户端（/mes/<entity>）。 */
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
