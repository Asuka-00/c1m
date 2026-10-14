/**
 * P3 Cycle Time / Move 报表接口（口径按 D62 + D63 定稿；契约见 docs/p3-ct-move-contract.md）。
 *
 * `GET /mes/exec/reports/ct-move`，权限 `mes.exec:read`（定稿）。只做工序 CT，批次 CT 不进 P3。
 * - 入参：`date_from` / `date_to`（YYYY-MM-DD，含两端，最多 92 天，超出 422 `date_range_too_large`）、
 *   可选 `operation_id`、`product_id`。
 * - Move：一次出站 = 1 个 move（批次 move 数 `moves`）；`move_qty` = 出站片数（晶圆 move 数）。
 *   拆批 / 合批 / 跳站不算；返工出站单独列 `rework_moves` / `rework_move_qty`，不计入 moves / move_qty。
 * - CT：上一工序出站（首工序为开批）→ 本工序出站，小时，十进制字符串（D50），按出站日期归天，不扣 Hold；
 *   Hold 时长单独 `hold_hours`（小时字符串）。没有数据：计数 0，时长 null；`trend` 每天都列。
 * - 分桶按站点时区（后端算）：前端不硬编码，显示响应里的 `timezone`。
 * P3-B5（be/p3 2c19bb3）已上线：默认走真实接口；`VITE_CT_MOVE_MOCK=1` 时用 `mockCtMoveReport`（页面标注“示例数据”）。
 * 404 = 工序 / 产品不存在（不再回退示例数据）；422 date_range_too_large（ctx.max_days=92）/ range_inverted。
 */
import { AxiosError, AxiosHeaders } from 'axios'
import { http } from '../client'
import type { DecimalValue } from './execution'

/** 日期跨度上限（D62-3，含两端）。 */
export const CT_MOVE_MAX_DAYS = 92

export interface CtMoveParams {
  date_from: string
  date_to: string
  operation_id?: string
  product_id?: string
}

/** 计数与时长指标（trend / by_operation / total 共用）。 */
export interface CtMoveMetrics {
  /** 批次 move 数（出站次数，不含返工出站） */
  moves: number
  /** 晶圆 move 数 = 出站片数合计（不含返工） */
  move_qty: DecimalValue
  /** 返工出站批次数 */
  rework_moves: number
  /** 返工出站片数 */
  rework_move_qty: DecimalValue
  /** 返工片数（T5-1） */
  rework_qty?: DecimalValue
  /** 平均工序 CT（小时），无数据 null */
  ct_avg_hours: DecimalValue | null
  /** 平均 Hold 时长（按出站批次平均，同 ct_avg_hours；小时，CT 内不扣除，单独列；字段名已定稿），无数据 null */
  hold_hours: DecimalValue | null
}

/** 按日趋势点（范围内每天都有；无数据计数 0、时长 null）。 */
export interface CtMoveTrendPoint extends CtMoveMetrics {
  /** 自然日 YYYY-MM-DD（按响应 timezone） */
  day: string
}

/** 按工序汇总行。 */
export interface CtMoveOperationRow extends CtMoveMetrics {
  operation_id: string
  operation: string
  operation_name: string | null
  ct_p50_hours: DecimalValue | null
  ct_p90_hours: DecimalValue | null
  /** 期末在制批次数（date_to 站点日结束时点） */
  wip_lots: number
  /** 期末 Hold 批次数 */
  on_hold_lots: number
  /** 期末 Hold 片数 */
  on_hold_qty: DecimalValue
}

export interface CtMoveReport {
  date_from: string
  date_to: string
  /** 站点时区（IANA，后端分桶依据） */
  timezone: string
  trend: CtMoveTrendPoint[]
  by_operation: CtMoveOperationRow[]
  total: CtMoveMetrics
  /** 前端标记：接口未上线时为示例数据 */
  mock?: boolean
}

/** 区间天数（含两端）；格式不对或倒序返回 null。 */
export function rangeDays(from: string, to: string): number | null {
  const re = /^\d{4}-\d{2}-\d{2}$/
  if (!re.test(from) || !re.test(to)) return null
  const a = Date.parse(`${from}T00:00:00Z`)
  const b = Date.parse(`${to}T00:00:00Z`)
  if (Number.isNaN(a) || Number.isNaN(b) || b < a) return null
  return Math.round((b - a) / 86_400_000) + 1
}

/** 前端预校验：null 表示可查询，否则返回问题类型（倒序单独为 inverted，D77 补充一）。 */
export function rangeProblem(
  from: string,
  to: string
): 'invalid' | 'inverted' | 'too_large' | null {
  const re = /^\d{4}-\d{2}-\d{2}$/
  if (re.test(from) && re.test(to) && from > to) return 'inverted'
  const n = rangeDays(from, to)
  if (n == null) return 'invalid'
  return n > CT_MOVE_MAX_DAYS ? 'too_large' : null
}

const days = (from: string, to: string) => {
  const out: string[] = []
  const d = new Date(`${from}T00:00:00Z`)
  const end = new Date(`${to}T00:00:00Z`)
  while (d <= end && out.length < 400) {
    // 纯日历迭代（输入已是站点日期，按 UTC 零点逐日加），不是取「今天」
    out.push(d.toISOString().slice(0, 10))
    d.setUTCDate(d.getUTCDate() + 1)
  }
  return out
}

/** 空指标：计数 0，时长 null。 */
export const emptyMetrics = (): CtMoveMetrics => ({
  moves: 0,
  move_qty: '0',
  rework_moves: 0,
  rework_move_qty: '0',
  ct_avg_hours: null,
  hold_hours: null,
})

