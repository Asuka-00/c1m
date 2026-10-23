/** 仓储单据（领料单 / 出货单 / 来料接收单）行操作：确认、取消。 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { PackageCheck, X } from 'lucide-react'
import { toast } from 'sonner'
import { type MesRow } from '@/lib/api/mes/common'
import { docApi } from '@/lib/api/mes/warehouse'
import { ConfirmDialog } from '@/components/crud'
import { IconButton } from '@/components/icon-button'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesEntity, useMesMeta } from '@/features/mes/common/use-mes-meta'

/** 动作 -> 所需权限（与后端 mes/warehouse 一致）；仅草稿可操作。 */
const ACTIONS = [
  ['confirm', 'mes.wh:confirm', PackageCheck],
  ['cancel', 'mes.wh:write', X],
] as const

/**
 * 单据行操作：草稿状态下显示确认 / 取消按钮。
 *
 * @param entity - 实体编码
 * @param path - 后端路径段（`/mes/<path>/{id}/transition`）
 * @param prefix - 语言包前缀 `mes.<prefix>.action|done|confirm`
 */
export function DocActions({
  row,
  entity,
  path,
  prefix,
}: {
  row: MesRow
  entity: string
  path: string
  prefix: string
}) {
  const qc = useQueryClient()
  const { data: meta } = useMesMeta()
  const { entity: spec } = useMesEntity(entity)
  const perms = meta?.perms ?? []
  const [confirm, setConfirm] = useState<string | null>(null)
  const act = useMutation({
    mutationFn: (a: string) => docApi.transition(path, row.id, a),
    onSuccess: (_r, a) => {
      toast.success(t(`mes.${prefix}.done.${a}`))
      qc.invalidateQueries({ queryKey: ['mes'] })
      setConfirm(null)
    },
    onError: (e: unknown) => toast.error(mesErrorMessage(e, spec)),
  })
  if (row.issue_status !== 'draft') return null
  return (
    <>
      {ACTIONS.filter(([, p]) => perms.includes(p)).map(([a, , Icon]) => (
        <IconButton
          key={a}
          label={t(`mes.${prefix}.action.${a}`)}
          variant='ghost'
          onClick={() => setConfirm(a)}
        >
          <Icon className='size-4' />
        </IconButton>
      ))}
      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm ? t(`mes.${prefix}.action.${confirm}`) : ''}
        desc={
          confirm
            ? t(`mes.${prefix}.confirm.${confirm}`, { code: row.code })
            : ''
        }
        destructive={confirm === 'cancel'}
        confirmText={t('mes.doc.confirmBtn')}
        handleConfirm={() => confirm && act.mutate(confirm)}
      />
    </>
  )
}
