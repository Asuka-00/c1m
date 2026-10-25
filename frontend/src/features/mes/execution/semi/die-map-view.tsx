/** 芯片级晶圆图：按坐标着色的芯片网格与 Bin 图例。 */
import { useQuery } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { useTenantKey } from '@/lib/api/hooks'
import { semiApi, type DieMapDetail } from '@/lib/api/mes/semi'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { enumLabel } from '@/features/mes/common/labels'
import { binColor } from './semi-utils'

/** 芯片网格（SVG，每颗芯片一个方格，y 轴向下）。 */
export function DieGrid({ map }: { map: DieMapDetail }) {
  const xs = map.dies.map((d) => d[0])
  const ys = map.dies.map((d) => d[1])
  const x0 = Math.min(...xs)
  const y0 = Math.min(...ys)
  const colors = new Map(
    map.legend.map((b) => [b.bin, binColor(map.legend, b.bin)])
  )
  return (
    <svg
      viewBox={`0 0 ${map.cols} ${map.rows}`}
      className='aspect-square w-full max-w-md rounded-full border bg-muted/40'
      role='img'
      aria-label={map.unit}
    >
      {map.dies.map(([x, y, b]) => (
        <rect
          key={`${x},${y}`}
          x={x - x0 + 0.05}
          y={y - y0 + 0.05}
          width={0.9}
          height={0.9}
          fill={colors.get(String(b))}
        >
          <title>{`(${x}, ${y}) ${b}`}</title>
        </rect>
      ))}
    </svg>
  )
}

/** 晶圆图对话框：网格 + 良率 + 图例。 */
export function DieMapDialog({
  mapId,
  onClose,
}: {
  mapId: string | null
  onClose: () => void
}) {
  const tk = useTenantKey()
  const q = useQuery({
    queryKey: ['mes', 'die-map', tk, mapId],
    queryFn: () => semiApi.dieMap(mapId!),
    enabled: !!mapId,
  })
  const m = q.data
  return (
    <Dialog open={!!mapId} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>
            {m
              ? `${m.unit} · ${enumLabel('die_map_kind', m.test_kind ?? '')}`
              : t('mes.entity.die_map')}
          </DialogTitle>
        </DialogHeader>
        {m && (
          <div className='grid gap-4 sm:grid-cols-[1fr_12rem]'>
            <DieGrid map={m} />
            <div className='space-y-3 text-sm'>
              <div>
                <div className='text-2xl font-semibold tabular-nums'>
                  {m.yield_pct}%
                </div>
                <div className='text-muted-foreground'>
                  {t('mes.semi.goodOfGross', { good: m.good, gross: m.gross })}
                </div>
                {m.at && (
                  <div className='text-xs text-muted-foreground'>
                    {fmtDateTime(m.at)}
                  </div>
                )}
              </div>
              <ul className='space-y-1'>
                {m.legend.map((b) => (
                  <li key={b.bin} className='flex items-center gap-2'>
                    <span
                      className='size-3 shrink-0 rounded-sm'
                      style={{ background: binColor(m.legend, b.bin) }}
                    />
                    <span className='font-mono'>{b.bin}</span>
                    <span className='truncate text-muted-foreground'>
                      {b.name}
                    </span>
                    <span className='ms-auto tabular-nums'>{b.count}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