/** 补齐后端可能缺省的新字段（老版本或部分返回），保证计数 0 / 时长 null。 */
export function normalizeReport(r: CtMoveReport): CtMoveReport {
  const fix = <T extends Partial<CtMoveMetrics>>(x: T) => ({
    ...emptyMetrics(),
    ...Object.fromEntries(Object.entries(x).filter(([, v]) => v !== undefined)),
  })
  return {
    ...r,
    trend: (r.trend ?? []).map((x) => fix(x) as CtMoveTrendPoint),
    by_operation: (r.by_operation ?? []).map(
      (x) =>
        ({
          ct_p50_hours: null,
          ct_p90_hours: null,
          wip_lots: 0,
          on_hold_lots: 0,
          on_hold_qty: '0',
          ...fix(x),
        }) as CtMoveOperationRow
    ),
    total: fix(r.total ?? {}),
  }
}

const OPS = [
  ['op-dice', 'DS', 'Dicing'],
  ['op-da', 'DA', 'Die attach'],
  ['op-wb', 'WB', 'Wire bond'],
  ['op-mold', 'MD', 'Molding'],
  ['op-ft', 'FT', 'Final test'],
] as const

/** 示例数据（确定性，便于截图和测试）；每 6 天有一天无出站，用来演示空日。 */
export function ctMoveMock(p: CtMoveParams): CtMoveReport {
  const ops = OPS.filter(([id]) => !p.operation_id || id === p.operation_id)
  const trend: CtMoveTrendPoint[] = days(p.date_from, p.date_to).map(
    (day, i) => {
      if (i % 6 === 5) return { day, ...emptyMetrics() }
      const moves = ops.length * (8 + ((i * 7) % 5))
      const rw = i % 3 === 0 && ops.length ? 1 : 0
      return {
        day,
        moves,
        move_qty: String(moves * 25),
        rework_moves: rw,
        rework_move_qty: String(rw * 25),
        ct_avg_hours: ops.length
          ? (3.5 + ((i * 3) % 7) * 0.25).toFixed(2)
          : null,
        hold_hours: ops.length ? (0.2 + (i % 4) * 0.1).toFixed(2) : null,
      }
    }
  )
  const by_operation = ops.map(([id, code, name], k) => ({
    operation_id: id,
    operation: code,
    operation_name: name,
    moves: trend.length * (8 + k),
    move_qty: String(trend.length * (8 + k) * 25),
    rework_moves: k,
    rework_move_qty: String(k * 25),
    ct_avg_hours: (2 + k * 0.75).toFixed(2),
    ct_p50_hours: (1.8 + k * 0.7).toFixed(2),
    ct_p90_hours: (3.2 + k * 1.1).toFixed(2),
    hold_hours: (0.1 + k * 0.05).toFixed(2),
    wip_lots: 3 + k,
    on_hold_lots: k % 2,
    on_hold_qty: String((k % 2) * 25),
  }))
  const moves = trend.reduce((n, x) => n + x.moves, 0)
  const rw = trend.reduce((n, x) => n + x.rework_moves, 0)
  return {
    date_from: p.date_from,
    date_to: p.date_to,
    timezone: 'Asia/Taipei',
    trend,
    by_operation,
    total: {
      moves,
      move_qty: String(moves * 25),
      rework_moves: rw,
      rework_move_qty: String(rw * 25),
      ct_avg_hours: moves ? '4.25' : null,
      hold_hours: moves ? '8.50' : null,
    },
    mock: true,
  }
}

const mockErr = (status: number, detail: unknown) => {
  const e = new AxiosError('mock', 'ERR_BAD_REQUEST')
  e.response = {
    status,
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
    data: { detail },
  }
  return e
}

/** mock 版接口：与后端同样校验（422 missing / value_error range_inverted / date_range_too_large，404 工序或产品不存在）。 */
export function mockCtMoveReport(p: CtMoveParams): CtMoveReport {
  for (const k of ['date_from', 'date_to'] as const)
    if (!p[k])
      throw mockErr(422, [
        { loc: ['query', k], type: 'missing', msg: 'Field required' },
      ])
  if (p.date_from > p.date_to)
    throw mockErr(422, [
      {
        loc: ['query', 'date_from'],
        type: 'value_error',
        msg: 'date_from after date_to',
        ctx: { reason: 'range_inverted' },
      },
    ])
  if ((rangeDays(p.date_from, p.date_to) ?? 0) > CT_MOVE_MAX_DAYS)
    throw mockErr(422, [
      {
        loc: ['query', 'date_to'],
        type: 'date_range_too_large',
        msg: `range too long (max ${CT_MOVE_MAX_DAYS} days)`,
        ctx: { max_days: CT_MOVE_MAX_DAYS },
      },
    ])
  if (p.operation_id && !OPS.some(([id]) => id === p.operation_id))
    throw mockErr(404, {
      code: 'operation_not_found',
      message: 'operation not found',
    })
  if (p.product_id && p.product_id.startsWith('missing'))
    throw mockErr(404, {
      code: 'product_not_found',
      message: 'product not found',
    })
  return ctMoveMock(p)
}

/** 是否用 mock（默认走真实接口）。 */
export const CT_MOVE_MOCK = import.meta.env.VITE_CT_MOVE_MOCK === '1'

export const ctMoveApi = {
  report: async (p: CtMoveParams): Promise<CtMoveReport> => {
    if (CT_MOVE_MOCK) return mockCtMoveReport(p)
    const r = (
      await http.get<CtMoveReport>('/mes/exec/reports/ct-move', {
        params: {
          ...p,
          operation_id: p.operation_id || undefined,
          product_id: p.product_id || undefined,
        },
      })
    ).data
    return normalizeReport(r)
  },
}
