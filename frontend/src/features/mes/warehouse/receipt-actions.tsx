/** 完工入库单行操作：提交、退回、确认入库、取消。 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { MoreHorizontal, PackageCheck, Send } from 'lucide-react'
import { toast } from 'sonner'
import { type MesRow } from '@/lib/api/mes/common'
import { receiptApi } from '@/lib/api/mes/warehouse'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ConfirmDialog } from '@/components/crud'
import { IconButton } from '@/components/icon-button'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesEntity, useMesMeta } from '@/features/mes/common/use-mes-meta'

/** 动作 -> [可用的入库单状态, 所需权限]（与后端 mes/warehouse 一致） */
const ACTIONS: [string, string[], string][] = [
  ['submit', ['draft'], 'mes.wh:write'],
  ['confirm', ['submitted'], 'mes.wh:confirm'],
  ['reject', ['submitted'], 'mes.wh:confirm'],
  ['cancel', ['draft', 'submitted'], 'mes.wh:write'],
]

/** 入库单行操作：常用动作（提交 / 确认）直接显示为按钮，其余放入菜单。 */
export function ReceiptActions({ row }: { row: MesRow }) {
  const qc = useQueryClient()
  const { data: meta } = useMesMeta()
  const { entity } = useMesEntity('receipt')
  const perms = meta?.perms ?? []
  const [confirm, setConfirm] = useState<string | null>(null)
  const st = String(row.receipt_status)
  const act = useMutation({
    mutationFn: (a: string) => receiptApi.transition(row.id, a),
    onSuccess: (_r, a) => {
      toast.success(t(`mes.receipt.done.${a}`))
      qc.invalidateQueries({ queryKey: ['mes'] })
      setConfirm(null)
    },
    onError: (e: unknown) => toast.error(mesErrorMessage(e, entity)),
  })
  const offered = ACTIONS.filter(
    ([, from, p]) => from.includes(st) && perms.includes(p)
  )
  if (!perms.includes('mes.wh:write') && !perms.includes('mes.wh:confirm'))
    return null
  const quick = offered.find(([a]) => a === 'submit' || a === 'confirm')
  return (
    <>
      {quick && (
        <IconButton
          label={t(`mes.receipt.action.${quick[0]}`)}
          variant='ghost'
          onClick={() => setConfirm(quick[0])}
        >
          {quick[0] === 'submit' ? (
            <Send className='size-4' />
          ) : (
            <PackageCheck className='size-4' />
          )}
        </IconButton>
      )}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <IconButton label={t('mes.receipt.actions')} variant='ghost'>
            <MoreHorizontal className='size-4' />
          </IconButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent align='end'>
          {offered.map(([a]) => (
            <DropdownMenuItem key={a} onClick={() => setConfirm(a)}>
              {t(`mes.receipt.action.${a}`)}
            </DropdownMenuItem>
          ))}
          {!offered.length && (
            <DropdownMenuItem disabled>
              {t('mes.receipt.noActions')}
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm ? t(`mes.receipt.action.${confirm}`) : ''}
        desc={
          confirm ? t(`mes.receipt.confirm.${confirm}`, { code: row.code }) : ''
        }
        destructive={confirm === 'cancel'}
        confirmText={t('mes.receipt.confirmBtn')}
        handleConfirm={() => confirm && act.mutate(confirm)}
      />
    </>
  )
}
