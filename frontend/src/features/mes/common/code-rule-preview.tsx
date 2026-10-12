import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Loader2 } from 'lucide-react'
import { mesApi, type MesRow } from '@/lib/api/mes/common'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

/** Next codes of a rule (preview only; nothing is reserved). */
export function CodeRulePreview({ row }: { row: MesRow }) {
  const [lot, setLot] = useState('LT2610A001')
  const needsLot = String(row.pattern ?? '').includes('{LOT}')
  const { data, isLoading, error } = useQuery({
    queryKey: [
      'mes',
      'code_rule',
      'preview',
      row.id,
      row.pattern,
      needsLot && lot,
    ],
    queryFn: () =>
      mesApi.codePreview(row.id, 5, needsLot ? { LOT: lot } : undefined),
  })
  return (
    <div className='space-y-3 pt-2'>
      <p className='text-sm text-muted-foreground'>
        {t('mes.pattern')}: <code>{String(row.pattern)}</code>
      </p>
      {needsLot && (
        <div className='max-w-xs space-y-1.5'>
          <Label htmlFor='cr-lot'>{t('mes.sampleLot')}</Label>
          <Input
            id='cr-lot'
            value={lot}
            onChange={(e) => setLot(e.target.value)}
          />
        </div>
      )}
      {isLoading ? (
        <Loader2 className='animate-spin' />
      ) : error ? (
        <p className='text-sm text-destructive'>{String(error)}</p>
      ) : (
        <ol
          className='list-decimal space-y-1 ps-6 font-mono text-sm'
          data-testid='code-preview'
        >
          {data?.codes.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ol>
      )}
      <p className='text-xs text-muted-foreground'>{t('mes.previewHint')}</p>
    </div>
  )
}
