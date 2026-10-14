import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n, { fmtDateTime, t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { mapApi, type MapListItem } from '@/lib/api/mes/map'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import { MapList } from './map-list'
import { emptyMapFilter, localDayStart, mapListParams } from './map-list-params'

const item = (v: number, latest: boolean): MapListItem => ({
  id: `M${v}`,
  substrate_id: 'WF001-01',
  substrate_type: 'wafer',
  map_version: v,
  is_latest: latest,
  rows: 6,
  cols: 6,
  total_qty: 36,
  good_qty: 24,
  excluded_qty: 4,
  bin_set_id: 'B1',
  bin_set_code: 'BINSET-DEMO',
  bin_set_version: 1,
  lot_id: 'L1',
  lot_code: 'LOT1',
  equipment_id: null,
  operation_id: null,
  map_import_id: 'I1',
  file_name: 'map_ok.csv',
  source: 'manual',
  imported_by: 'kai',
  imported_at: '2026-10-14T06:00:00Z',
  created_at: '2026-10-14T06:00:00Z',
})

function setup(perms: string[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  qc.setQueryDefaults(['mes', 'meta'], { staleTime: Infinity })
  qc.setQueryData(['mes', 'meta', 'auto'], {
    modules: [],
    entities: [],
    enums: {},
    perms,
  })
  return render(
    <QueryClientProvider client={qc}>
      <MapList />
    </QueryClientProvider>
  )
}

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})
afterEach(() => vi.restoreAllMocks())

describe('坐标图列表（P2-F8 / B5）', () => {
  it('参数：默认按导入时间倒序、每页 20；结束日含当天（次日 0 点，半开区间）', () => {
    expect(mapListParams(emptyMapFilter())).toEqual({
      page: 1,
      page_size: 20,
      sort_by: 'imported_at',
      sort_order: 'desc',
    })
    const p = mapListParams({
      ...emptyMapFilter(),
      q: ' map ',
      substrate: ' WF001-01 ',
      latestOnly: true,
      from: '2026-10-14',
      to: '2026-10-14',
    })
    expect(p).toMatchObject({
      q: 'map',
      substrate_id: 'WF001-01',
      latest_only: true,
      imported_from: '2026-10-14T00:00:00+08:00',
      imported_to: '2026-10-15T00:00:00+08:00',
    })
    expect(localDayStart('bad')).toBeUndefined()
    expect(localDayStart('2026-11-01', 1, 'America/Los_Angeles')).toBe(
      '2026-11-02T00:00:00-08:00'
    )
  })

  it('同一基板多版本都列出并标出最新；时间按本地显示；只看最新传 latest_only', async () => {
    const spy = vi
      .spyOn(mapApi, 'list')
      .mockResolvedValue({ data: [item(2, true), item(1, false)], count: 2 })
    const s = await setup([MES_PERM.mapRead])
    await expect
      .poll(() => document.querySelectorAll('[data-testid=map-row]').length)
      .toBe(2)
    const rows = document.querySelectorAll('[data-testid=map-row]')
    expect(rows[0].textContent).toContain('v2')
    expect(rows[0].textContent).toContain(t('mes.mapList.latest'))
    expect(rows[1].textContent).not.toContain(t('mes.mapList.latest'))
    expect(rows[0].textContent).toContain('BINSET-DEMO v1')
    expect(rows[0].textContent).toContain(fmtDateTime('2026-10-14T06:00:00Z'))
    await expect
      .element(s.getByTestId('map-count'))
      .toHaveTextContent('共 2 条 · 第 1/1 页')
    await userEvent.click(s.getByText(t('mes.mapList.latestOnly')))
    await expect.poll(() => spy.mock.lastCall?.[0].latest_only).toBe(true)
  })

  it('没有 mes.map:read 不请求，显示无权限', async () => {
    const spy = vi.spyOn(mapApi, 'list')
    const s = await setup([])
    await expect.element(s.getByText(t('mes.map.noPermission'))).toBeVisible()
    expect(spy).not.toHaveBeenCalled()
  })
})
