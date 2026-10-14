/**
 * 客户来料字段的纯函数（P1 F6 / B7，D36、D37、D40）。
 *
 * - 批次：`customer_lot_no`（客户批号）、`ownership`（own / customer，默认 own）、`customer_id`。
 * - 规则（后端 `customer_start_errors`）：归属为客户来料时必须选客户；自有时不能带客户和客户批号。
 * - 客户批号只去首尾空格，原样保存；查询不区分大小写、精确匹配（D37）。
 */
import { t } from '@/i18n'
import { enumLabel } from '@/features/mes/common/labels'

export type Ownership = 'own' | 'customer'

/** 开批向导里一个批次的客户字段草稿。 */
export interface CustomerDraft {
  ownership: Ownership
  customer_id: string | null
  customer_label: string | null
  customer_lot_no: string
}

export const emptyCustomer = (): CustomerDraft => ({
  ownership: 'own',
  customer_id: null,
  customer_label: null,
  customer_lot_no: '',
})

/** 开批请求体里的客户字段：自有只发 ownership，客户来料带客户和客户批号（去首尾空格）。 */
export function customerBody(d: CustomerDraft): {
  ownership: Ownership
  customer_id?: string
  customer_lot_no?: string | null
} {
  if (d.ownership === 'own') return { ownership: 'own' }
  return {
    ownership: 'customer',
    ...(d.customer_id ? { customer_id: d.customer_id } : {}),
    customer_lot_no: d.customer_lot_no.trim() || null,
  }
}

/**
 * 前端校验，按批次行（从 0 开始）给出字段错误：客户来料必须选客户、必须填客户批号
 * （D52：去首尾空格后为空即拦）。自有批不校验。
 */
export function customerRowErrors(
  lots: CustomerDraft[]
): Record<number, Record<string, string>> {
  const out: Record<number, Record<string, string>> = {}
  lots.forEach((l, i) => {
    if (l.ownership !== 'customer') return
    const row: Record<string, string> = {}
    if (!l.customer_id) row.customer_id = t('mes.start.fe.customerRequired')
    if (!l.customer_lot_no.trim())
      row.customer_lot_no = t('mes.start.fe.customerLotRequired')
    if (Object.keys(row).length) out[i] = row
  })
  return out
}

/** 前端校验的汇总提示（第 n 个批次，从 1 开始显示），用于阻止进入下一步。 */
export function customerErrors(lots: CustomerDraft[]): string[] {
  const out: string[] = []
  lots.forEach((l, i) => {
    if (l.ownership !== 'customer') return
    if (!l.customer_id) out.push(t('mes.cust.errCustomer', { n: i + 1 }))
    if (!l.customer_lot_no.trim())
      out.push(t('mes.cust.errLotNo', { n: i + 1 }))
  })
  return out
}

/** 接口返回的客户信息（追溯、客户批号查询；批次详情用 `customer_label`）。 */
export interface CustomerInfo {
  customer_lot_no?: string | null
  ownership?: string | null
  /** 客户编码（追溯、客户批号查询） */
  customer?: string | null
  /** 客户名称（O-F6-1，与编码一起返回） */
  customer_name?: string | null
  /** 通用接口的引用显示文本（已是「编码 · 名称」） */
  customer_label?: string | null
}

/**
 * 归属文本（O-F6-1，全站统一）：客户来料「客户来料 · 编码 · 名称」，没有名称只显示编码；
 * 自有显示「自有」；历史空值按自有显示，不报错。
 */
export function ownershipText(c: CustomerInfo): string {
  const own = c.ownership || 'own'
  const label = enumLabel('ownership', own)
  if (own !== 'customer') return label
  const who = c.customer
    ? [c.customer, c.customer_name].filter(Boolean).join(' · ')
    : c.customer_label
  return who ? `${label} · ${who}` : label
}
