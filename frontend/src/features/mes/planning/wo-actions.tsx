/** 工单行操作与开批进度。 */
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
import { type MesRow } from '@/lib/api/mes/common'
import { woApi } from '@/lib/api/mes/planning'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ConfirmDialog } from '@/components/crud'
import { IconButton } from '@/components/icon-button'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesEntity, useMesMeta } from '@/features/mes/common/use-mes-meta'

/** 动作 -> 可用的工单状态（与后端 mes/planning/service.py 一致） */
const ACTIONS: [string, string[]][] = [
  ['release', ['draft']],
  ['hold', ['released', 'in_progress']],
  ['resume', ['on_hold']],
  ['complete', ['in_progress']],
  ['close', ['completed']],
  ['cancel', ['draft', 'released']],
]

/** 工单行操作：生命周期迁移、开批、撤销开批。 */
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
        <IconButton
          label={t('mes.wo.action.release')}
          variant='ghost'
          onClick={() => setConfirm('release')}
        >
          <Send className='size-4' />
        </IconButton>
      )}
      {canStart && startable && (
        <IconButton
          label={t('mes.wo.startLots')}
          variant='ghost'
          onClick={() =>
            nav({
              to: '/$',
              params: { _splat: 'mes/lot-start' },
              search: { wo: row.id } as never,
            })
          }
        >
          <PlayCircle className='size-4' />
        </IconButton>
      )}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <IconButton label={t('mes.wo.actions')} variant='ghost'>
            <MoreHorizontal className='size-4' />
          </IconButton>
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

/** "已开批 / 计划数" 进度条（超投显示为琥珀色）。 */
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
