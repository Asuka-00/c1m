import { describe, expect, it } from 'vitest'
import { packSlots } from './sort-slots'

describe('packSlots', () => {
  it('按晶圆号从起始槽位连续编号', () => {
    const r = packSlots([
      { id: 'b', code: 'W02', from: 7, to: 7 },
      { id: 'a', code: 'W01', from: 9, to: 9 },
    ])
    expect(r.map((x) => [x.code, x.to])).toEqual([
      ['W01', 1],
      ['W02', 2],
    ])
    expect(packSlots(r, 5).map((x) => x.to)).toEqual([5, 6])
  })
})
