import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { t } from '@/i18n'
import {
  CircleCheck,
  MoreHorizontal,
  PlayCircle,
  Send,
  Undo2,
} from 'lucide-react'
import { toast } from 'sonner'
import { woApi, type MesRow } from '@/lib/api/mes'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ConfirmDialog } from '@/components/crud'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesEntity, useMesMeta } from '@/features/mes/common/use-mes-meta'

/** action -> statuses it is offered in (mirrors app/mes/wo.py) */
const ACTIONS: [string, string[]][] = [
  ['release', ['draft']],
  ['hold', ['released', 'in_progress']],
  ['resume', ['on_hold']],
  ['complete', ['in_progress']],
  ['close', ['completed']],
  ['cancel', ['draft', 'released']],
]

/** Work-order row actions: lifecycle transitions, start lots, undo start. */
export function WoActions({ row }: { row: MesRow }) {
  const qc = useQueryClient()
  const nav = useNavigate()
  const { data: meta } = useMesMeta()
  const { entity } = useMesEntity('work_order')
  const perms = meta?.perms ?? []
  const [confirm, setConfirm] = useState<string | null>(null)
  const st = String(row.wo_status)
  const done = () => {
    qc.invalidateQueries({ queryKey: ['mes'] })
    setConfirm(null)
  }
  const onError = (e: unknown) => toast.error(mesErrorMessage(e, entity))
  const act = useMutation({
    mutationFn: (a: string) => woApi.transition(row.id, a),
    onSuccess: (_r, a) => {
      toast.success(t(`mes.wo.done.${a}`))
      done()
    },
    onError,
  })
  const undo = useMutation({
    mutationFn: () => woApi.undo(row.id),
    onSuccess: (r) => {
      toast.success(t('mes.wo.undone', { count: r.undone }))
      done()
    },
    onError,
  })
  const canRelease = perms.includes('mes.wo:release')
  const canStart = perms.includes('mes.lot:start')
  const startable = ['released', 'in_progress'].includes(st)
  const offered = ACTIONS.filter(([, from]) => from.includes(st))
  if (!canRelease && !canStart) return null
  return (
    <>
      {canRelease && st === 'draft' && (
        <Button
          size='icon'
          variant='ghost'
          title={t('mes.wo.action.release')}
          aria-label={t('mes.wo.action.release')}
          onClick={() => setConfirm('release')}
        >
          <Send className='size-4' />
        </Button>
      )}
      {canStart && startable && (
        <Button
          size='icon'
          variant='ghost'
          title={t('mes.wo.startLots')}
          aria-label={t('mes.wo.startLots')}
          onClick={() =>
            nav({
              to: '/$',
              params: { _splat: 'mes/lot-start' },
              search: { wo: row.id } as never,
            })
          }
        >
          <PlayCircle className='size-4' />
        </Button>
      )}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button size='icon' variant='ghost' aria-label={t('mes.wo.actions')}>
            <MoreHorizontal className='size-4' />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align='end'>
          {canRelease &&
            offered.map(([a]) => (
              <DropdownMenuItem key={a} onClick={() => setConfirm(a)}>
                {a === 'complete' && <CircleCheck className='size-4' />}
                {t(`mes.wo.action.${a}`)}
              </DropdownMenuItem>
            ))}
          {canStart && startable && Number(row.started_qty) > 0 && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setConfirm('undo')}>
                <Undo2 className='size-4' />
                {t('mes.wo.undoStart')}
              </DropdownMenuItem>
            </>
          )}
          {!offered.length && !(canStart && startable) && (
            <DropdownMenuItem disabled>
              {t('mes.wo.noActions')}
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={
          confirm
            ? t(
                confirm === 'undo'
                  ? 'mes.wo.undoStart'
                  : `mes.wo.action.${confirm}`
              )
            : ''
        }
        desc={
          confirm
            ? t(
                confirm === 'undo'
                  ? 'mes.wo.confirm.undo'
                  : `mes.wo.confirm.${confirm}`,
                { code: row.code }
              )
            : ''
        }
        destructive={confirm === 'cancel' || confirm === 'undo'}
        confirmText={t('mes.wo.confirmBtn')}
        handleConfirm={() =>
          confirm === 'undo' ? undo.mutate() : confirm && act.mutate(confirm)
        }
      />
    </>
  )
}

/** "started / planned" with a progress bar (over-start shown in amber). */
export function WoProgress({ row }: { row: MesRow }) {
  const started = Number(row.started_qty ?? 0)
  const planned = Number(row.planned_qty ?? 0) || 1
  const pct = Math.min(100, (started / planned) * 100)
  return (
    <div
      className='flex min-w-28 items-center gap-2'
      title={`${started} / ${planned}`}
    >
      <div className='h-1.5 flex-1 overflow-hidden rounded bg-muted'>
        <div
          className={
            started > planned ? 'h-full bg-amber-500' : 'h-full bg-primary'
          }
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className='text-xs tabular-nums'>
        {started}/{Number(row.planned_qty ?? 0)}
      </span>
    </div>
  )
}
