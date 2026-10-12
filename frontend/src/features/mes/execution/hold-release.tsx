/** 批量释放 Hold 页面：按原因 / 来源 / 产品筛选生效中的 Hold，勾选后批量释放。 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { fmtDateTime, t } from '@/i18n'
import { Unlock } from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { mesApi } from '@/lib/api/mes/common'
import { execApi } from '@/lib/api/mes/execution'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { Page } from '@/components/crud'
import { optLabel } from '@/features/mes/common/labels'
import { RefSelect } from '@/features/mes/common/ref-select'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesMeta } from '@/features/mes/common/use-mes-meta'
import { Pick } from './exec-parts'

const PAGE = 20
const SOURCES = ['manual', 'qtime', 'dc', 'check']

/** 批量释放 Hold。 */
export default function HoldReleasePage() {
  const tk = useTenantKey()
  const { data: meta } = useMesMeta()
  const canRelease = (meta?.perms ?? []).includes('mes.exec:hold')
  const [reason, setReason] = useState<string | null>(null)
  const [source, setSource] = useState('')
  const [product, setProduct] = useState<string | null>(null)
  const [sel, setSel] = useState<string[]>([])
  const [page, setPage] = useState(0)
  const [open, setOpen] = useState(false)
  const f = {
    reason_id: reason ?? undefined,
    source: source || undefined,
    product_id: product ?? undefined,
  }
  const q = useQuery({
    queryKey: ['mes', 'exec', tk, 'holds-active', f],
    queryFn: () => execApi.activeHolds(f),
  })
  const rows = q.data ?? []
  const pages = Math.max(1, Math.ceil(rows.length / PAGE))
  const view = rows.slice(page * PAGE, page * PAGE + PAGE)
  const allOn = view.length > 0 && view.every((r) => sel.includes(r.id))
  const toggleAll = () =>
    setSel((s) =>
      allOn
        ? s.filter((x) => !view.some((r) => r.id === x))
        : [...new Set([...s, ...view.map((r) => r.id)])]
    )
  return (
    <Page
      title={t('menu.mes-hold-release')}
      description={t('mes.holdrel.hint')}
      actions={
        <Button
          disabled={!canRelease || sel.length === 0}
          onClick={() => setOpen(true)}
          data-testid='open-batch-release'
        >
          <Unlock className='size-4' />
          {t('mes.holdrel.release')} ({sel.length})
        </Button>
      }
    >
      <div className='mb-3 flex flex-wrap items-end gap-3'>
        <div className='grid w-56 gap-1'>
          <Label>{t('mes.holdrel.reason')}</Label>
          <RefSelect
            target='reason_code'
            value={reason}
            filters={{ reason_type: 'hold' }}
            onChange={(id) => {
              setReason(id)
              setPage(0)
            }}
          />
        </div>
        <div className='w-40'>
          <Pick
            id='hold-source'
            label={t('mes.holdrel.source')}
            value={source}
            onChange={(v) => {
              setSource(v)
              setPage(0)
            }}
            options={SOURCES.map((s) => ({
              id: s,
              label: t(`mes.holdrel.src.${s}`),
            }))}
          />
        </div>
        <div className='grid w-56 gap-1'>
          <Label>{t('mes.holdrel.product')}</Label>
          <RefSelect
            target='product'
            value={product}
            onChange={(id) => {
              setProduct(id)
              setPage(0)
            }}
          />
        </div>
      </div>
      <div className='rounded-md border'>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className='w-8'>
                <Checkbox
                  checked={allOn}
                  onCheckedChange={toggleAll}
                  aria-label='all'
                />
              </TableHead>
              <TableHead>{t('mes.holdrel.lot')}</TableHead>
              <TableHead>{t('mes.holdrel.product')}</TableHead>
              <TableHead>{t('mes.holdrel.step')}</TableHead>
              <TableHead>{t('mes.holdrel.reason')}</TableHead>
              <TableHead>{t('mes.holdrel.source')}</TableHead>
              <TableHead>{t('mes.holdrel.heldAt')}</TableHead>
              <TableHead>{t('mes.holdrel.heldBy')}</TableHead>
              <TableHead className='text-right'>
                {t('mes.holdrel.hours')}
              </TableHead>
              <TableHead>{t('mes.holdrel.comment')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {view.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={10}
                  className='h-20 text-center text-muted-foreground'
                >
                  {q.isLoading ? t('common.loading') : t('common.noResults')}
                </TableCell>
              </TableRow>
            )}
            {view.map((r) => (
              <TableRow key={r.id}>
                <TableCell>
                  <Checkbox
                    checked={sel.includes(r.id)}
                    onCheckedChange={(v) =>
                      setSel((s) =>
                        v ? [...s, r.id] : s.filter((x) => x !== r.id)
                      )
                    }
                  />
                </TableCell>
                <TableCell className='font-mono'>
                  <Link
                    to='/$'
                    params={{ _splat: 'mes/lot-console' }}
                    search={{ lot: r.lot_id } as never}
                    className='underline-offset-2 hover:underline'
                  >
                    {r.lot}
                  </Link>
                </TableCell>
                <TableCell>{r.product ?? '—'}</TableCell>
                <TableCell>{r.step_seq ?? '—'}</TableCell>
                <TableCell>
                  {r.reason ? `${r.reason} · ${r.reason_name ?? ''}` : '—'}
                </TableCell>
                <TableCell>
                  {SOURCES.includes(r.source)
                    ? t(`mes.holdrel.src.${r.source}`)
                    : r.source}
                </TableCell>
                <TableCell>
                  {r.held_at ? fmtDateTime(r.held_at) : '—'}
                </TableCell>
                <TableCell>{r.held_by ?? '—'}</TableCell>
                <TableCell className='text-right'>{r.hours ?? '—'}</TableCell>
                <TableCell className='max-w-48 truncate'>
                  {r.comment ?? ''}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className='mt-3 flex items-center justify-end gap-2 text-sm'>
        <span className='text-muted-foreground'>
          {t('mes.holdrel.selected', { n: sel.length })} ·{' '}
          {t('common.total', { count: rows.length })}
        </span>
        <Button
          size='sm'
          variant='outline'
          disabled={page === 0}
          onClick={() => setPage(page - 1)}
        >
          ‹
        </Button>
        <span>
          {page + 1} / {pages}
        </span>
        <Button
          size='sm'
          variant='outline'
          disabled={page + 1 >= pages}
          onClick={() => setPage(page + 1)}
        >
          ›
        </Button>
      </div>
      {open && (
        <ReleaseDialog
          ids={sel}
          onClose={(done) => {
            setOpen(false)
            if (done) setSel([])
          }}
        />
      )}
    </Page>
  )
}

/** 批量释放对话框：释放原因代码 + 备注。 */
function ReleaseDialog({
  ids,
  onClose,
}: {
  ids: string[]
  onClose: (done: boolean) => void
}) {
  const qc = useQueryClient()
  const [reason, setReason] = useState('')
  const [comment, setComment] = useState('')
  const reasons = useQuery({
    queryKey: ['mes', 'reason_code', 'release-options'],
    queryFn: () =>
      mesApi.list('reason_code', { reason_type: 'release', page_size: 100 }),
  })
  const m = useMutation({
    mutationFn: () =>
      execApi.releaseBatch({
        hold_ids: ids,
        reason_id: reason,
        comment: comment || undefined,
      }),
    onSuccess: (r) => {
      const msg = t('mes.holdrel.released', {
        ok: r.released.length,
        bad: r.failed.length,
      })
      if (r.failed.length) toast.warning(msg)
      else toast.success(msg)
      qc.invalidateQueries({ queryKey: ['mes'] })
      onClose(true)
    },
    onError: (e) => toast.error(mesErrorMessage(e, undefined)),
  })
  return (
    <Dialog open onOpenChange={(o) => !o && onClose(false)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('mes.holdrel.release')}</DialogTitle>
          <DialogDescription>
            {t('mes.holdrel.selected', { n: ids.length })}
          </DialogDescription>
        </DialogHeader>
        <Pick
          id='batch-reason'
          label={t('mes.exec.reason')}
          required
          none={false}
          value={reason}
          onChange={setReason}
          options={(reasons.data?.data ?? []).map((r) => ({
            id: String(r.id),
            label: optLabel(r as { code: string; name?: string }),
          }))}
        />
        <div className='grid gap-1'>
          <Label htmlFor='batch-comment'>{t('mes.exec.comment')}</Label>
          <Textarea
            id='batch-comment'
            rows={2}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button disabled={!reason || m.isPending} onClick={() => m.mutate()}>
            {t('mes.holdrel.release')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
