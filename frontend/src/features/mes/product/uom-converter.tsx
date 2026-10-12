import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fmtNumber, t } from '@/i18n'
import { errorMessage } from '@/lib/api/client'
import { mesApi, type MesRow } from '@/lib/api/mes'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { rowLabel } from '@/features/mes/common/labels'
import { RefSelect } from '@/features/mes/common/ref-select'

/** Convert from this unit to another one (direct / inverse / multi-hop). */
export function UomConverter({ row }: { row: MesRow }) {
  const [value, setValue] = useState('1')
  const [to, setTo] = useState<{ id: string | null; label: string | null }>({
    id: null,
    label: null,
  })
  const n = Number(value)
  const { data, error } = useQuery({
    queryKey: ['mes', 'uom', 'convert', row.id, to.id, n],
    queryFn: () => mesApi.convert(row.id, to.id!, n),
    enabled: !!to.id && Number.isFinite(n),
    retry: false,
  })
  return (
    <div className='grid max-w-xl gap-3 pt-2 sm:grid-cols-2'>
      <div className='space-y-1.5'>
        <Label htmlFor='uom-v'>
          {t('mes.convertValue', { unit: rowLabel(row) })}
        </Label>
        <Input
          id='uom-v'
          type='number'
          step='any'
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
      </div>
      <div className='space-y-1.5'>
        <Label>{t('mes.convertTo')}</Label>
        <RefSelect
          target='uom'
          value={to.id}
          label={to.label}
          onChange={(id, label) => setTo({ id, label })}
        />
      </div>
      <p
        className='text-lg font-semibold sm:col-span-2'
        data-testid='uom-result'
      >
        {error
          ? errorMessage(error)
          : data
            ? `${fmtNumber(n)} → ${fmtNumber(data.value)} ${to.label ?? ''}`
            : '—'}
      </p>
    </div>
  )
}
