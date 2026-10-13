/** 设备看板：展开显示腔体 E10 状态，可逐个改状态。 */
import { t } from '@/i18n'
import type { E10Unit } from '@/lib/api/mes/equipment'
import { Button } from '@/components/ui/button'

/**
 * 一台设备的腔体状态列表。
 *
 * @param main - 主设备编码
 * @param chambers - 腔体及其 E10 状态
 * @param canChange - 是否有改 E10 状态的权限
 * @param onChange - 点击“改状态”的回调
 */
export function ChamberStates({
  main,
  chambers,
  canChange,
  onChange,
}: {
  main: string
  chambers: E10Unit[]
  canChange: boolean
  onChange: (c: E10Unit) => void
}) {
  return (
    <div className='rounded-md border p-3' data-testid={`chambers-${main}`}>
      <div className='mb-2 text-sm font-medium'>
        {t('mes.eqp.chambersOf', { code: main })}
      </div>
      <ul className='space-y-1.5 text-sm'>
        {chambers.map((c) => (
          <li key={c.id} className='flex items-center gap-2'>
            <span
              className='size-2.5 rounded-full'
              style={{ background: c.state?.color ?? '#9ca3af' }}
            />
            <span className='font-mono'>{c.code}</span>
            <span className='text-muted-foreground'>
              {c.state ? `${c.state.code} · ${c.state.name}` : '—'}
            </span>
            <Button
              size='sm'
              variant='ghost'
              className='ms-auto'
              disabled={!canChange || c.next.length === 0}
              onClick={() => onChange(c)}
              data-testid={`e10-${c.code}`}
            >
              {t('mes.eqp.changeState')}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  )
}
