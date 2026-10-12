import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Loader2 } from 'lucide-react'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi, type MesRow } from '@/lib/api/mes'
import { DescItem, DescList } from '@/components/desc-list'
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
      <DescList>
        {keys.map((k) => (
          <DescItem
            key={k}
            label={fieldLabel(entity, k)}
            value={cellValue(entity, row, k)}
          />
        ))}
      </DescList>
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
