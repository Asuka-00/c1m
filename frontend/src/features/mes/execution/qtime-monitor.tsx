/** Q-Time 监控页面：等待中批次的计时、剩余时间与超时状态，可立即执行超时扫描。 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { fmtDateTime, t } from '@/i18n'
import { RefreshCw, ScanSearch } from 'lucide-react'
import { toast } from 'sonner'
import { useTenantKey } from '@/lib/api/hooks'
import { execApi } from '@/lib/api/mes/execution'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Page } from '@/components/crud'
import { mesErrorMessage } from '@/features/mes/common/required'

const PAGE = 20

/** Q-Time 监控。 */
export default function QtimeMonitor() {
  const tk = useTenantKey()
  const qc = useQueryClient()
  const [page, setPage] = useState(0)
  const q = useQuery({
    queryKey: ['mes', 'exec', tk, 'qtime-monitor'],
    queryFn: execApi.qtimeMonitor,
    refetchInterval: 60_000,
  })
  const sweep = useMutation({
    mutationFn: execApi.qtimeSweep,
    onSuccess: (r) => {
      toast.success(
        t('mes.qtime.swept', { checked: r.checked, acted: r.actions.length })
      )
      qc.invalidateQueries({ queryKey: ['mes'] })
    },
    onError: (e) => toast.error(mesErrorMessage(e, undefined)),
  })
  const rows = q.data ?? []
  const pages = Math.max(1, Math.ceil(rows.length / PAGE))
  const view = rows.slice(page * PAGE, page * PAGE + PAGE)
  return (
    <Page
      title={t('menu.mes-qtime-monitor')}
      description={t('mes.qtime.hint')}
      actions={
        <>
          <Button variant='outline' onClick={() => q.refetch()}>
            <RefreshCw className='size-4' />
            {t('mes.qtime.refresh')}
          </Button>
          <Button
            onClick={() => sweep.mutate()}
            disabled={sweep.isPending}
            data-testid='qtime-sweep'
          >
            <ScanSearch className='size-4' />
            {t('mes.qtime.sweep')}
          </Button>
        </>
      }
    >
      <div className='rounded-md border'>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('mes.qtime.lot')}</TableHead>
              <TableHead>{t('mes.qtime.step')}</TableHead>
              <TableHead>{t('mes.qtime.rule')}</TableHead>
              <TableHead>{t('mes.qtime.since')}</TableHead>
              <TableHead className='text-right'>
                {t('mes.qtime.elapsed')}
              </TableHead>
              <TableHead className='text-right'>{t('mes.qtime.max')}</TableHead>
              <TableHead className='text-right'>
                {t('mes.qtime.remaining')}
              </TableHead>
              <TableHead>{t('mes.qtime.action')}</TableHead>
              <TableHead>{t('mes.qtime.state')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {view.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={9}
                  className='h-20 text-center text-muted-foreground'
                >
                  {q.isLoading ? t('common.loading') : t('common.noResults')}
                </TableCell>
              </TableRow>
            )}
            {view.map((r) => (
              <TableRow key={`${r.lot_id}-${r.rule}`}>
                <TableCell>
                  <Link
                    to='/$'
                    params={{ _splat: 'mes/lot-console' }}
                    search={{ lot: r.lot_id } as never}
                    className='font-mono underline-offset-2 hover:underline'
                  >
                    {r.lot}
                  </Link>
                </TableCell>
                <TableCell>{r.step_seq}</TableCell>
                <TableCell className='font-mono'>{r.rule}</TableCell>
                <TableCell>{fmtDateTime(r.since)}</TableCell>
                <TableCell className='text-right'>{r.minutes}</TableCell>
                <TableCell className='text-right'>
                  {r.max_minutes ?? '—'}
                </TableCell>
                <TableCell
                  className={
                    r.exceeded
                      ? 'text-right font-medium text-destructive'
                      : 'text-right'
                  }
                >
                  {r.remaining ?? '—'}
                </TableCell>
                <TableCell>{t(`mes.qtime.act.${r.action}`)}</TableCell>
                <TableCell>
                  {r.on_hold ? (
                    <Badge variant='secondary'>{t('mes.qtime.held')}</Badge>
                  ) : r.exceeded ? (
                    <Badge variant='destructive'>
                      {t('mes.qtime.exceeded')}
                    </Badge>
                  ) : (
                    <Badge variant='outline'>{t('mes.qtime.ok')}</Badge>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <div className='mt-3 flex items-center justify-end gap-2 text-sm'>
        <span className='text-muted-foreground'>
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
    </Page>
  )
}
