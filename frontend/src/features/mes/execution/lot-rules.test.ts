import { describe, expect, it } from 'vitest'
import {
  blocksScrapToZero,
  canAdjustLot,
  canChangeCarrier,
  canChangePriority,
  canHold,
  canJumpLot,
  canMergeLot,
  canRunStage,
  canSplitLot,
  checkSplit,
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
  it('Hold（M2）：completed / stored 可 Hold，scrapped / merged 不可', () => {
    const ok = ALL.filter((s) => !['scrapped', 'merged'].includes(s))
    expect(where(canHold)).toEqual(ok)
    expect(where(canHold, true)).toEqual(ok)
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

describe('checkSplit（P13：不能拆完）', () => {
  it('数量模式：合计须小于母批', () => {
    expect(checkSplit([{ qty: 3 }, { qty: 2 }], 10, true)).toEqual({
      moved: 5,
      remain: 5,
      tooMany: false,
      ready: true,
    })
    expect(checkSplit([{ qty: 10 }], 10, true)).toMatchObject({
      remain: 0,
      tooMany: true,
      ready: false,
    })
    expect(checkSplit([{ qty: 8 }, { qty: 5 }], 10, true).remain).toBe(0)
    expect(checkSplit([{ qty: 3 }, { qty: 0 }], 10, true).ready).toBe(false)
  })

  it('单元模式：按选中的晶圆数计', () => {
    expect(checkSplit([{ unit_ids: ['a', 'b'] }], 3, false).ready).toBe(true)
    expect(
      checkSplit([{ unit_ids: ['a', 'b'] }, { unit_ids: ['c'] }], 3, false)
    ).toMatchObject({ tooMany: true, ready: false, remain: 0 })
  })
})

describe('canChangeCarrier（换载具 / 分拣）', () => {
  it('非终态且不在 running；空载具与终态不可', () => {
    expect(ALL.filter((x) => canChangeCarrier(x))).toEqual([
      'waiting',
      'moved_in',
      'tracked_out',
    ])
    expect(canChangeCarrier(null)).toBe(false)
  })
  it('旧接口没有 lot_status 字段时不拦截', () => {
    expect(canChangeCarrier(undefined)).toBe(true)
  })
})

describe('blocksScrapToZero（decisions #3）', () => {
  it('仅 running 且报废后为 0 时禁止', () => {
    expect(blocksScrapToZero(lot('running'), 25, 25)).toBe(true)
    expect(blocksScrapToZero(lot('running'), 30, 25)).toBe(true)
    expect(blocksScrapToZero(lot('running'), 24, 25)).toBe(false)
    expect(blocksScrapToZero(lot('running'), 0, 0)).toBe(false)
    expect(blocksScrapToZero(lot('waiting'), 25, 25)).toBe(false)
    expect(blocksScrapToZero(lot('tracked_out', true), 25, 25)).toBe(false)
  })
})
