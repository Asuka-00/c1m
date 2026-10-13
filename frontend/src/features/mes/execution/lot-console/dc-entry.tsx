/** Track Out 数据采集录入表（超规格值标红）。 */
import { useMemo } from 'react'
import { t } from '@/i18n'
import type { ExecContext } from '@/lib/api/mes/execution'
import { cn } from '@/lib/utils'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { enumLabel } from '@/features/mes/common/labels'
import type { Dc } from './types'

export function DcEntry(p: {
  cx: ExecContext
  units: ExecContext['units']
  dc: Dc
  setDc: (v: Dc) => void
}) {
  const dc = p.cx.dc
  const units = useMemo(
    () =>
      dc?.unit_ids?.length
        ? p.units.filter((u) => dc.unit_ids?.includes(u.id))
        : [null],
    [dc, p.units]
  )
  return (
    <section className='space-y-2' data-testid='dc-entry'>
      <div>
        <h4 className='text-sm font-semibold'>{t('mes.exec.dc')}</h4>
        <p className='text-xs text-muted-foreground'>
          {dc?.dc_plan ? `${dc.dc_plan} · ` : ''}
          {dc?.message}
        </p>
      </div>
      {dc?.sampled && dc.items.length > 0 ? (
        <div className='overflow-hidden rounded-md border'>
          <Table>
            <TableHeader className='bg-muted/40'>
              <TableRow>
                <TableHead>{t('mes.exec.item')}</TableHead>
                <TableHead>{t('mes.exec.unit')}</TableHead>
                <TableHead>{t('mes.exec.values')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {dc.items.flatMap((it) =>
                units.map((u) => (
                  <TableRow key={`${it.measurement_item_id}-${u?.id ?? 'lot'}`}>
                    <TableCell className='align-top'>
                      <div className='font-medium'>{it.code}</div>
                      <div className='text-xs text-muted-foreground'>
                        {it.lsl ?? '−∞'} … {it.usl ?? '∞'}
                      </div>
                      <div className='text-xs text-muted-foreground'>
                        {t('mes.exec.oosAction')}:{' '}
                        {enumLabel('oos_action', it.oos_action)}
                      </div>
                    </TableCell>
                    <TableCell className='align-top font-mono text-xs'>
                      {u ? u.code : t('mes.exec.lotLevel')}
                    </TableCell>
                    <TableCell className='whitespace-normal'>
                      <div className='flex flex-wrap gap-1.5'>
                        {Array.from(
                          { length: Math.min(it.sites ?? 1, 5) || 1 },
                          (_, s) => {
                            const k = `${it.measurement_item_id}|${u?.id ?? ''}|${s + 1}`
                            const v = p.dc[k] ?? ''
                            const n = Number(v)
                            const oos =
                              v !== '' &&
                              ((it.lsl != null && n < it.lsl) ||
                                (it.usl != null && n > it.usl))
                            return (
                              <Input
                                key={k}
                                aria-label={`${it.code} ${s + 1}`}
                                placeholder={`#${s + 1}`}
                                className={cn(
                                  'h-8 w-20',
                                  oos && 'border-destructive text-destructive'
                                )}
                                inputMode='decimal'
                                value={v}
                                onChange={(e) =>
                                  p.setDc({ ...p.dc, [k]: e.target.value })
                                }
                              />
                            )
                          }
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      ) : (
        <p className='text-sm text-muted-foreground'>{t('mes.exec.noDc')}</p>
      )}
    </section>
  )
}
