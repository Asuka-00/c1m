/** PM 计划的到期状态列：汇总看板中各设备该计划的超期 / 即将到期台数与最近到期日。 */
import { useQuery } from '@tanstack/react-query'
import { fmtDate, t } from '@/i18n'
import { useTenantKey } from '@/lib/api/hooks'
import type { MesRow } from '@/lib/api/mes/common'
import { eqpApi } from '@/lib/api/mes/equipment'
import { Badge } from '@/components/ui/badge'

/** PM 计划到期状态（与设备状态看板共用查询缓存）。 */
export function PmPlanStatus({ row }: { row: MesRow }) {
  const tk = useTenantKey()
  const q = useQuery({
    queryKey: ['mes', 'eqp', tk, 'board'],
    queryFn: eqpApi.board,
    staleTime: 60_000,
  })
  const items = (q.data ?? []).flatMap((b) =>
    b.pm.filter((p) => p.plan_id === row.id)
  )
  if (!items.length) return <span className='text-muted-foreground'>—</span>
  const due = items.filter((p) => p.due).length
  const warn = items.filter((p) => p.warn && !p.due).length
  const next = items
    .map((p) => p.next_due)
    .filter(Boolean)
    .sort()[0]
  return (
    <span className='inline-flex flex-wrap items-center gap-1'>
      {due > 0 && (
        <Badge variant='destructive'>{t('mes.pmStatus.due', { n: due })}</Badge>
      )}
      {warn > 0 && (
        <Badge className='bg-amber-500 text-white'>
          {t('mes.pmStatus.warn', { n: warn })}
        </Badge>
      )}
      {!due && !warn && <Badge variant='outline'>{t('mes.pmStatus.ok')}</Badge>}
      {next && (
        <span className='text-xs text-muted-foreground'>
          {t('mes.pmStatus.next', { d: fmtDate(next) })}
        </span>
      )}
    </span>
  )
}
