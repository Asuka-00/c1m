/** 来料明细行操作：IQC 判定（合格 / 不合格）。 */
import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Check, X } from 'lucide-react'
import { toast } from 'sonner'
import { type MesRow } from '@/lib/api/mes/common'
import { docApi } from '@/lib/api/mes/warehouse'
import { ConfirmDialog } from '@/components/crud'
import { IconButton } from '@/components/icon-button'
import { mesErrorMessage } from '@/features/mes/common/required'
import { useMesEntity, useMesMeta } from '@/features/mes/common/use-mes-meta'

const RESULTS = [
  ['pass', Check],
  ['fail', X],
] as const

/** 已确认收料且尚未判定的明细行显示 IQC 合格 / 不合格按钮（需 `mes.wh:confirm`）。 */
export function IqcActions({ row }: { row: MesRow }) {
  const qc = useQueryClient()
  const { data: meta } = useMesMeta()
  const { entity } = useMesEntity('material_receipt_line')
  const [result, setResult] = useState<string | null>(null)
  const run = useMutation({
    mutationFn: (r: string) => docApi.iqc(row.id, r),
    onSuccess: (_d, r) => {
      toast.success(t(`mes.inbound.iqc.done.${r}`))
      qc.invalidateQueries({ queryKey: ['mes'] })
      setResult(null)
    },
    onError: (e: unknown) => toast.error(mesErrorMessage(e, entity)),
  })
  if (
    row.iqc_result !== 'pending' ||
    !row.material_lot_id ||
    !meta?.perms.includes('mes.wh:confirm')
  )
    return null
  return (
    <>
      {RESULTS.map(([r, Icon]) => (
        <IconButton
          key={r}
          label={t(`mes.inbound.iqc.${r}`)}
          variant='ghost'
          onClick={() => setResult(r)}
        >
          <Icon className='size-4' />
        </IconButton>
      ))}
      <ConfirmDialog
        open={!!result}
        onOpenChange={(o) => !o && setResult(null)}
        title={result ? t(`mes.inbound.iqc.${result}`) : ''}
        desc={t('mes.inbound.iqc.confirm', {
          result: result ? t(`mes.inbound.iqc.${result}`) : '',
        })}
        destructive={result === 'fail'}
        confirmText={t('mes.doc.confirmBtn')}
        handleConfirm={() => result && run.mutate(result)}
      />
    </>
  )
}
