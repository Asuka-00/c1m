import { act } from 'react'
import { describe, expect, it } from 'vitest'
import { renderHook } from 'vitest-browser-react'
import type { ExecContext } from '@/lib/api/mes/execution'
import { useStageForm } from './use-stage-form'

const opt = (id: string) => ({ id, code: id, name: id })

function cx(over: Partial<ExecContext> = {}): ExecContext {
  return {
    lot: { id: 'L1', code: 'LOT1', qty: 25, carrier_id: 'C1' },
    next_stage: 'track_in',
    tracking_level: 'wafer',
    units: [
      { id: 'U1', code: 'W1', status: 'active' },
      { id: 'U2', code: 'W2', status: 'scrapped' },
    ],
    holds: [],
    reasons: {
      hold: [],
      release: [],
      scrap: [opt('S1')],
      rework: [],
      jump: [],
      bonus: [],
    },
    stack: [],
    exec_ctx: {},
    recipes: [{ ...opt('R1'), version: 1, status: 'active' }],
    equipment: [
      {
        ...opt('E1'),
        state: 'SBY',
        category: 'SBY',
        color: null,
        chambers: [
          { ...opt('PM1'), state: 'SBY', category: 'SBY', color: null },
        ],
      },
    ],
    ...over,
  } as unknown as ExecContext
}

describe('useStageForm', () => {
  it('Track In：唯一配方默认选中，过滤不属于所选设备的腔体', async () => {
    const { result } = await renderHook(() => useStageForm(cx()))
    expect(result.current.activeUnits.map((u) => u.id)).toEqual(['U1'])
    await act(async () => {
      result.current.setEquipment('E1')
      result.current.setChambers(['PM1', 'PMX'])
      result.current.setEqpRecipe('  EQR ')
    })
    expect(result.current.body()).toMatchObject({
      equipment_id: 'E1',
      recipe_id: 'R1',
      eqp_recipe: 'EQR',
      carrier_id: 'C1',
      chamber_ids: ['PM1'],
      tool_ids: [],
      material_lot_ids: [],
    })
  })

  it('Track Out：只提交有效的量测值与报废行', async () => {
    const { result } = await renderHook(() =>
      useStageForm(cx({ next_stage: 'track_out' }))
    )
    await act(async () => {
      result.current.setDc({ 'M1|U1|1': '1.5', 'M1|U1|2': '', 'M1||1': 'x' })
      result.current.setScrap([
        { unit_id: 'U1', reason_id: 'S1' },
        { unit_id: 'U2', reason_id: '' },
      ])
      result.current.setRework({ U1: 'RW', U2: '' })
    })
    const b = result.current.body()
    expect(b.equipment_id).toBeUndefined()
    expect(b.dc).toEqual([
      { measurement_item_id: 'M1', unit_id: 'U1', site_no: 1, value: 1.5 },
    ])
    expect(b.scrap).toEqual([{ reason_id: 'S1', unit_id: 'U1' }])
    expect(b.rework_units).toEqual([{ unit_id: 'U1', reason_id: 'RW' }])
  })

  it('Move Out：提交分支与重工选项', async () => {
    const { result } = await renderHook(() =>
      useStageForm(
        cx({ next_stage: 'move_out', lot: { id: 'L1', pending_rework: true } })
      )
    )
    expect(result.current.body()).toEqual({ branch: false, rework: true })
  })
})
