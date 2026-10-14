import { AxiosError, AxiosHeaders } from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  mockMarkingApi as api,
  resetMarkingMock,
  trackOutBlock,
} from '@/lib/api/mes/marking'
import { rangeInverted } from '@/components/crud/filter-defs'
import { mapListParams } from '@/features/mes/map/map-list-params'
import { codeItemText } from './client'

const ax = (detail: unknown) => {
  const e = new AxiosError('422')
  e.response = {
    status: 422,
    data: { detail },
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
  }
  return e
}
void ax

beforeEach(() => resetMarkingMock())
afterEach(async () => {
  await i18n.changeLanguage('zh-CN')
})

describe('D77 补充一：range_inverted', () => {
  it('from 晚于 to 才算倒置；相等不拦', () => {
    expect(rangeInverted('2026-10-15', '2026-10-14')).toBe(true)
    expect(rangeInverted('2026-10-14', '2026-10-14')).toBe(false)
    expect(rangeInverted('2026-10-13', '2026-10-14')).toBe(false)
    expect(rangeInverted('', '2026-10-14')).toBe(false)
    expect(rangeInverted('2026-10-15T00:00:00+08:00', '2026-10-14')).toBe(true)
  })
  it('坐标图列表：倒置时不发导入时间范围', () => {
    const base = { q: '', substrate: '', latestOnly: false, page: 1 }
    const p = mapListParams({ ...base, from: '2026-10-15', to: '2026-10-14' })
    expect(p).not.toHaveProperty('imported_from')
    expect(p).not.toHaveProperty('imported_to')
    const ok = mapListParams({ ...base, from: '2026-10-14', to: '2026-10-14' })
    expect(ok.imported_from).toMatch(/[+-]\d{2}:\d{2}$/)
    expect(ok.imported_to).toMatch(/[+-]\d{2}:\d{2}$/)
  })
  it.each(['zh-CN', 'en', 'ja'])(
    '%s：value_error + ctx.reason 兜底文案',
    async (l) => {
      await i18n.changeLanguage(l)
      for (const r of ['range_inverted', 'timezone_required'])
        expect(codeItemText({ type: 'value_error', ctx: { reason: r } })).toBe(
          t(`mes.err.code.${r}`)
        )
      expect(i18n.exists('errors.rangeInverted')).toBe(true)
    }
  )
  it('mock：marked_at from 晚于 to → 422 range_inverted；相等返回空', async () => {
    await expect(
      api.records({
        marked_at_from: '2026-10-15T00:00:00+08:00',
        marked_at_to: '2026-10-14T00:00:00+08:00',
      })
    ).rejects.toMatchObject({
      response: {
        status: 422,
        data: { detail: [{ ctx: { reason: 'range_inverted' } }] },
      },
    })
    expect(
      await api.records({
        marked_at_from: '2026-10-14T00:00:00+08:00',
        marked_at_to: '2026-10-14T00:00:00+08:00',
      })
    ).toEqual([])
  })
})

describe('D79 补充六：未首打主记录', () => {
  it('三个字段为 null；按 marked_at 筛选时排除；出站按未打标拦', async () => {
    const r = await api.create({ lot_id: 'lot1' }, 'c6')
    expect(r).toMatchObject({
      marked_at: null,
      last_printed_at: null,
      latest_inspection_status: null,
    })
    expect((await api.records({})).some((x) => x.id === r.id)).toBe(true)
    expect(
      (await api.records({ marked_at_from: '2000-01-01T00:00:00+08:00' })).some(
        (x) => x.id === r.id
      )
    ).toBe(false)
    expect(trackOutBlock([r])).toBe('not_marked')
    const p = await api.print(r.id, {}, 'p6')
    expect(p.latest_inspection_status).toBe('pending')
  })
})
