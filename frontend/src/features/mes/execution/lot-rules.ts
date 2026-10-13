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

/** 能否 Hold：非终态（decisions #4），已 Hold 可再加一条。 */
export const canHold = (lot: LotLike) => !isTerminal(lot)

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
