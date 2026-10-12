/** 批次类型编号预览面板。 */
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Loader2 } from 'lucide-react'
import { mesApi, type MesRow } from '@/lib/api/mes/common'

/** 该批次类型的下一个批次号及对应晶圆号（仅预览）。 */
export function LotTypePreview({ row }: { row: MesRow }) {
  const lotRule = row.lot_id_rule_id as string | null
  const waferRule = row.wafer_id_rule_id as string | null
  const max = Number(row.max_wafers ?? 25)
  const { data, isLoading } = useQuery({
    queryKey: ['mes', 'lot_type', 'preview', row.id, lotRule, waferRule, max],
    queryFn: async () => {
      const lot = lotRule
        ? (await mesApi.codePreview(lotRule, 1)).codes[0]
        : null
      const wafers =
        waferRule && lot
          ? (
              await mesApi.codePreview(waferRule, Math.min(max, 25), {
                LOT: lot,
              })
            ).codes
          : []
      return { lot, wafers }
    },
  })
  if (!lotRule)
    return (
      <p className='pt-2 text-sm text-muted-foreground'>{t('mes.noLotRule')}</p>
    )
  if (isLoading) return <Loader2 className='animate-spin' />
  return (
    <div className='space-y-3 pt-2'>
      <p className='text-sm'>
        {t('mes.nextLotId')}:{' '}
        <code className='rounded bg-muted px-2 py-1 font-semibold'>
          {data?.lot}
        </code>
      </p>
      {!!data?.wafers.length && (
        <div>
          <p className='mb-2 text-sm text-muted-foreground'>
            {t('mes.waferIds')}
          </p>
          <div
            className='grid grid-cols-3 gap-1 font-mono text-xs sm:grid-cols-5'
            data-testid='wafer-ids'
          >
            {data.wafers.map((w) => (
              <span key={w} className='rounded border px-1.5 py-0.5'>
                {w}
              </span>
            ))}
          </div>
        </div>
      )}
      <p className='text-xs text-muted-foreground'>{t('mes.previewHint')}</p>
    </div>
  )
}
