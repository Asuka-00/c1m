/** 批量作业结果 / 预检阻断列表。 */
import { t } from '@/i18n'
import type { BatchItem } from '@/lib/api/mes/execution'
import { Badge } from '@/components/ui/badge'
import { enumLabel } from '@/features/mes/common/labels'
import { checkMessage } from './check-message'

/** 检查名：有规则编码用编码，否则翻译检查类型（不显示原始代码）。 */
const checkName = (r: { rule_code?: string | null; check_type: string }) =>
  r.rule_code ?? enumLabel('check_type', r.check_type)

/** 单批错误详情转为文本（校验错误 / 检查阻断 / 其他）。 */
function detailText(d: unknown): string {
  if (Array.isArray(d))
    return d.map((x: { msg?: string }) => x.msg ?? '').join('; ')
  if (d && typeof d === 'object' && 'results' in d) {
    const rs = (d as { results: BatchItem['results'] }).results ?? []
    return rs
      .filter((r) => r.result === 'block')
      .map((r) => `${checkName(r)}: ${checkMessage(r)}`)
      .join('; ')
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
                {checkName(r)}: {checkMessage(r)}
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
