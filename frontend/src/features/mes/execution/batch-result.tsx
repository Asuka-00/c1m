/** 批量作业结果 / 预检阻断列表。 */
import { t } from '@/i18n'
import type { BatchItem } from '@/lib/api/mes/execution'
import {
  checkMessage,
  codeText,
  detailParams,
  itemText,
  type CodedItem,
} from '@/lib/backend-text'
import { Badge } from '@/components/ui/badge'

/** 单批错误详情转为文本（字段校验错误 / 检查阻断 / 业务错误码）。 */
function detailText(d: unknown): string {
  if (Array.isArray(d))
    return d
      .map((x: CodedItem) => itemText(x) ?? x.msg ?? '')
      .join(t('mes.checkSep'))
  if (d && typeof d === 'object' && 'results' in d) {
    const rs = (d as { results: BatchItem['results'] }).results ?? []
    return rs
      .filter((r) => r.result === 'block')
      .map((r) => `${r.rule_code ?? r.check_type}: ${checkMessage(r)}`)
      .join(t('mes.checkSep'))
  }
  if (d && typeof d === 'object' && 'code' in d) {
    const x = d as Record<string, unknown>
    return codeText(x.code, detailParams(x)) ?? String(x.message ?? x.code)
  }
  return String(d)
}

/**
 * 按批次显示结果：成功、失败原因或阻断的检查。
 *
 * @param items - 各批次结果
 */
export function BatchResult({ items }: { items: BatchItem[] }) {
  return (
    <ul className='space-y-2 text-sm' data-testid='batch-result'>
      {items.map((it) => {
        const blocks = (it.results ?? []).filter((r) => r.result === 'block')
        const ok = it.ok ?? blocks.length === 0
        return (
          <li key={it.lot_id} className='flex flex-wrap items-start gap-2'>
            <span className='font-mono'>{it.code}</span>
            <Badge variant={ok ? 'secondary' : 'destructive'}>
              {ok ? t('mes.batch.ok') : t('mes.batch.failed')}
            </Badge>
            {blocks.map((r) => (
              <span key={r.rule_id ?? r.check_type} className='text-red-600'>
                {r.rule_code ?? r.check_type}: {checkMessage(r)}
              </span>
            ))}
            {it.error != null && (
              <span className='text-red-600'>{detailText(it.error)}</span>
            )}
          </li>
        )
      })}
    </ul>
  )
}
