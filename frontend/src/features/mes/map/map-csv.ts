/**
 * 坐标图 CSV（cim-map-csv v1）解析与校验。
 *
 * 后端 B4（`POST /mes/map/import/preview`）上线前作为本地 mock 的预览实现；
 * 规则与约定一致：`#` 开头为文件头，数据列 `substrate_id,row,col,bin_code`，
 * 报错的 `row_no` 按数据行计（不含文件头和列名，从 1 开始），`file_line` 为原始文件行号。
 */

/** 逐行报错代码。 */
export type MapErrorCode =
  | 'bad_columns'
  | 'bad_number'
  | 'duplicate_coord'
  | 'unknown_bin'

/** 一条逐行报错。 */
export interface MapRowError {
  row_no: number
  file_line: number
  code: MapErrorCode
  /** 报错涉及的值（坐标或 bin 码），用于拼提示文字。 */
  value: string
}

/** 文件级错误（整份文件不能导入，不逐行列出）。 */
export type MapFileErrorCode =
  | 'missing_header'
  | 'bad_column_header'
  | 'unknown_bin_set'
  | 'empty'

/** 单片基板的汇总。 */
export interface SubstrateSummary {
  substrate_id: string
  rows: number
  cols: number
  cells: number
  /** 按 bin 类型计数（good / fail / edge）。 */
  by_type: Record<string, number>
}

/** 预览结果（与后端预览接口的返回结构对齐）。 */
export interface MapPreview {
  header: Record<string, string>
  bin_set: { name: string; version: string } | null
  total_rows: number
  errors: MapRowError[]
  file_error: MapFileErrorCode | null
  substrates: SubstrateSummary[]
}

/** bin 定义（一行）。 */
export interface BinDef {
  bin_code: string
  bin_type: string
  description: string
}

/** bin 定义集。 */
export interface BinSet {
  name: string
  version: string
  bins: BinDef[]
}

const MAP_COLUMNS = ['substrate_id', 'row', 'col', 'bin_code']
const REQUIRED_HEADER = [
  'origin_location',
  'x_axis',
  'y_axis',
  'bin_definition_set',
  'bin_definition_version',
]

/** 拆出文件头（`# key=value`）、列名和数据行，保留原始行号。 */
function split(text: string) {
  const header: Record<string, string> = {}
  const lines = text.replace(/^\uFEFF/, '').split(/\r?\n/)
  let columns: string[] | null = null
  const data: { line: number; cells: string[] }[] = []
  lines.forEach((raw, i) => {
    const line = raw.trim()
    if (!line) return
    if (line.startsWith('#')) {
      const m = /^#\s*([\w.]+)\s*=\s*(.*)$/.exec(line)
      if (m) header[m[1]] = m[2].trim()
      return
    }
    const cells = line.split(',').map((c) => c.trim())
    if (!columns) columns = cells
    else data.push({ line: i + 1, cells })
  })
  return { header, columns: columns as string[] | null, data }
}

/** 解析 bin 定义 CSV（cim-bin-csv v1）；定义集名称和版本取自它自己的文件头。 */
export function parseBinSet(text: string): BinSet {
  const { header, data } = split(text)
  return {
    name: header.bin_definition_set ?? '',
    version: header.version ?? '',
    bins: data.map(({ cells: [bin_code, bin_type, description] }) => ({
      bin_code,
      bin_type,
      description: description ?? '',
    })),
  }
}

/**
 * 校验坐标图 CSV。
 *
 * @param text 文件内容
 * @param binSets 已有的 bin 定义集；按文件头 `bin_definition_set` + `bin_definition_version` 查找
 */
export function previewMap(text: string, binSets: BinSet[]): MapPreview {
  const { header, columns, data } = split(text)
  const base: MapPreview = {
    header,
    bin_set: null,
    total_rows: data.length,
    errors: [],
    file_error: null,
    substrates: [],
  }
  if (!columns && !data.length) return { ...base, file_error: 'empty' }
  if (REQUIRED_HEADER.some((k) => !header[k]))
    return { ...base, file_error: 'missing_header' }
  if (columns?.join(',') !== MAP_COLUMNS.join(','))
    return { ...base, file_error: 'bad_column_header' }
  const set = binSets.find(
    (s) =>
      s.name === header.bin_definition_set &&
      s.version === header.bin_definition_version
  )
  if (!set) return { ...base, file_error: 'unknown_bin_set' }
  const typeOf = new Map(set.bins.map((b) => [b.bin_code, b.bin_type]))
  const errors: MapRowError[] = []
  const seen = new Set<string>()
  const subs = new Map<string, SubstrateSummary>()
  data.forEach(({ line, cells }, i) => {
    const row_no = i + 1
    const err = (code: MapErrorCode, value: string) =>
      errors.push({ row_no, file_line: line, code, value })
    if (cells.length !== MAP_COLUMNS.length)
      return err('bad_columns', cells.join(','))
    const [sid, r, c, bin] = cells
    const row = Number(r)
    const col = Number(c)
    if (!/^\d+$/.test(r) || !/^\d+$/.test(c))
      return err('bad_number', `${r},${c}`)
    const key = `${sid}|${row}|${col}`
    if (seen.has(key)) return err('duplicate_coord', `${sid} (${row},${col})`)
    seen.add(key)
    const type = typeOf.get(bin)
    if (!type) return err('unknown_bin', bin)
    const s = subs.get(sid) ?? {
      substrate_id: sid,
      rows: 0,
      cols: 0,
      cells: 0,
      by_type: {},
    }
    s.rows = Math.max(s.rows, row + 1)
    s.cols = Math.max(s.cols, col + 1)
    s.cells += 1
    s.by_type[type] = (s.by_type[type] ?? 0) + 1
    subs.set(sid, s)
  })
  return {
    ...base,
    bin_set: { name: set.name, version: set.version },
    errors,
    substrates: [...subs.values()],
  }
}
