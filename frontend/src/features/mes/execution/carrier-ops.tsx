/** 载具管理页面：载具状态、所装批次、清洗与换载具。 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { fmtDateTime, t } from '@/i18n'
import {
  ArrowRightLeft,
  ListOrdered,
  RefreshCw,
  Sparkles,
  Split,
} from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { execApi, type CarrierRow } from '@/lib/api/mes/execution'
import { Button } from '@/components/ui/button'
import {
  ConfirmDialog,
  DataTable,
  Page,
  clientList,
  useListParams,
  type FilterDef,
} from '@/components/crud'
import { enumLabel } from '@/features/mes/common/labels'
import { MES_PERM, useMesCan } from '@/features/mes/common/mes-perm'
import { RefLink } from '@/features/mes/common/ref-link'
import { mesErrorMessage } from '@/features/mes/common/required'
import { CarrierDue } from './carrier-due'
import { Pick } from './exec-parts'
import { canChangeCarrier } from './lot-rules'
import { SorterDialog } from './sorter-dialog'

/** 载具管理。 */
export default function CarrierOps() {
  const tk = useTenantKey()
  const qc = useQueryClient()
  const [clean, setClean] = useState<CarrierRow | null>(null)
  const [move, setMove] = useState<CarrierRow | null>(null)
  const [target, setTarget] = useState('')
  const [sort, setSort] = useState<CarrierRow | null>(null)
  const q = useQuery({
    queryKey: ['mes', 'exec', tk, 'carrier-board'],
    queryFn: execApi.carrierBoard,
  })
  const all = useMemo(() => q.data ?? [], [q.data])
  const types = [...new Set(all.map((r) => r.carrier_type).filter(Boolean))]
  const filters: FilterDef[] = [
    { type: 'text', name: 'q', placeholder: t('mes.carrier.search') },
    {
      type: 'select',
      name: 'carrier_type',
      label: t('mes.carrier.allTypes'),
      options: types.map((v) => ({ value: v!, label: v! })),
    },
    {
      type: 'select',
      name: 'status',
      label: t('mes.carrier.allStatus'),
      options: ['available', 'in_use', 'dirty', 'hold', 'retired'].map((v) => ({
        value: v,
        label: enumLabel('asset_status', v),
      })),
    },
    {
      type: 'select',
      name: 'due_state',
      label: t('mes.carrier.allDue'),
      options: (['overdue', 'warn', 'ok'] as const).map((v) => ({
        value: v,
        label: t(`mes.carrier.due.${v}`),
      })),
    },
  ]
  const lp = useListParams(filters)
  const view = clientList(all, lp, {
    text: (r) => `${r.code} ${r.lot ?? ''}`,
  })
  const can = useMesCan()
  const canMove = (r: CarrierRow) =>
    can(MES_PERM.execWrite) && canChangeCarrier(r.lot_status)
  const done = (msg: string) => {
    toast.success(msg)
    qc.invalidateQueries({ queryKey: ['mes'] })
  }
  const doClean = useMutation({
    mutationFn: (r: CarrierRow) => execApi.carrierClean(r.id),
    onSuccess: () => {
      setClean(null)
      done(t('mes.carrier.cleaned'))
    },
    onError: (e) => toast.error(mesErrorMessage(e, undefined)),
  })
  const doMove = useMutation({
    mutationFn: (r: CarrierRow) => execApi.changeCarrier(r.lot_id!, target),
    onSuccess: () => {
      setMove(null)
      setTarget('')
      done(t('mes.carrier.moved'))
    },
    onError: (e) => toast.error(mesErrorMessage(e, undefined)),
  })
  const empty = all.filter(
    (r) => !r.lot && r.status === 'available' && r.id !== move?.id
  )
  return (
    <Page
      title={t('menu.mes-carrier-ops')}
      description={t('mes.carrier.hint')}
      actions={
        <Button variant='outline' onClick={() => q.refetch()}>
          <RefreshCw className='size-4' />
          {t('mes.qtime.refresh')}
        </Button>
      }
    >
      <ConfirmDialog
        open={!!clean}
        onOpenChange={(o) => !o && setClean(null)}
        title={t('mes.carrier.clean')}
        desc={t('mes.carrier.cleanConfirm', { code: clean?.code })}
        confirmText={t('mes.carrier.clean')}
        isLoading={doClean.isPending}
        handleConfirm={() => clean && doClean.mutate(clean)}
      />
      <ConfirmDialog
        open={!!move}
        onOpenChange={(o) => !o && setMove(null)}
        title={t('mes.carrier.change')}
        desc={t('mes.carrier.changeDesc', { lot: move?.lot, code: move?.code })}
        confirmText={t('mes.carrier.change')}
        disabled={!target}
        isLoading={doMove.isPending}
        handleConfirm={() => move && doMove.mutate(move)}
      >
        <Pick
          id='carrier-target'
          label={t('mes.carrier.target')}
          required
          value={target}
          onChange={setTarget}
          options={empty.map((r) => ({
            id: r.id,
            label: `${r.code} · ${r.carrier_type ?? ''}`,
          }))}
        />
      </ConfirmDialog>
      {sort && (
        <SorterDialog
          carrier={sort}
          targets={all.filter((r) => !r.lot && r.status === 'available')}
          onClose={() => setSort(null)}
        />
      )}
      <DataTable
        rows={view.rows}
        total={view.total}
        params={lp}
        filters={filters}
        loading={q.isLoading}
        rowKey={(r) => r.id}
        columns={[
          {
            header: t('mes.carrier.code'),
            sortKey: 'code',
            cell: (r) => <RefLink target='carrier' id={r.id} label={r.code} />,
          },
          {
            header: t('mes.carrier.type'),
            sortKey: 'carrier_type',
            cell: (r) => r.carrier_type ?? '—',
          },
          {
            header: t('mes.carrier.status'),
            sortKey: 'status',
            cell: (r) => enumLabel('asset_status', r.status),
          },
          {
            header: t('mes.carrier.lot'),
            sortKey: 'lot',
            cell: (r) =>
              r.lot_id ? (
                <RefLink target='lot' id={r.lot_id} label={r.lot!} />
              ) : (
                '—'
              ),
          },
          {
            header: t('mes.carrier.fill'),
            sortKey: 'wafers',
            className: 'tabular-nums',
            cell: (r) => `${r.wafers}${r.capacity ? ` / ${r.capacity}` : ''}`,
          },
          {
            header: t('mes.carrier.usage'),
            sortKey: 'use_count',
            cell: (r) => <CarrierDue row={r} />,
          },
          {
            header: t('mes.carrier.cleanDue'),
            sortKey: 'clean_due_at',
            cell: (r) => (r.clean_due_at ? fmtDateTime(r.clean_due_at) : '—'),
          },
          {
            header: '',
            cell: (r) => (
              <span className='flex justify-end gap-1'>
                {r.lot_id && (
                  <>
                    <Button
                      size='sm'
                      variant='ghost'
                      disabled={!canMove(r)}
                      data-testid='carrier-change'
                      onClick={() => setMove(r)}
                    >
                      <ArrowRightLeft className='size-4' />
                      {t('mes.carrier.change')}
                    </Button>
                    <Button
                      size='sm'
                      variant='ghost'
                      disabled={!canMove(r)}
                      data-testid='carrier-sort'
                      onClick={() => setSort(r)}
                    >
                      <ListOrdered className='size-4' />
                      {t('mes.sorter.action')}
                    </Button>
                    <Button size='sm' variant='ghost' asChild>
                      <Link
                        to='/$'
                        params={{ _splat: 'mes/lot-console' }}
                        search={{ lot: r.lot_id } as never}
                      >
                        <Split className='size-4' />
                        {t('mes.carrier.splitMerge')}
                      </Link>
                    </Button>
                  </>
                )}
                {!r.lot_id &&
                  r.status !== 'retired' &&
                  can(MES_PERM.execWrite) && (
                    <Button
                      size='sm'
                      variant='ghost'
                      disabled={!can(MES_PERM.execWrite)}
                      data-testid='carrier-clean'
                      onClick={() => setClean(r)}
                    >
                      <Sparkles className='size-4' />
                      {t('mes.carrier.clean')}
                    </Button>
                  )}
              </span>
            ),
          },
        ]}
      />
    </Page>
  )
}
