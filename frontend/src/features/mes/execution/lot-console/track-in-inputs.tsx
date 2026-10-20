/** Track In 阶段输入：配方、设备配方、光罩、载具、治具与物料。 */
import { t } from '@/i18n'
import type { ExecContext } from '@/lib/api/mes/execution'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { enumLabel, optLabel } from '@/features/mes/common/labels'
import { RefSelect } from '@/features/mes/common/ref-select'
import { Pick } from '../shared/exec-parts'
import { MaterialPick } from './material-pick'

export function TrackInInputs(p: {
  cx: ExecContext
  recipe: string
  setRecipe: (v: string) => void
  eqpRecipe: string
  setEqpRecipe: (v: string) => void
  reticle: string
  setReticle: (v: string) => void
  carrier: string | null
  setCarrier: (v: string | null) => void
  tools: Record<string, string>
  setTools: (v: Record<string, string>) => void
  mats: string[]
  setMats: (v: string[]) => void
}) {
  const { cx } = p
  return (
    <div className='space-y-3'>
      <div className='grid gap-3 sm:grid-cols-2'>
        <Pick
          id='ex-recipe'
          label={t('mes.exec.recipe')}
          required={(cx.recipes?.length ?? 0) > 0}
          value={p.recipe}
          onChange={p.setRecipe}
          options={(cx.recipes ?? []).map((r) => ({
            id: r.id,
            label: `${optLabel(r)} v${r.version} (${enumLabel('status', r.status)})`,
          }))}
        />
        <div className='grid gap-1'>
          <Label htmlFor='ex-eqp-recipe'>{t('mes.exec.eqpRecipe')}</Label>
          <Input
            id='ex-eqp-recipe'
            placeholder={t('mes.exec.eqpRecipeHint')}
            value={p.eqpRecipe}
            onChange={(e) => p.setEqpRecipe(e.target.value)}
          />
        </div>
        {(cx.reticles?.length ?? 0) > 0 && (
          <Pick
            id='ex-reticle'
            label={t('mes.exec.reticle')}
            required
            value={p.reticle}
            onChange={p.setReticle}
            options={(cx.reticles ?? []).map((r) => ({
              id: r.id,
              label: `${r.code} (${enumLabel('asset_status', r.status)})`,
            }))}
          />
        )}
        <div className='grid gap-1'>
          <Label>{t('mes.exec.carrier')}</Label>
          <RefSelect
            target='carrier'
            value={p.carrier}
            label={String(cx.lot.carrier_label ?? '') || null}
            onChange={(id) => p.setCarrier(id)}
          />
        </div>
        {(cx.tools ?? []).map((g) =>
          g.fixture ? (
            <Pick
              key={g.fixture.id}
              id={`ex-tool-${g.fixture.code}`}
              label={`${t('mes.exec.tool')} · ${g.fixture.code}`}
              required
              value={p.tools[g.fixture.id] ?? ''}
              onChange={(v) => p.setTools({ ...p.tools, [g.fixture!.id]: v })}
              options={g.options.map((o) => ({
                id: o.id,
                label: `${o.code} · ${o.usage}/${o.max ?? '∞'} · ${enumLabel('tool_status', o.status)}`,
              }))}
            />
          ) : null
        )}
      </div>
      <MaterialPick cx={cx} mats={p.mats} setMats={p.setMats} />
    </div>
  )
}
