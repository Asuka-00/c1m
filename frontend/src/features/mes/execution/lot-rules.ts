/**
 * 批次操作按钮的前置条件（界面侧），与架构设计
 * `lot-state-machine.md` §4 合法转移表及 `decisions.md` 保持一致。
 * 只决定按钮是否可用；后端仍做最终校验。
 */

/** 终态：completed（待入库）、stored、scrapped、merged（decisions #6）。 */
export const TERMINAL_STATUSES = [
  'completed',
  'stored',
  'scrapped',
  'merged',
] as const

/** 可拆批 / 合批的状态（§4 split / merge）。 */
export const SPLIT_MERGE_STATUSES = ['waiting', 'moved_in'] as const

type LotLike = Record<string, unknown>

const status = (lot: LotLike) => String(lot.lot_status ?? '')
const held = (lot: LotLike) => !!lot.on_hold

export const isTerminal = (lot: LotLike) =>
  (TERMINAL_STATUSES as readonly string[]).includes(status(lot))

/**
 * 能否执行下一阶段（Move In / Track In / Track Out / Move Out）。
 * Hold 中只允许 Track Out（decisions #2：加工中被 Hold 可 Track Out，不可 Move Out）。
 */
export function canRunStage(lot: LotLike, stage: string | null | undefined) {
  if (!stage || isTerminal(lot)) return false
  return !held(lot) || stage === 'track_out'
}

/**
 * 不能 Hold 的状态（M2）：scrapped、merged。
 * completed / stored 允许 Hold（如入库前扣留）。
 */
export const NON_HOLDABLE_STATUSES = ['scrapped', 'merged'] as const

/** 能否 Hold（M2，替代 decisions #4）：除 scrapped / merged 外均可，已 Hold 可再加一条。 */
export const canHold = (lot: LotLike) =>
  !(NON_HOLDABLE_STATUSES as readonly string[]).includes(status(lot))

/** 能否 Release：任意状态（终态批次的历史 Hold 也允许解除）。 */
export const canRelease = () => true

/** 能否拆批：waiting / moved_in，Hold 中允许（子批继承 Hold）。 */
export const canSplitLot = (lot: LotLike) =>
  (SPLIT_MERGE_STATUSES as readonly string[]).includes(status(lot))

/** 能否合批：waiting / moved_in，且非 Hold。 */
export const canMergeLot = (lot: LotLike) => canSplitLot(lot) && !held(lot)

/** 能否跳站（返工跳站）：waiting 且非 Hold。 */
export const canJumpLot = (lot: LotLike) =>
  status(lot) === 'waiting' && !held(lot)

/**
 * 能否数量调整（报废 / 补数）：非终态，Hold 中允许。
 * 加工中（running）不能报废至 0（decisions #3），由后端按数量校验。
 */
export const canAdjustLot = (lot: LotLike) => !isTerminal(lot)

/** 能否调整优先级：非终态，Hold 中允许。 */
export const canChangePriority = (lot: LotLike) => !isTerminal(lot)

/** 拆批子批定义（数量模式用 qty，单元模式用 unit_ids）。 */
type SplitChildLike = { qty?: number; unit_ids?: string[] }

/**
 * 拆批对话框校验（P13）：每个子批至少 1，子批合计须小于母批数量（不能拆完）。
 *
 * @returns moved 子批合计；remain 母批剩余（不小于 0）；
 *   tooMany 合计 ≥ 母批数量；ready 可提交
 */
export function checkSplit(
  children: SplitChildLike[],
  lotQty: number,
  qtyMode: boolean
) {
  const size = (c: SplitChildLike) =>
    qtyMode ? c.qty || 0 : c.unit_ids?.length || 0
  const moved = children.reduce((a, c) => a + size(c), 0)
  const tooMany = moved >= lotQty
  const ready =
    children.length > 0 && children.every((c) => size(c) > 0) && !tooMany
  return { moved, remain: Math.max(lotQty - moved, 0), tooMany, ready }
}

/**
 * 能否换载具 / 分拣：非终态且不在 running（SM §4 change_carrier / sort）。
 * `lot_status` 为 undefined 表示后端未下发该字段（旧版接口），不在前端拦截、交由后端校验。
 */
export function canChangeCarrier(lotStatus: string | null | undefined) {
  if (lotStatus === undefined) return true
  if (lotStatus === null) return false
  return !isTerminal({ lot_status: lotStatus }) && lotStatus !== 'running'
}

/**
 * 报废到 0 是否被禁止：加工中（running）批次不能整批报废（decisions #3）。
 *
 * @param scrap 本次报废数量（数量级）或晶圆数（单元级）
 * @param total 批次当前数量或未报废的晶圆数
 */
export function blocksScrapToZero(lot: LotLike, scrap: number, total: number) {
  return status(lot) === 'running' && scrap > 0 && scrap >= total
}
