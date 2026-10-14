/**
 * BOM 超量用料（P1 F4 / B2，D32）：出站只提示、不拦截。
 *
 * 出站响应 `warnings` 里 `code=bom_over_consumption` 的一条带 `lines`；
 * 批次履历 `bom_over_consumption` 的 `details.lines` 同样格式。数量可能是数字或定点字符串（D50），
 * 只用 decimal.ts 显示，不做浮点运算。
 */
import { t } from '@/i18n'
import { decimalText } from '@/lib/decimal'

export interface OverLine {
  bom_line_id?: string
  material?: string | null
  uom?: string | null
  planned?: number | string | null
  actual?: number | string | null
  excess?: number | string | null
}

export interface StageWarning {
  code: string
  message?: string
  lines?: OverLine[]
}

/** 一条超量明细的文本：「AU-WIRE 0.35 / 0.3 g（超 0.05）」。 */
export function overLineText(l: OverLine): string {
  return t('mes.over.line', {
    material: l.material ?? '—',
    actual: decimalText(l.actual),
    planned: decimalText(l.planned),
    uom: l.uom ?? '',
    excess: decimalText(l.excess),
  }).trim()
}

/** 出站响应里的超量提示文本；没有超量返回 null。 */
export function overWarningText(ws: StageWarning[] | undefined): string | null {
  const lines = (ws ?? [])
    .filter((w) => w.code === 'bom_over_consumption')
    .flatMap((w) => w.lines ?? [])
  if (!lines.length) return null
  return t('mes.over.toast', { lines: lines.map(overLineText).join('；') })
}
