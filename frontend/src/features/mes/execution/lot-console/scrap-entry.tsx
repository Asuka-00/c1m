/** Track Out 报废 / 重工录入（按数量或按晶圆）。 */
import { t } from '@/i18n'
import { Plus, Trash2 } from 'lucide-react'
import type { ExecContext } from '@/lib/api/mes/execution'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { IconButton } from '@/components/icon-button'
import { optLabel } from '@/features/mes/common/labels'
import { Pick } from '../exec-parts'
import type { Scrap } from './types'

export function ScrapEntry(p: {
  cx: ExecContext
  qty: boolean
  units: ExecContext['units']
  scrap: Scrap[]
  setScrap: (v: Scrap[]) => void
  rework: Record<string, string>
  setRework: (v: Record<string, string>) => void
}) {
  const { cx } = p
  const scrapReasons = cx.reasons.scrap.map((r) => ({
    id: r.id,
    label: optLabel(r),
  }))
  return (
    <section className='space-y-2' data-testid='scrap-entry'>
      <h4 className='text-sm font-semibold'>
        {p.qty ? t('mes.exec.scrapQty') : t('mes.exec.scrapUnits')}
      </h4>
      {p.qty ? (
        <>
          {p.scrap.map((s, i) => (
            <div key={i} className='flex items-end gap-2'>
              <div className='grid gap-1'>
                <Label htmlFor={`sq-${i}`}>{t('mes.exec.qty')}</Label>
                <Input
                  id={`sq-${i}`}
                  className='w-24'
                  inputMode='numeric'
                  value={s.qty ?? ''}
                  onChange={(e) =>
                    p.setScrap(
                      p.scrap.map((x, j) =>
                        j === i ? { ...x, qty: e.target.value } : x
                      )
                    )
                  }
                />
              </div>
              <div className='w-64'>
                <Pick
                  id={`sr-${i}`}
                  label={t('mes.exec.reason')}
                  required
                  value={s.reason_id}
                  onChange={(v) =>
                    p.setScrap(
                      p.scrap.map((x, j) =>
                        j === i ? { ...x, reason_id: v } : x
                      )
                    )
                  }
                  options={scrapReasons}
                />
              </div>
              <IconButton
                label={t('common.delete')}
                variant='ghost'
                onClick={() => p.setScrap(p.scrap.filter((_, j) => j !== i))}
              >
                <Trash2 className='size-4' />
              </IconButton>
            </div>
          ))}
          <Button
            size='sm'
            variant='outline'
            onClick={() => p.setScrap([...p.scrap, { qty: '', reason_id: '' }])}
          >
            <Plus className='size-4' />
            {t('mes.exec.addScrap')}
          </Button>
          <p className='text-xs text-muted-foreground'>
            {t('mes.exec.goodQty', {
              good:
                Number(cx.lot.qty) -
                p.scrap.reduce((a, s) => a + (Number(s.qty) || 0), 0),
            })}
          </p>
        </>
      ) : (
        <div className='max-h-80 overflow-y-auto rounded-md border'>
          <Table>
            <TableHeader className='sticky top-0 z-10 bg-muted'>
              <TableRow>
                <TableHead className='w-14'>{t('mes.exec.slot')}</TableHead>
                <TableHead>{t('mes.exec.unit')}</TableHead>
                <TableHead>{t('mes.exec.disposition')}</TableHead>
                {cx.reasons.rework.length > 0 && (
                  <TableHead>{t('mes.exec.rework')}</TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {p.units.map((u) => {
                const s = p.scrap.find((x) => x.unit_id === u.id)
                return (
                  <TableRow key={u.id}>
                    <TableCell className='text-muted-foreground tabular-nums'>
                      {u.slot ?? '—'}
                    </TableCell>
                    <TableCell className='font-mono text-xs'>
                      {u.code}
                    </TableCell>
                    <TableCell className='py-1'>
                      <select
                        aria-label={`${u.code} scrap`}
                        className='h-8 w-full min-w-28 rounded-md border border-input bg-transparent px-2 text-sm'
                        value={s?.reason_id ?? ''}
                        onChange={(e) => {
                          const rest = p.scrap.filter((x) => x.unit_id !== u.id)
                          p.setScrap(
                            e.target.value
                              ? [
                                  ...rest,
                                  {
                                    unit_id: u.id,
                                    reason_id: e.target.value,
                                  },
                                ]
                              : rest
                          )
                        }}
                      >
                        <option value=''>{t('mes.exec.good')}</option>
                        {cx.reasons.scrap.map((r) => (
                          <option key={r.id} value={r.id}>
                            {t('mes.exec.scrap')}: {r.code}
                          </option>
                        ))}
                      </select>
                    </TableCell>
                    {cx.reasons.rework.length > 0 && (
                      <TableCell className='py-1'>
                        <select
                          aria-label={`${u.code} rework`}
                          className='h-8 w-full min-w-28 rounded-md border border-input bg-transparent px-2 text-sm'
                          value={p.rework[u.id] ?? ''}
                          disabled={!!s}
                          onChange={(e) =>
                            p.setRework({
                              ...p.rework,
                              [u.id]: e.target.value,
                            })
                          }
                        >
                          <option value=''>—</option>
                          {cx.reasons.rework.map((r) => (
                            <option key={r.id} value={r.id}>
                              {r.code}
                            </option>
                          ))}
                        </select>
                      </TableCell>
                    )}
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  )
}
