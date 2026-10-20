/** 晶圆整理（Sorter）对话框：调整本批次晶圆槽位，可同时换到空载具。 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import {
  blockedResults,
  execApi,
  type CarrierRow,
} from '@/lib/api/mes/execution'
import { checkMessage } from '@/lib/backend-text'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { mesErrorMessage } from '@/features/mes/common/required'
import { Pick } from '../shared/exec-parts'
import { packSlots, type SortRow } from './sort-slots'

/**
 * 晶圆整理对话框。
 *
 * @param carrier - 当前载具行（含批次）
 * @param targets - 可选的空载具
 * @param onClose - 关闭回调
 */
export function SorterDialog({
  carrier,
  targets,
  onClose,
}: {
  carrier: CarrierRow
  targets: CarrierRow[]
  onClose: () => void
}) {
  const tk = useTenantKey()
  const qc = useQueryClient()
  const [edits, setEdits] = useState<Record<string, number>>({})
  const [target, setTarget] = useState('')
  const map = useQuery({
    queryKey: ['mes', 'exec', tk, 'wafer-map', carrier.lot_id],
    queryFn: () => execApi.waferMap(carrier.lot_id!),
  })
  const rows: SortRow[] = useMemo(
    () =>
      (map.data?.slots ?? [])
        .filter((x) => x.wafer)
        .map((x) => ({
          id: x.wafer!.id,
          code: x.wafer!.code,
          from: x.slot,
          to: edits[x.wafer!.id] ?? x.slot,
        })),
    [map.data, edits]
  )
  const run = useMutation({
    mutationFn: () =>
      execApi.sortWafers(carrier.lot_id!, {
        slots: rows.map((r) => ({ wafer_id: r.id, slot: r.to })),
        carrier_id: target || null,
      }),
    onSuccess: () => {
      toast.success(t('mes.sorter.done'))
      qc.invalidateQueries({ queryKey: ['mes'] })
      onClose()
    },
    onError: (e) => {
      const b = blockedResults(e)
      toast.error(
        b
          ? b
              .filter((r) => r.result === 'block')
              .map(checkMessage)
              .join(t('mes.checkSep'))
          : mesErrorMessage(e, undefined)
      )
    },
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>
            {t('mes.sorter.title', { lot: carrier.lot, code: carrier.code })}
          </DialogTitle>
        </DialogHeader>
        <Pick
          id='sorter-target'
          label={t('mes.sorter.target')}
          value={target}
          onChange={setTarget}
          options={targets.map((r) => ({ id: r.id, label: r.code }))}
        />
        <div className='max-h-80 overflow-auto rounded-md border'>
          <table className='w-full text-sm' data-testid='sorter-table'>
            <thead className='bg-muted/50 text-left'>
              <tr>
                <th className='px-3 py-1.5'>{t('mes.sorter.wafer')}</th>
                <th className='px-3 py-1.5'>{t('mes.sorter.from')}</th>
                <th className='px-3 py-1.5'>{t('mes.sorter.to')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className='border-t'>
                  <td className='px-3 py-1 font-mono'>{r.code}</td>
                  <td className='px-3 py-1 tabular-nums'>{r.from}</td>
                  <td className='px-3 py-1'>
                    <Input
                      type='number'
                      min={1}
                      className='h-8 w-20'
                      aria-label={r.code}
                      value={r.to}
                      onChange={(e) =>
                        setEdits((cur) => ({
                          ...cur,
                          [r.id]: Number(e.target.value) || 1,
                        }))
                      }
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <DialogFooter>
          <Button
            variant='outline'
            onClick={() =>
              setEdits(
                Object.fromEntries(packSlots(rows).map((r) => [r.id, r.to]))
              )
            }
          >
            {t('mes.sorter.pack')}
          </Button>
          <Button
            disabled={!rows.length || run.isPending}
            onClick={() => run.mutate()}
          >
            {t('mes.sorter.run')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
