/** Wafer / Die Bank 页面：完工批次入库，按工单从 Bank 领用开出新批次。 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearch } from '@tanstack/react-router'
import { fmtDateTime, t } from '@/i18n'
import { PackageMinus, PackagePlus } from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi } from '@/lib/api/mes/common'
import { semiApi } from '@/lib/api/mes/semi'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Page } from '@/components/crud'
import { MES_PERM, useMesCan } from '@/features/mes/common/mes-perm'
import { RefLink } from '@/features/mes/common/ref-link'
import { RefSelect } from '@/features/mes/common/ref-select'
import { mesErrorMessage } from '@/features/mes/common/required'

type Ref = { id: string; code: string } | null

function RefField({
  id,
  label,
  target,
  value,
  onChange,
  filters,
}: {
  id: string
  label: string
  target: string
  value: Ref
  onChange: (v: Ref) => void
  filters?: Record<string, string>
}) {
  return (
    <div className='grid gap-1'>
      <Label htmlFor={id}>{label}</Label>
      <RefSelect
        id={id}
        target={target}
        value={value?.id ?? null}
        label={value?.code ?? null}
        filters={filters}
        onChange={(v, l) => onChange(v ? { id: v, code: l ?? '' } : null)}
      />
    </div>
  )
}

/** Bank 入库与领用。 */
export default function BankOps() {
  const tk = useTenantKey()
  const qc = useQueryClient()
  const can = useMesCan()
  const canBank = can(MES_PERM.execBank)
  // 从操作台「去 Bank 入库」带 ?lot=&lot_code= 进入时预选该完工批次
  const search = useSearch({ strict: false }) as Record<string, unknown>
  const [lot, setLot] = useState<Ref>(() =>
    search.lot
      ? { id: String(search.lot), code: String(search.lot_code ?? search.lot) }
      : null
  )
  const [bank, setBank] = useState<Ref>(null)
  const [wo, setWo] = useState<Ref>(null)
  const [picked, setPicked] = useState<string[]>([])
  const banked = useQuery({
    queryKey: ['mes', 'lot', tk, 'banked'],
    queryFn: () => mesApi.list('lot', { lot_status: 'banked', page_size: 200 }),
  })
  const rows = banked.data?.data ?? []
  const done = (msg: string) => {
    toast.success(msg)
    qc.invalidateQueries({ queryKey: ['mes'] })
  }
  const bankIn = useMutation({
    mutationFn: () => semiApi.bankIn(lot!.id, bank!.id),
    onSuccess: () => {
      done(t('mes.semi.bankedIn', { lot: lot?.code }))
      setLot(null)
    },
    onError: (e) => toast.error(mesErrorMessage(e, undefined)),
  })
  const issue = useMutation({
    mutationFn: () =>
      semiApi.bankIssue({
        work_order_id: wo!.id,
        lots: picked.map((id) => ({ lot_id: id })),
      }),
    onSuccess: (r) => {
      done(t('mes.semi.issued', { lot: r.lot.code, qty: r.lot.qty }))
      setPicked([])
    },
    onError: (e) => toast.error(mesErrorMessage(e, undefined)),
  })
  const toggle = (id: string, on: boolean) =>
    setPicked((p) => (on ? [...p, id] : p.filter((x) => x !== id)))
  return (
    <Page title={t('menu.mes-bank-ops')} description={t('mes.semi.bankHint')}>
      <div className='grid gap-4 lg:grid-cols-2'>
        <Card>
          <CardHeader>
            <CardTitle>{t('mes.semi.bankIn')}</CardTitle>
          </CardHeader>
          <CardContent className='space-y-3'>
            <RefField
              id='bank-lot'
              label={t('mes.semi.completedLot')}
              target='lot'
              value={lot}
              onChange={setLot}
              filters={{ lot_status: 'completed' }}
            />
            <RefField
              id='bank-bank'
              label={t('mes.entity.bank')}
              target='bank'
              value={bank}
              onChange={setBank}
              filters={{ is_active: 'true' }}
            />
            <Button
              disabled={!canBank || !lot || !bank || bankIn.isPending}
              onClick={() => bankIn.mutate()}
            >
              <PackagePlus className='size-4' />
              {t('mes.semi.bankIn')}
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t('mes.semi.issue')}</CardTitle>
          </CardHeader>
          <CardContent className='space-y-3'>
            <RefField
              id='bank-wo'
              label={t('mes.entity.work_order')}
              target='work_order'
              value={wo}
              onChange={setWo}
            />
            <p className='text-sm text-muted-foreground'>
              {t('mes.semi.picked', { count: picked.length })}
            </p>
            <Button
              disabled={!canBank || !wo || !picked.length || issue.isPending}
              onClick={() => issue.mutate()}
            >
              <PackageMinus className='size-4' />
              {t('mes.semi.issue')}
            </Button>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>{t('mes.semi.inBank', { count: rows.length })}</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className='w-8' />
                <TableHead>{t('mes.field.lot.code')}</TableHead>
                <TableHead>{t('mes.field.lot.bank')}</TableHead>
                <TableHead>{t('mes.exec.qty')}</TableHead>
                <TableHead>{t('mes.field.lot.banked_at')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    <Checkbox
                      aria-label={String(r.code)}
                      checked={picked.includes(r.id)}
                      disabled={!!r.on_hold}
                      onCheckedChange={(v) => toggle(r.id, v === true)}
                    />
                  </TableCell>
                  <TableCell>
                    <RefLink target='lot' id={r.id} label={String(r.code)} />
                  </TableCell>
                  <TableCell>{String(r.bank_label ?? '—')}</TableCell>
                  <TableCell className='tabular-nums'>
                    {String(r.qty)}
                  </TableCell>
                  <TableCell>
                    {r.banked_at ? fmtDateTime(String(r.banked_at)) : '—'}
                  </TableCell>
                </TableRow>
              ))}
              {!rows.length && (
                <TableRow>
                  <TableCell colSpan={5} className='text-muted-foreground'>
                    {t('mes.semi.bankEmpty')}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </Page>
  )
}
