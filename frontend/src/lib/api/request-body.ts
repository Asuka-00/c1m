/**
 * 自定义 MES / EAP 接口的请求体白名单（对照后端 be/p2 1a7c0fb 的 pydantic 请求模型）。
 * 后端会给这些接口加 extra=forbid，多带字段 422 unknown_field；API 层统一按模型字段显式挑选，
 * 调用方即使 spread 了整个表单 / 行对象也不会把多余字段发出去。
 */
type Obj = Record<string, unknown>

/** 只保留 keys 中列出的键（值为 undefined 的也去掉）。 */
export function pickBody<T extends object>(
  body: T | null | undefined,
  keys: readonly string[]
): Partial<T> {
  const out: Obj = {}
  if (!body) return out as Partial<T>
  for (const k of keys) {
    const v = (body as Obj)[k]
    if (v !== undefined) out[k] = v
  }
  return out as Partial<T>
}

const pickList = (v: unknown, keys: readonly string[]) =>
  Array.isArray(v) ? v.map((x) => pickBody(x as Obj, keys)) : v

/** 后端请求模型字段（模型名见注释）。 */
export const BODY_KEYS = {
  /** StageIn（进站 / 出站 / 预检 / 放行 override） */
  stage: [
    'equipment_id',
    'recipe_id',
    'eqp_recipe',
    'reticle_id',
    'carrier_id',
    'tool_ids',
    'chamber_ids',
    'material_lot_ids',
    'dc',
    'scrap',
    'rework_units',
    'branch',
    'rework',
    'override',
    'override_reason',
  ],
  dc: ['measurement_item_id', 'unit_id', 'site_no', 'value'],
  scrap: ['reason_id', 'unit_id', 'qty'],
  reworkUnit: ['reason_id', 'unit_id'],
  /** HoldIn / ReleaseIn */
  hold: ['reason_id', 'comment'],
  /** BatchReleaseIn */
  releaseBatch: ['hold_ids', 'reason_id', 'comment'],
  /** SplitIn / SplitChildIn / MergeIn */
  split: ['children', 'comment', 'override', 'override_reason', 'preview'],
  splitChild: ['unit_ids', 'qty', 'carrier_id'],
  merge: [
    'source_lot_ids',
    'comment',
    'override',
    'override_reason',
    'preview',
  ],
  /** JumpIn / AdjustIn / PriorityIn */
  jump: ['to_step_id', 'reason_id', 'comment', 'override', 'override_reason'],
  adjust: [
    'kind',
    'qty',
    'unit_ids',
    'reason_id',
    'comment',
    'override',
    'override_reason',
  ],
  priority: ['priority_id', 'comment', 'override', 'override_reason'],
  /** SortIn / SortSlotIn / CarrierChangeIn / CommentIn */
  sort: ['slots', 'carrier_id', 'comment', 'override', 'override_reason'],
  sortSlot: ['wafer_id', 'slot'],
  carrierChange: ['carrier_id', 'comment'],
  comment: ['comment'],
  /** TransformIn 及子模型 */
  transform: [
    'transform_type',
    'input_lot_ids',
    'outputs',
    'manual_good',
    'reason_id',
    'comment',
  ],
  transformOutput: [
    'product_id',
    'route_id',
    'track_unit_kind',
    'qty',
    'sources',
  ],
  transformSource: ['wafer_id', 'qty'],
  manualGood: ['wafer_id', 'good_qty', 'fail_qty'],
  /** TransformUndoIn */
  transformUndo: ['reason_id', 'comment'],
  /** BinSplitIn 及子模型 */
  binSplit: ['input_lot_ids', 'outputs', 'manual_bins', 'reason_id', 'comment'],
  binOutput: ['bin_codes', 'product_id', 'route_id'],
  manualBins: ['wafer_id', 'bins'],
  binQty: ['bin_code', 'qty'],
  /** ShiftLogIn */
  shiftLog: ['shift_date', 'shift_id', 'area_id', 'summary', 'open_items'],
  /** E10In / PmIn / AlarmClearIn / MountIn（equipment）/ QualResultIn */
  e10: ['to_state_id', 'reason_id', 'comment'],
  pm: ['equipment_id', 'result', 'comment'],
  alarmClear: ['cleared_at', 'comment', 'external_event_id'],
  mount: [
    'port_code',
    'material_lot_id',
    'material_lot_code',
    'mounted_at',
    'external_event_id',
    'comment',
  ],
  qualResult: ['result', 'comment'],
  /** PlanIn / LotIn / UndoIn */
  plan: ['lot_size', 'qty'],
  startLot: [
    'qty',
    'carrier_id',
    'slots',
    'source_ref',
    'wafer_sources',
    'customer_lot_no',
    'ownership',
    'customer_id',
  ],
  /** ImportIn / MapImportIn */
  binSetImport: ['content', 'file_name'],
  mapImport: ['content', 'file_name', 'lot_id', 'equipment_id', 'operation_id'],
  /** SubscriptionIn（通知订阅新建 / 更新，be/p2 56474fe platform/notification/router.py） */
  subscription: [
    'name',
    'event_type',
    'role_ids',
    'user_ids',
    'channels',
    'is_active',
  ],
  /** 光罩动作（P3 v0.8.2 §3.2 / §5）：ReticleUsageIn / ReticleReasonIn / ReticleCommentIn */
  reticleUsage: ['delta', 'reason_id', 'note'],
  reticleReason: ['reason'],
  reticleComment: ['comment'],
  /** UnmountIn / InspectionIn（be/p3 335db8a reticle/router.py） */
  reticleUnmount: ['unmounted_at', 'comment'],
  reticleInspection: [
    'kind',
    'result',
    'defect_count',
    'measured',
    'equipment_id',
    'inspected_at',
    'disposition',
    'comment',
  ],
} as const

