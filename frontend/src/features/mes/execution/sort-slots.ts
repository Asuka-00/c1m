/** 晶圆整理的槽位计算。 */

/** 晶圆的当前与目标槽位。 */
export interface SortRow {
  id: string
  code: string
  from: number
  to: number
}

/** 按晶圆号顺排（从 start 起连续编号）。 */
export function packSlots(rows: SortRow[], start = 1): SortRow[] {
  return [...rows]
    .sort((a, b) => a.code.localeCompare(b.code))
    .map((r, i) => ({ ...r, to: start + i }))
}
