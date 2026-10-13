import { describe, expect, it } from 'vitest'
import {
  canAdjustLot,
  canChangePriority,
  canHold,
  canJumpLot,
  canMergeLot,
  canRunStage,
  canSplitLot,
} from './lot-rules'

const ALL = [
  'waiting',
  'moved_in',
  'running',
  'tracked_out',
  'completed',
  'stored',
  'scrapped',
  'merged',
]
const TERM = ['completed', 'stored', 'scrapped', 'merged']
const lot = (s: string, h = false) => ({ lot_status: s, on_hold: h })
const where = (f: (l: ReturnType<typeof lot>) => boolean, h = false) =>
  ALL.filter((s) => f(lot(s, h)))

describe('lot-rules（对齐 lot-state-machine §4 / decisions）', () => {
  it('Hold：非终态可 Hold（含已 Hold），终态不可', () => {
    expect(where(canHold)).toEqual(ALL.filter((s) => !TERM.includes(s)))
    expect(where(canHold, true)).toEqual(ALL.filter((s) => !TERM.includes(s)))
  })

  it('阶段作业：Hold 中只允许 Track Out，不允许 Move Out', () => {
    expect(canRunStage(lot('running', true), 'track_out')).toBe(true)
    expect(canRunStage(lot('tracked_out', true), 'move_out')).toBe(false)
    expect(canRunStage(lot('waiting', true), 'move_in')).toBe(false)
    expect(canRunStage(lot('moved_in', true), 'track_in')).toBe(false)
    expect(canRunStage(lot('waiting'), 'move_in')).toBe(true)
    expect(canRunStage(lot('completed'), null)).toBe(false)
  })

  it('拆批：waiting / moved_in，Hold 中也允许', () => {
    expect(where(canSplitLot)).toEqual(['waiting', 'moved_in'])
    expect(where(canSplitLot, true)).toEqual(['waiting', 'moved_in'])
  })

  it('合批：waiting / moved_in，且非 Hold', () => {
    expect(where(canMergeLot)).toEqual(['waiting', 'moved_in'])
    expect(where(canMergeLot, true)).toEqual([])
  })

  it('跳站：仅 waiting 且非 Hold', () => {
    expect(where(canJumpLot)).toEqual(['waiting'])
    expect(where(canJumpLot, true)).toEqual([])
  })

  it('数量调整 / 优先级：非终态，Hold 中允许', () => {
    const live = ALL.filter((s) => !TERM.includes(s))
    expect(where(canAdjustLot, true)).toEqual(live)
    expect(where(canChangePriority, true)).toEqual(live)
  })
})
