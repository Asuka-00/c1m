import { afterEach, describe, expect, it, vi } from 'vitest'
import { http } from '@/lib/api/client'
import { bomApi } from '@/lib/api/mes/bom'
import { fetchAllPages, MAX_PAGE_SIZE } from './request'

afterEach(() => vi.restoreAllMocks())

describe('fetchAllPages（FE-F3-1）', () => {
  it('page_size 不超过 100，按 count 拉全', async () => {
    const all = Array.from({ length: 230 }, (_, i) => i)
    const calls: [number, number][] = []
    const r = await fetchAllPages(async (page, size) => {
      calls.push([page, size])
      return { data: all.slice((page - 1) * size, page * size), count: 230 }
    })
    expect(r).toEqual(all)
    expect(calls).toEqual([
      [1, 100],
      [2, 100],
      [3, 100],
    ])
    expect(MAX_PAGE_SIZE).toBe(100)
  })

  it('空页即停止', async () => {
    const f = vi.fn().mockResolvedValue({ data: [], count: 999 })
    expect(await fetchAllPages(f)).toEqual([])
    expect(f).toHaveBeenCalledTimes(1)
  })

  it('BOM 单位换算：请求 page_size=100 并逐页拉全', async () => {
    const row = (i: number) => ({
      id: `c${i}`,
      from_uom_id: `u${i}`,
      to_uom_id: 'g',
      from_uom_label: null,
      to_uom_label: null,
      factor: '0.001',
    })
    const get = vi.spyOn(http, 'get').mockImplementation(async (_url, cfg) => {
      const p = (cfg?.params as { page: number }).page
      const n = p === 1 ? 100 : 5
      return {
        data: {
          data: Array.from({ length: n }, (_, i) => row(p * 1000 + i)),
          count: 105,
        },
      }
    })
    const r = await bomApi.conversions()
    expect(r).toHaveLength(105)
    expect(get.mock.calls.map((c) => c[1]?.params)).toEqual([
      { page: 1, page_size: 100 },
      { page: 2, page_size: 100 },
    ])
  })
})
