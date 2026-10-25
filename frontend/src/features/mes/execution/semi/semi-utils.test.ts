import { describe, expect, it } from 'vitest'
import { parseDieCsv, type SpcChart } from '@/lib/api/mes/semi'
import { binColor, convertBody, yRange } from './semi-utils'

describe('parseDieCsv', () => {
  it('按晶圆分组，跳过表头并报告错误行', () => {
    const r = parseDieCsv(
      'wafer,x,y,bin\nW1,0,0,1\nW1,1,0,X\nW2,0,0,1\nW2,a,0,1\n'
    )
    expect(r.maps).toEqual([
      {
        unit_code: 'W1',
        dies: [
          [0, 0, '1'],
          [1, 0, 'X'],
        ],
      },
      { unit_code: 'W2', dies: [[0, 0, '1']] },
    ])
    expect(r.bad).toEqual([5])
  })
})

describe('binColor', () => {
  const legend = [
    { bin: '1', name: null, color: null, is_good: true, count: 1 },
    { bin: '2', name: null, color: '#123456', is_good: false, count: 1 },
  ]
  it('配置色优先，否则良品绿、坏品红', () => {
    expect(binColor(legend, '1')).toBe('#10b981')
    expect(binColor(legend, '2')).toBe('#123456')
    expect(binColor(legend, '9')).toBe('#ef4444')
  })
})

describe('yRange', () => {
  it('覆盖点与控制限并留边', () => {
    const c = {
      limits: { usl: null, lsl: null, target: null, ucl: 13, cl: 10, lcl: 7 },
      points: [{ mean: 15 }],
    } as unknown as SpcChart
    expect(yRange(c)).toEqual([6.2, 15.8])
  })
})

describe('convertBody', () => {
  it('按方式设置比例与按图取片', () => {
    expect(convertBody('die', 'map', 5, ' ')).toEqual({
      to_kind: 'die',
      per_parent: 1,
      per_child: 1,
      use_map: true,
      comment: undefined,
    })
    expect(convertBody('strip', 'assemble', 4, 'x').per_child).toBe(4)
    expect(convertBody('unit', 'split', 3, '').per_parent).toBe(3)
  })
})
