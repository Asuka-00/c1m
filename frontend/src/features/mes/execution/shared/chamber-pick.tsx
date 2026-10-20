import { useTranslation } from 'react-i18next'
import type { EqpOpt } from '@/lib/api/mes/execution'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'

/**
 * Track In 腔体多选（显示各腔体当前 E10 状态）；设备无腔体时不渲染。
 *
 * @param options - 所选设备下的腔体候选
 * @param value - 已选腔体 id
 * @param onChange - 选择变化回调
 */
export function ChamberPick({
  options,
  value,
  onChange,
}: {
  options: EqpOpt[]
  value: string[]
  onChange: (v: string[]) => void
}) {
  const { t } = useTranslation()
  if (!options.length) return null
  return (
    <div className='space-y-2' data-testid='chambers'>
      <Label>{t('mes.exec.chambers')}</Label>
      <div className='flex flex-wrap gap-3'>
        {options.map((c) => (
          <label key={c.id} className='flex items-center gap-1.5 text-sm'>
            <Checkbox
              aria-label={c.code}
              checked={value.includes(c.id)}
              onCheckedChange={(v) =>
                onChange(v ? [...value, c.id] : value.filter((x) => x !== c.id))
              }
            />
            <span
              className='inline-block size-2 rounded-full'
              style={{ background: c.color ?? '#999' }}
            />
            <span className='font-mono'>{c.code}</span>
            <span className='text-xs text-muted-foreground'>{c.state}</span>
          </label>
        ))}
      </div>
    </div>
  )
}
