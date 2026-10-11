import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Loader2 } from 'lucide-react'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi, type MesRow } from '@/lib/api/mes'
import { cellValue } from './cells'
import { fieldLabel } from './labels'
import { RouteFlow } from './route-flow'
import { useMesEntity } from './use-mes-meta'

/** Lot detail: header facts + route flow with the current step highlighted
 *  (wafers are the second tab, from the generic child table). */
export function LotDetail({ row }: { row: MesRow }) {
  const tk = useTenantKey()
  const { entity } = useMesEntity('lot')
  const route = useQuery({
    queryKey: ['mes', 'route', 'one', tk, row.route_id],
    queryFn: () => mesApi.get('route', String(row.route_id)),
  })
  if (!entity) return null
  const keys = [
    'work_order',
    'product',
    'route',
    'qty',
    'lot_status',
    'on_hold',
    'tracking_level',
    'current_step',
    'site',
    'carrier',
    'priority',
    'started_at',
    'started_by',
    'source_ref',
  ]
  return (
    <div className='space-y-3 pt-2' data-testid='lot-detail'>
      <dl className='grid gap-x-6 gap-y-1 text-sm sm:grid-cols-3'>
        {keys.map((k) => (
          <div key={k} className='flex gap-2'>
            <dt className='text-muted-foreground'>{fieldLabel(entity, k)}</dt>
            <dd>{cellValue(entity, row, k)}</dd>
          </div>
        ))}
      </dl>
      <p className='text-sm font-medium'>{t('mes.lotRoute')}</p>
      {route.data ? (
        <RouteFlow
          row={route.data}
          readOnly
          highlight={String(
            (row.route_stack as { step_id: string }[] | null)?.[0]?.step_id ??
              row.current_step_id ??
              ''
          )}
        />
      ) : (
        <Loader2 className='animate-spin' />
      )}
    </div>
  )
}
