/**
 * P3 即将到期人员汇总（D62-8 / D64，见 docs/p3-operator-qual.md）。
 *
 * `GET /mes/exec/operator-qual/expiring?days=`，权限沿用 operator_qual 读权限；
 * 前端默认不传 days，后端取设置（默认 30）。行字段为前端假设。
 * 404（未上线）时返回示例数据并标 `mock: true`。
 */
import { AxiosError } from 'axios'
import { http } from '../client'

export interface QualExpiringRow {
  qual_id: string
  username: string
  operation: string
  equipment_type: string | null
  expires_on: string
  /** 距到期天数（按站点时区，当天为 0 仍有效） */
  days_left: number
}

export interface QualExpiringReport {
  warn_days: number
  timezone: string
  rows: QualExpiringRow[]
  mock?: boolean
}

/** 示例数据（确定性）。 */
export function qualExpiringMock(): QualExpiringReport {
  const rows: QualExpiringRow[] = [
    ['op1', 'WB', 'WB-ASM', 0],
    ['op2', 'DA', null, 5],
    ['op3', 'FT', 'FT-ADV', 18],
    ['op1', 'MD', null, 29],
  ].map(([u, op, et, d], i) => ({
    qual_id: `mock-${i}`,
    username: u as string,
    operation: op as string,
    equipment_type: et as string | null,
    expires_on: `2026-11-${String(1 + ((d as number) % 28)).padStart(2, '0')}`,
    days_left: d as number,
  }))
  return { warn_days: 30, timezone: 'Asia/Taipei', rows, mock: true }
}

export const qualExpiringApi = {
  list: async (days?: number): Promise<QualExpiringReport> => {
    try {
      return (
        await http.get<QualExpiringReport>('/mes/exec/operator-qual/expiring', {
          params: { days },
        })
      ).data
    } catch (e) {
      if (e instanceof AxiosError && e.response?.status === 404)
        return qualExpiringMock()
      throw e
    }
  },
}
