import { AxiosError, AxiosHeaders } from 'axios'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fmtDateTime, t } from '@/i18n'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { mapApi, mapApiError, type MapPreview } from '@/lib/api/mes/map'
import { PageEmbedContext } from '@/components/crud/page-embed'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import okCsv from './__fixtures__/map_ok.csv?raw'
import { mapErrorMessage } from './map-errors'
import MapImport from './map-import'

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
      <PageEmbedContext.Provider value={true}>
        <MapImport />
      </PageEmbedContext.Provider>
    </QueryClientProvider>
  )
}

const csv = (text: string, name: string) =>
  new File([text], name, { type: 'text/csv' })

function axiosErr(status: number, detail: unknown) {
  const e = new AxiosError('err')
  e.response = {
    status,
    data: { detail },
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
  }
  return e
}

// 以下样例取自 fe-demo-examples.md（8011 实采）
const header = {
  substrate_type: 'wafer',
  origin_location: 'UL',
  x_axis: 'right',
  y_axis: 'down',
  bin_definition_set: 'FED-BINSET',
  bin_definition_version: '1',
  rows: '2',
  cols: '3',
}
const badPreview: MapPreview = {
  ok: false,
  header,
  bin_set_id: '2386a8dc-b4ce-4e5c-94d9-bf486ad28ec3',
  substrates: [],
  errors: [
    {
      row_no: 6,
      file_line: 16,
      field: 'bin_code',
      code: 'unknown_bin',
      message: 'bin_code Z not defined in the bin set',
    },
  ],
}
const okPreview: MapPreview = {
  ok: true,
  header,
  bin_set_id: '2386a8dc-b4ce-4e5c-94d9-bf486ad28ec3',
  substrates: [
    {
      code: 'FED-EX-1014135855',
      rows: 2,
      cols: 3,
      total_qty: 6,
      bin_counts: { '1': 3, '2': 1, E: 1, U: 1 },
      good_qty: 3,
      excluded_qty: 2,
      map_version: 1,
    },
  ],
  errors: [],
}
const created = {
  id: '391f6744-ea2e-4e22-a20d-1ad1034cc466',
  code: 'FED-EX-1014135855',
  substrate_type: 'wafer',
  map_version: 1,
  rows: 2,
  cols: 3,
  origin_location: 'UL',
  x_axis: 'right',
  y_axis: 'down',
  total_qty: 6,
  good_qty: 3,
  excluded_qty: 2,
  bin_counts: { '1': 3, '2': 1, E: 1, U: 1 },
  lot_id: null,
  lot_label: null,
  operation_label: null,
  equipment_label: null,
  bin_set_label: 'FED-BINSET',
  created_at: '2026-10-14T05:58:55.215341Z',
}

afterEach(() => vi.restoreAllMocks())

describe('坐标图导入页（真实接口）', () => {
  it('坏文件：逐行列出问题，显示数据行号、悬停原始行号，不能确认', async () => {
    const preview = vi.spyOn(mapApi, 'preview').mockResolvedValue(badPreview)
    const screen = await setup([MES_PERM.mapImport])
    await userEvent.upload(
      screen.getByLabelText(t('mes.map.chooseFile')),
      csv(okCsv, 'bad.csv')
    )
    const cell = screen.getByRole('cell', { name: '6', exact: true })
    await expect.element(cell).toBeVisible()
    expect(cell.element().getAttribute('title')).toBe(
      t('mes.map.fileLine', { n: 16 })
    )
    await expect
      .element(screen.getByText(t('mes.map.errors.unknown_bin')))
      .toBeVisible()
    await expect
      .element(screen.getByRole('button', { name: t('mes.map.confirm') }))
      .toBeDisabled()
    expect(preview.mock.calls[0][0]).toEqual({
      content: okCsv,
      file_name: 'bad.csv',
    })
  })

  it('好文件：预览汇总后确认导入，显示新版本，导入时间按本地时区', async () => {
    vi.spyOn(mapApi, 'preview').mockResolvedValue(okPreview)
    const commit = vi
      .spyOn(mapApi, 'commit')
      .mockResolvedValue({ import_id: 'imp', data: [created] })
    const screen = await setup([MES_PERM.mapImport])
    await userEvent.upload(
      screen.getByLabelText(t('mes.map.chooseFile')),
      csv(okCsv, 'map_ok.csv')
    )
    const confirm = screen.getByRole('button', { name: t('mes.map.confirm') })
    await expect.element(confirm).toBeEnabled()
    await confirm.click()
    await expect.element(screen.getByText(t('mes.map.listTitle'))).toBeVisible()
    expect(Object.keys(commit.mock.calls[0][0]).sort()).toEqual([
      'content',
      'file_name',
    ])
    await expect
      .element(
        screen.getByRole('cell', { name: fmtDateTime(created.created_at) })
      )
      .toBeVisible()
  })

  it('正式导入 422 map_invalid：列出逐行错误', async () => {
    vi.spyOn(mapApi, 'preview').mockResolvedValue(okPreview)
    vi.spyOn(mapApi, 'commit').mockRejectedValue(
      axiosErr(422, {
        code: 'map_invalid',
        message: 'map file has errors',
        errors: badPreview.errors,
      })
    )
    const screen = await setup([MES_PERM.mapImport])
    await userEvent.upload(
      screen.getByLabelText(t('mes.map.chooseFile')),
      csv(okCsv, 'map_ok.csv')
    )
    await screen.getByRole('button', { name: t('mes.map.confirm') }).click()
    await expect
      .element(screen.getByText(t('mes.map.errors.unknown_bin')))
      .toBeVisible()
  })

  it('错误归类：409 / 413 / 403 / 字段级 422', () => {
    expect(
      mapErrorMessage(
        mapApiError(axiosErr(409, { code: 'map_version_conflict' }))
      )
    ).toBe(t('mes.map.conflict'))
    expect(
      mapErrorMessage(mapApiError(axiosErr(413, { code: 'payload_too_large' })))
    ).toBe(t('mes.map.tooLarge'))
    expect(mapErrorMessage(mapApiError(axiosErr(403, 'forbidden')))).toBe(
      t('mes.map.forbidden')
    )
    expect(
      mapErrorMessage(
        mapApiError(
          axiosErr(422, [
            { loc: ['body', 'lot_id'], msg: 'lot not found', type: 'v' },
          ])
        )
      )
    ).toBe('lot_id: lot not found')
  })

  it('没有 mes.map:import 权限时不能选择文件', async () => {
    const screen = await setup([])
    const btn = screen
      .getByRole('button', { name: t('mes.map.chooseFile') })
      .elements()
      .find((e) => e.tagName === 'BUTTON') as HTMLButtonElement
    await vi.waitFor(() => expect(btn.disabled).toBe(true))
  })
})
