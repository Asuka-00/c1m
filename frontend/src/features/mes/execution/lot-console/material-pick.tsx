/** 物料批次勾选（Track In / Track Out 共用）。 */
import { t } from '@/i18n'
import type { ExecContext } from '@/lib/api/mes/execution'
import { decimalText } from '@/lib/decimal'
import { Checkbox } from '@/components/ui/checkbox'
import { enumLabel } from '@/features/mes/common/labels'

export function MaterialPick({
  cx,
  mats,
  setMats,
}: {
  cx: ExecContext
  mats: string[]
  setMats: (v: string[]) => void
}) {
  if (!cx.materials?.length) return null
  return (
    <div className='space-y-2'>
      <p className='text-sm font-medium'>{t('mes.exec.materials')}</p>
      {cx.materials.map((m) => (
        <div key={m.material_id} className='rounded-md border p-2 text-sm'>
          <div className='font-medium'>
            {m.material}: {decimalText(m.need)} {m.uom ?? ''}{' '}
            <span className='text-xs text-muted-foreground'>
              ({enumLabel('qty_basis', m.basis)})
            </span>
          </div>
          {m.options.length === 0 && (
            <p className='text-destructive'>{t('mes.exec.noMaterial')}</p>
          )}
          {m.options.map((o) => (
            <label key={o.id} className='flex items-center gap-2'>
              <Checkbox
                checked={mats.includes(o.id)}
                onCheckedChange={(v) =>
                  setMats(v ? [...mats, o.id] : mats.filter((x) => x !== o.id))
                }
              />
              {o.code} · {decimalText(o.qty)} · {o.location ?? ''}{' '}
              {o.expiry && (
                <span className='text-muted-foreground'>({o.expiry})</span>
              )}
            </label>
          ))}
          <p className='text-xs text-muted-foreground'>{t('mes.exec.fefo')}</p>
        </div>
      ))}
    </div>
  )
}
