import { t } from '@/i18n'
import type { MesEntity, MesRow } from '@/lib/api/mes'
import { Badge } from '@/components/ui/badge'
import { enumLabel } from './labels'

export function cellValue(
  e: MesEntity,
  row: MesRow,
  name: string
): React.ReactNode {
  const f = e.fields.find((x) => x.name === name)
  if (!f) return null
  const v = row[f.column]
  if (v == null || v === '')
    return <span className='text-muted-foreground'>—</span>
  switch (f.type) {
    case 'ref':
      return String(row[`${f.name}_label`] ?? v)
    case 'enum':
      return <Badge variant='outline'>{enumLabel(f.enum!, String(v))}</Badge>
    case 'bool':
      return v ? t('common.yes') : t('common.no')
    case 'json':
      return (
        <code className='line-clamp-2 max-w-72 text-xs break-all'>
          {JSON.stringify(v)}
        </code>
      )
    case 'time':
      return String(v).slice(0, 5)
    default:
      return name === 'code' ? (
        <span className='font-medium'>{String(v)}</span>
      ) : (
        String(v)
      )
  }
}
