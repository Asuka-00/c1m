/**
 * 坐标图 / bin 定义集接口（P1 / B4，已接真实后端）。
 *
 * - `POST /mes/map/import/preview`、`POST /mes/map/import`：坐标图 CSV（`mes.map:import`）
 * - `POST /mes/map/bin-sets/import/preview`、`POST /mes/map/bin-sets/import`：bin 定义集 CSV
 * - `GET /mes/map/substrates/{code}?version=`：按基板查询（`mes.map:read`）
 *
 * 请求体严格（多余字段 422）：只传 `content`、`file_name`，坐标图可选 `lot_id` / `equipment_id` / `operation_id`。
 * 时间字段为带 Z 的 UTC，显示时用 `fmtDateTime` 转本地时区。
 */
import { AxiosError } from 'axios'
import { http } from '../client'

/** 坐标图请求体上限（后端 D39：超过 413 payload_too_large）。 */
export const MAP_MAX_BYTES = 10 * 1024 * 1024

/** 一条逐行报错；文件级错误的 `row_no` / `file_line` 为 null。`row_no` 按数据行从 1 开始。 */
export interface MapRowError {
  row_no: number | null
  file_line: number | null
  field: string | null
  code: string
  message: string
}

/** 坐标图预览里单片基板的汇总。 */
export interface PreviewSubstrate {
  code: string
  rows: number
  cols: number
  total_qty: number
  bin_counts: Record<string, number>
  good_qty: number
  excluded_qty: number
  /** 导入后将得到的版本号。 */
  map_version: number
}

export interface MapPreview {
  ok: boolean
  header: Record<string, string>
  bin_set_id: string | null
  substrates: PreviewSubstrate[]
  errors: MapRowError[]
}

export interface BinDefinition {
  bin_code: string
  bin_type: string
  description: string | null
}

export interface BinSetPreview {
  ok: boolean
  bin_set: { code: string; version: number } | null
  definitions: BinDefinition[]
  excluded_bin_codes: string[]
  errors: MapRowError[]
}

export interface BinSet {
  id: string
  code: string
  version: number
  created_at: string
  definitions: BinDefinition[]
}

/** 一个基板的一版坐标图。 */
export interface SubstrateMap {
  id: string
  code: string
  substrate_type: string
  map_version: number
  rows: number
  cols: number
  origin_location: string
  x_axis: string
  y_axis: string
  total_qty: number
  good_qty: number
  excluded_qty: number
  bin_counts: Record<string, number>
  lot_id: string | null
  lot_label: string | null
  operation_label: string | null
  equipment_label: string | null
  bin_set_label: string | null
  created_at: string
}

/** 按基板查询的结果：带格子和全部版本号。 */
export interface SubstrateMapDetail extends SubstrateMap {
  bin_set_code: string
  bin_set_version: number
  cells: { row: number; col: number; bin_code: string }[]
  versions: number[]
}

export interface MapImportResult {
  import_id: string
  data: SubstrateMap[]
}

export interface ImportBody {
  content: string
  file_name?: string
}

export interface MapImportBody extends ImportBody {
  lot_id?: string
  equipment_id?: string
  operation_id?: string
}

/** 接口错误归类，页面据此给提示。 */
export type MapApiError =
  | { kind: 'rows'; code: string; errors: MapRowError[] }
  | { kind: 'conflict' }
  | { kind: 'too_large' }
  | { kind: 'forbidden' }
  | { kind: 'not_found' }
  | { kind: 'fields'; fields: { field: string; msg: string }[] }
  | { kind: 'other'; message: string }

/** 把 axios 错误转成 {@link MapApiError}。 */
export function mapApiError(e: unknown): MapApiError {
  if (!(e instanceof AxiosError) || !e.response)
    return { kind: 'other', message: e instanceof Error ? e.message : '' }
  const { status } = e.response
  const detail = (e.response.data as { detail?: unknown } | undefined)?.detail
  if (status === 403) return { kind: 'forbidden' }
  if (status === 404) return { kind: 'not_found' }
  if (status === 413) return { kind: 'too_large' }
  if (status === 409) return { kind: 'conflict' }
  if (Array.isArray(detail))
    return {
      kind: 'fields',
      fields: detail.map((d: { loc?: unknown[]; msg?: string }) => ({
        field: (d.loc ?? []).filter((x) => x !== 'body').join('.'),
        msg: d.msg ?? '',
      })),
    }
  if (detail && typeof detail === 'object' && 'code' in detail) {
    const d = detail as { code: string; errors?: MapRowError[] }
    return { kind: 'rows', code: d.code, errors: d.errors ?? [] }
  }
  return {
    kind: 'other',
    message: typeof detail === 'string' ? detail : e.message,
  }
}

/** 文件读成请求体；超过 10MB 直接拒绝（后端也会 413）。 */
export async function fileBody(file: File): Promise<ImportBody> {
  if (file.size > MAP_MAX_BYTES) {
    const e = new AxiosError('payload too large')
    e.response = {
      status: 413,
      data: { detail: { code: 'payload_too_large' } },
      statusText: '',
      headers: {},
      config: e.config as never,
    }
    throw e
  }
  return { content: await file.text(), file_name: file.name }
}

export const mapApi = {
  /** 坐标图预览：成功 200 时 `ok` 表示能否导入，`errors` 逐行列出。 */
  preview: async (body: MapImportBody): Promise<MapPreview> =>
    (await http.post('/mes/map/import/preview', body)).data,
  /** 坐标图导入：同一基板再导入生成新版本；有错 422 map_invalid，并发 409。 */
  commit: async (body: MapImportBody): Promise<MapImportResult> =>
    (await http.post('/mes/map/import', body)).data,
  binSetPreview: async (body: ImportBody): Promise<BinSetPreview> =>
    (await http.post('/mes/map/bin-sets/import/preview', body)).data,
  binSetCommit: async (body: ImportBody): Promise<BinSet> =>
    (await http.post('/mes/map/bin-sets/import', body)).data,
  /** 按基板编号查坐标图，默认最新版本。 */
  bySubstrate: async (
    code: string,
    version?: number
  ): Promise<SubstrateMapDetail> =>
    (
      await http.get(`/mes/map/substrates/${encodeURIComponent(code)}`, {
        params: version ? { version } : undefined,
      })
    ).data,
}
