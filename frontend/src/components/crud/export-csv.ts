/** 单元格值转 CSV 字段（含逗号 / 引号 / 换行时加引号转义）。 */
export function csvCell(v: unknown): string {
  const s = v == null ? '' : String(v)
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

/** 生成 CSV 文本（首行表头）。 */
export function toCsv(head: string[], rows: unknown[][]): string {
  return [head, ...rows].map((r) => r.map(csvCell).join(',')).join('\r\n')
}

/**
 * 下载 CSV（带 UTF-8 BOM，Excel 直接打开中文不乱码）。用于前端已取回数据的看板 / 报表导出。
 *
 * @param name 文件名（不含扩展名）
 * @param head 表头
 * @param rows 数据行
 */
export function downloadCsv(name: string, head: string[], rows: unknown[][]) {
  const blob = new Blob(['\uFEFF' + toCsv(head, rows)], {
    type: 'text/csv;charset=utf-8',
  })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${name}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
}
