/**
 * P3 Cycle Time / Move 报表接口（前端假设，后端未定；契约草案见 docs/p3-ct-move-contract.md）。
 *
 * 假设：`GET /mes/exec/reports/ct-move`，权限 `mes.exec:read`。
 * - 入参：`date_from` / `date_to`（YYYY-MM-DD，按租户时区的自然日，含两端）、可选 `operation_id`、`product_id`。
 * - 出参：按日趋势 `trend[]` + 按工序汇总 `by_operation[]` + 总计 `total`。
 * - CT 单位为小时，十进制字符串（D50）；没有数据为 null。Move = 该工序 Track Out（出站）次数，按批次计，
 *   另给 `move_qty`（出站数量合计）。
 * 后端返回 404（接口未上线）时前端用 `ctMoveMock` 示例数据，并在页面标注“示例数据”。
 */
import { AxiosError } from 'axios'
import { http } from '../client'
import type { DecimalValue } from './execution'

export interface CtMoveParams {
  date_from: string
  date_to: string
  operation_id?: string
  product_id?: string
}

/** 按日趋势点。 */
export interface CtMoveTrendPoint {
  /** 自然日 YYYY-MM-DD（租户时区） */
  day: string
  /** 出站批次数 */
  moves: number
  /** 出站数量合计 */
  move_qty: DecimalValue
  /** 当日出站批次的平均工序 CT（小时，Track In → Track Out 之前的等待含在内与否见契约） */
  ct_avg_hours: DecimalValue | null
}

/** 按工序汇总行。 */
export interface CtMoveOperationRow {
  operation_id: string
  operation: string
  operation_name: string | null
  moves: number
  move_qty: DecimalValue
  ct_avg_hours: DecimalValue | null
  ct_p50_hours: DecimalValue | null
  ct_p90_hours: DecimalValue | null
  /** 期末在制批次数 */
  wip_lots: number
}

export interface CtMoveReport {
  date_from: string
  date_to: string
  /** 租户时区（IANA），日期分桶依据 */
  timezone: string
  trend: CtMoveTrendPoint[]
  by_operation: CtMoveOperationRow[]
  total: {
    moves: number
    move_qty: DecimalValue
    ct_avg_hours: DecimalValue | null
  }
  /** 前端标记：接口未上线时为示例数据 */
  mock?: boolean
}

const days = (from: string, to: string) => {
  const out: string[] = []
  const d = new Date(`${from}T00:00:00Z`)
  const end = new Date(`${to}T00:00:00Z`)
  while (d <= end && out.length < 400) {
    out.push(d.toISOString().slice(0, 10))
    d.setUTCDate(d.getUTCDate() + 1)
  }
  return out
}

const OPS = [
  ['op-dice', 'DS', 'Dicing'],
  ['op-da', 'DA', 'Die attach'],
  ['op-wb', 'WB', 'Wire bond'],
  ['op-mold', 'MD', 'Molding'],
  ['op-ft', 'FT', 'Final test'],
] as const

/** 示例数据（确定性，便于截图和测试）。 */
export function ctMoveMock(p: CtMoveParams): CtMoveReport {
  const ops = OPS.filter(([id]) => !p.operation_id || id === p.operation_id)
  const trend = days(p.date_from, p.date_to).map((day, i) => {
    const moves = ops.length * (8 + ((i * 7) % 5))
    return {
      day,
      moves,
      move_qty: String(moves * 25),
      ct_avg_hours: (3.5 + ((i * 3) % 7) * 0.25).toFixed(2),
    }
  })
  const by_operation = ops.map(([id, code, name], k) => ({
    operation_id: id,
    operation: code,
    operation_name: name,
    moves: trend.length * (8 + k),
    move_qty: String(trend.length * (8 + k) * 25),
    ct_avg_hours: (2 + k * 0.75).toFixed(2),
    ct_p50_hours: (1.8 + k * 0.7).toFixed(2),
    ct_p90_hours: (3.2 + k * 1.1).toFixed(2),
    wip_lots: 3 + k,
  }))
  const moves = trend.reduce((n, x) => n + x.moves, 0)
  return {
    date_from: p.date_from,
    date_to: p.date_to,
    timezone: 'Asia/Taipei',
    trend,
    by_operation,
    total: { moves, move_qty: String(moves * 25), ct_avg_hours: '4.25' },
    mock: true,
  }
}

export const ctMoveApi = {
  report: async (p: CtMoveParams): Promise<CtMoveReport> => {
    try {
      return (
        await http.get<CtMoveReport>('/mes/exec/reports/ct-move', {
          params: {
            ...p,
            operation_id: p.operation_id || undefined,
            product_id: p.product_id || undefined,
          },
        })
      ).data
    } catch (e) {
      if (e instanceof AxiosError && e.response?.status === 404)
        return ctMoveMock(p)
      throw e
    }
  },
}
