/** 工程变更单行操作：发布 / 取消，并显示生效结果。 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Ban, Send } from 'lucide-react'
import { toast } from 'sonner'
import type { MesRow } from '@/lib/api/mes/common'
import { changeApi } from '@/lib/api/mes/process'
import { ConfirmDialog } from '@/components/crud'
import { IconButton } from '@/components/icon-button'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesEntity, useMesMeta } from '@/features/mes/common/use-mes-meta'

type Act = 'release' | 'cancel'

/** 变更单行操作（草稿可发布；未生效可取消）。 */
export function ChangeActions({ row }: { row: MesRow }) {
  const qc = useQueryClient()
  const { data: meta } = useMesMeta()
  const { entity } = useMesEntity('change_order')
  const [confirm, setConfirm] = useState<Act | null>(null)
  const st = String(row.ecn_status)
  const m = useMutation({
    mutationFn: (a: Act) => changeApi.act(row.id, a),
    onSuccess: (r) => {
      toast.success(t(`mes.ecn.done.${String(r.ecn_status)}`))
      qc.invalidateQueries({ queryKey: ['mes'] })
      setConfirm(null)
    },
    onError: (e) => toast.error(mesErrorMessage(e, entity)),
  })
  if (!(meta?.perms ?? []).includes('mes.process:write')) return null
  return (
    <>
      {st === 'draft' && (
        <IconButton
          label={t('mes.ecn.release')}
          variant='ghost'
          onClick={() => setConfirm('release')}
        >
          <Send className='size-4' />
        </IconButton>
      )}
      {(st === 'draft' || st === 'released') && (
        <IconButton
          label={t('mes.ecn.cancel')}
          variant='ghost'
          onClick={() => setConfirm('cancel')}
        >
          <Ban className='size-4' />
        </IconButton>
      )}
      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm ? t(`mes.ecn.${confirm}`) : ''}
        desc={
          confirm ? t(`mes.ecn.confirm.${confirm}`, { code: row.code }) : ''
        }
        destructive={confirm === 'cancel'}
        confirmText={t('mes.wo.confirmBtn')}
        handleConfirm={() => confirm && m.mutate(confirm)}
      />
    </>
  )
}

/** 生效结果：新版本、改指引用数、切换 / 沿用旧版的在制批次。 */
export function ChangeResult({ row }: { row: MesRow }) {
  const r = row.result as {
    version: number
    refs: number
    switched: string[]
    kept: string[]
  } | null
  if (!r) return null
  return (
    <div className='space-y-1 p-3 text-sm'>
      <div>{t('mes.ecn.result', { v: r.version, n: r.refs })}</div>
      <div>
        {t('mes.ecn.switched')}: {r.switched.join(', ') || '—'}
      </div>
      <div>
        {t('mes.ecn.kept')}: {r.kept.join(', ') || '—'}
      </div>
    </div>
  )
}
