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
  /** 仅在条件必填满足时显示于表单 */
  only_when_required?: boolean
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
  /** 定点小数位数（numeric(18, scale)）；元数据不带时 float 按 6 位（D60） */
  scale?: number | null
  help: boolean
  /** 引用选项按该同级引用字段过滤（如 route） */
  depends: string | null
  /** 引用选项的固定筛选（如只列待入库批次） */
  ref_filter?: Record<string, string> | null
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
  /** 预警天数（operator_qual 等实体元数据下发，可缺省） */
  warn_days?: number | null
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
  /** 文本型筛选字段的去重取值（下拉筛选选项）。 */
  distinct: (code: string, field: string, q?: string) =>
    http
      .get<{ data: string[] }>(`${base(code)}/distinct/${field}`, {
        params: { q: q || undefined },
      })
      .then((r) => r.data.data),
  /** 导出 xlsx；传入列表查询参数时按当前关键字 / 筛选导出（忽略分页）。 */
  exportXlsx: async (code: string, query: Record<string, unknown> = {}) => {
    const { page: _p, page_size: _s, ...params } = query
    const r = await http.get<Blob>(`${base(code)}/export`, {
      responseType: 'blob',
      params,
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
  /** 单位换算：数量按十进制字符串传，返回值为定点字符串（D50，2d65b94；也兼容数字）。 */
  convert: (from_uom: string, to_uom: string, value: string) =>
    http
      .get<{ value: number | string; path: string[] }>('/mes/_convert', {
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