/** StageIn（含 dc / scrap / rework_units 子项）。 */
export function stageBody(b: object): Obj {
  const o = pickBody(b, BODY_KEYS.stage) as Obj
  if (o.dc) o.dc = pickList(o.dc, BODY_KEYS.dc)
  if (o.scrap) o.scrap = pickList(o.scrap, BODY_KEYS.scrap)
  if (o.rework_units)
    o.rework_units = pickList(o.rework_units, BODY_KEYS.reworkUnit)
  return o
}

/** SplitIn（含子批）。 */
export function splitBody(b: object): Obj {
  const o = pickBody(b, BODY_KEYS.split) as Obj
  o.children = pickList(o.children, BODY_KEYS.splitChild)
  return o
}

/** SortIn（含槽位）。 */
export function sortBody(b: object): Obj {
  const o = pickBody(b, BODY_KEYS.sort) as Obj
  o.slots = pickList(o.slots, BODY_KEYS.sortSlot)
  return o
}

/** TransformIn（含 outputs / sources / manual_good）。 */
export function transformBody(b: object): Obj {
  const o = pickBody(b, BODY_KEYS.transform) as Obj
  if (Array.isArray(o.outputs))
    o.outputs = o.outputs.map((x: Obj) => {
      const y = pickBody(x, BODY_KEYS.transformOutput) as Obj
      y.sources = pickList(y.sources, BODY_KEYS.transformSource)
      return y
    })
  if (o.manual_good)
    o.manual_good = pickList(o.manual_good, BODY_KEYS.manualGood)
  return o
}

/** BinSplitIn（含 outputs / manual_bins / bins）。 */
export function binSplitBody(b: object): Obj {
  const o = pickBody(b, BODY_KEYS.binSplit) as Obj
  if (o.outputs) o.outputs = pickList(o.outputs, BODY_KEYS.binOutput)
  if (Array.isArray(o.manual_bins))
    o.manual_bins = o.manual_bins.map((x: Obj) => {
      const y = pickBody(x, BODY_KEYS.manualBins) as Obj
      y.bins = pickList(y.bins, BODY_KEYS.binQty)
      return y
    })
  return o
}
