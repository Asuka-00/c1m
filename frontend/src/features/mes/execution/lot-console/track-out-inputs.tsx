/** Track Out 阶段输入：数据采集、报废 / 重工与物料。 */
import type { ExecContext } from '@/lib/api/mes/execution'
import { DcEntry } from './dc-entry'
import { MaterialPick } from './material-pick'
import { ScrapEntry } from './scrap-entry'
import type { Dc, Scrap } from './types'

export function TrackOutInputs(p: {
  cx: ExecContext
  qty: boolean
  units: ExecContext['units']
  dc: Dc
  setDc: (v: Dc) => void
  scrap: Scrap[]
  setScrap: (v: Scrap[]) => void
  rework: Record<string, string>
  setRework: (v: Record<string, string>) => void
  mats: string[]
  setMats: (v: string[]) => void
}) {
  const { cx } = p
  return (
    <div className='space-y-4'>
      <DcEntry cx={cx} units={p.units} dc={p.dc} setDc={p.setDc} />
      <ScrapEntry
        cx={cx}
        qty={p.qty}
        units={p.units}
        scrap={p.scrap}
        setScrap={p.setScrap}
        rework={p.rework}
        setRework={p.setRework}
      />
      <MaterialPick cx={cx} mats={p.mats} setMats={p.setMats} />
    </div>
  )
}
