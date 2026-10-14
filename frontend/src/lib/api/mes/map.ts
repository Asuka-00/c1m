/**
 * 坐标图接口（P1 / B4）：导入预览、提交导入、按基板查询。
 *
 * 后端 B4 上线前 `MAP_MOCK = true`，用本地解析（`features/mes/map/map-csv`）和内存数据模拟；
 * 接口路径与权限码按群里约定：`POST /mes/map/import/preview`、`POST /mes/map/import`
 * （`mes.map:import`），`GET /mes/map/by-substrate/{id}`（`mes.map:read`）。
 */
import binDemo from '@/features/mes/map/__fixtures__/bin_definition_demo.csv?raw'
import {
  parseBinSet,
  previewMap,
  type MapPreview,
} from '@/features/mes/map/map-csv'
import { http } from '../client'

export type { MapPreview, MapRowError } from '@/features/mes/map/map-csv'

/** 后端 B4 接好后改为 false。 */
export const MAP_MOCK = true

/** 一次导入后的基板坐标图（某个版本）。 */
export interface SubstrateMap {
  id: string
  substrate_id: string
  version: number
  rows: number
  cols: number
  cells: number
  by_type: Record<string, number>
  origin_location: string
  x_axis: string
  y_axis: string
  bin_set: string
  bin_set_version: string
  file_name: string
  imported_at: string
}

const mockSets = [parseBinSet(binDemo)]
const mockMaps: SubstrateMap[] = []

/** 模拟提交：同一基板再导入生成新版本，旧版本保留。 */
function mockCommit(text: string, fileName: string): SubstrateMap[] {
  const p = previewMap(text, mockSets)
  if (p.file_error || p.errors.length) throw new Error('preview has errors')
  const now = new Date().toISOString()
  const created = p.substrates.map((s) => {
    const version =
      Math.max(
        0,
        ...mockMaps
          .filter((m) => m.substrate_id === s.substrate_id)
          .map((m) => m.version)
      ) + 1
    return {
      ...s,
      id: `${s.substrate_id}@${version}`,
      version,
      origin_location: p.header.origin_location,
      x_axis: p.header.x_axis,
      y_axis: p.header.y_axis,
      bin_set: p.bin_set!.name,
      bin_set_version: p.bin_set!.version,
      file_name: fileName,
      imported_at: now,
    }
  })
  mockMaps.push(...created)
  return created
}

const form = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return fd
}

export const mapApi = {
  /** 预览：逐行报错（`row_no` 按数据行，`file_line` 为原始行号）与按基板汇总。 */
  preview: async (file: File): Promise<MapPreview> =>
    MAP_MOCK
      ? previewMap(await file.text(), mockSets)
      : (await http.post('/mes/map/import/preview', form(file))).data,
  /** 提交导入；返回新建的基板坐标图版本。 */
  commit: async (file: File): Promise<SubstrateMap[]> =>
    MAP_MOCK
      ? mockCommit(await file.text(), file.name)
      : (await http.post('/mes/map/import', form(file))).data,
  /** 已导入的坐标图（各基板各版本）。 */
  list: async (): Promise<SubstrateMap[]> =>
    MAP_MOCK ? [...mockMaps].reverse() : (await http.get('/mes/map')).data,
}
