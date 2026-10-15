/** MES 通用表格的单元格渲染。 */
import { fmtDateTime, t } from '@/i18n'
import type { MesEntity, MesRow } from '@/lib/api/mes/common'
import { Badge } from '@/components/ui/badge'
import { enumLabel } from './labels'
import { RefLink } from './ref-link'

/**
 * 按字段类型渲染单元格（枚举标签、布尔、日期、引用标签、实体专用渲染器）。
 *
 * @param e - 实体元数据
 * @param row - 行数据
 * @param f - 字段元数据
 */
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
      return (
        <RefLink
          target={f.ref!}
          id={String(v)}
          label={String(row[`${f.name}_label`] ?? v)}
        />
      )
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
    case 'datetime':
      return fmtDateTime(String(v))
    default:
      return name === 'code' ? (
        <span className='font-medium'>{String(v)}</span>
      ) : (
        String(v)
      )
  }
}
