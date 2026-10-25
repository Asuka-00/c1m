/** 阶段作业表单状态：按批次上下文初始化各输入，并组装提交给后端的 StageBody。 */
import { useState } from 'react'
import type { ExecContext, StageBody } from '@/lib/api/mes/execution'
import type { Dc, Scrap } from './types'

/**
 * 批次操作台阶段作业的输入状态。
 *
 * @param cx 批次执行上下文
 * @returns 各输入的值与 setter，以及 `body()`（按当前阶段组装请求体）
 */
export function useStageForm(cx: ExecContext) {
  const lot = cx.lot
  const stage = cx.next_stage
  const xc = cx.exec_ctx as Record<string, unknown>
  const [equipment, setEquipmentId] = useState(String(lot.equipment_id ?? ''))
  // 选定设备后只列该设备可用的配方
  const recipesFor = (eq: string) => {
    const ids = cx.equipment?.find((e) => e.id === eq)?.recipe_ids
    return (cx.recipes ?? []).filter((r) => !ids || ids.includes(r.id))
  }
  const eqRecipes = recipesFor(equipment)
  const [recipe, setRecipe] = useState(
    String(lot.recipe_id ?? (eqRecipes.length === 1 ? eqRecipes[0].id : ''))
  )
  const setEquipment = (eq: string) => {
    setEquipmentId(eq)
    const rs = recipesFor(eq)
    if (!rs.some((r) => r.id === recipe))
      setRecipe(rs.length === 1 ? rs[0].id : '')
  }
  const [chambers, setChambers] = useState<string[]>(
    (xc.chamber_ids as string[]) ?? []
  )
  const eqChambers =
    cx.equipment?.find((e) => e.id === equipment)?.chambers ?? []
  const [eqpRecipe, setEqpRecipe] = useState('')
  const [reticle, setReticle] = useState(
    String(
      xc.reticle_id ?? (cx.reticles?.length === 1 ? cx.reticles[0].id : '')
    )
  )
  const [carrier, setCarrier] = useState<string | null>(
    (lot.carrier_id as string) ?? null
  )
  const [tools, setTools] = useState<Record<string, string>>(() => {
    // 默认：已上机的工具（Track Out）或第一个可用工具
    const ids = (xc.tool_ids as string[]) ?? []
    const out: Record<string, string> = {}
    for (const g of cx.tools ?? []) {
      const cur = g.options.find((o) => ids.includes(o.id))
      const ok = g.options.find((o) => o.status === 'available')
      if (g.fixture) out[g.fixture.id] = (cur ?? ok)?.id ?? ''
    }
    return out
  })
  const [mats, setMats] = useState<string[]>(
    (xc.material_lot_ids as string[]) ?? []
  )
  const [dc, setDc] = useState<Dc>({})
  const [scrap, setScrap] = useState<Scrap[]>([])
  const [rework, setRework] = useState<Record<string, string>>({})
  const [branch, setBranch] = useState(false)
  const [doRework, setDoRework] = useState(!!lot.pending_rework)

  const qty = cx.tracking_level === 'quantity'
  const activeUnits = cx.units.filter((u) => u.status !== 'scrapped')
  const body = (): StageBody => {
    const b: StageBody = {}
    if (stage === 'move_in' || stage === 'track_in')
      b.equipment_id = equipment || null
    if (stage === 'track_in') {
      b.recipe_id = recipe || null
      b.eqp_recipe = eqpRecipe.trim() || null
      b.reticle_id = reticle || null
      b.carrier_id = carrier
      b.tool_ids = Object.values(tools).filter(Boolean)
      b.chamber_ids = chambers.filter((c) => eqChambers.some((x) => x.id === c))
      b.material_lot_ids = mats
    }
    if (stage === 'track_out') {
      b.material_lot_ids = mats
      b.dc = Object.entries(dc)
        .filter(([, v]) => v !== '' && !Number.isNaN(Number(v)))
        .map(([k, v]) => {
          const [item, unit, site] = k.split('|')
          return {
            measurement_item_id: item,
            unit_id: unit || null,
            site_no: Number(site),
            value: Number(v),
          }
        })
      b.scrap = scrap
        .filter((s) => s.reason_id && (s.unit_id || Number(s.qty) > 0))
        .map((s) =>
          qty
            ? { reason_id: s.reason_id, qty: Number(s.qty) }
            : { reason_id: s.reason_id, unit_id: s.unit_id }
        )
      b.rework_units = Object.entries(rework)
        .filter(([, r]) => r)
        .map(([unit_id, reason_id]) => ({ unit_id, reason_id }))
    }
    if (stage === 'move_out') {
      b.branch = branch
      b.rework = doRework
    }
    return b
  }
  return {
    qty,
    activeUnits,
    eqChambers,
    equipment,
    setEquipment,
    eqRecipes,
    recipe,
    setRecipe,
    chambers,
    setChambers,
    eqpRecipe,
    setEqpRecipe,
    reticle,
    setReticle,
    carrier,
    setCarrier,
    tools,
    setTools,
    mats,
    setMats,
    dc,
    setDc,
    scrap,
    setScrap,
    rework,
    setRework,
    branch,
    setBranch,
    doRework,
    setDoRework,
    body,
  }
}

export type StageForm = ReturnType<typeof useStageForm>
