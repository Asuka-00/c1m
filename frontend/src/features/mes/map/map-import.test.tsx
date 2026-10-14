import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { t } from '@/i18n'
import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { PageEmbedContext } from '@/components/crud/page-embed'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import unknownCsv from './__fixtures__/map_bad_unknown_bin.csv?raw'
import okCsv from './__fixtures__/map_ok.csv?raw'
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

describe('坐标图导入页（mock）', () => {
  it('坏文件：逐行列出问题，显示数据行号、悬停原始行号，不能确认', async () => {
    const screen = await setup([MES_PERM.mapImport])
    await userEvent.upload(
      screen.getByLabelText(t('mes.map.chooseFile')),
      csv(unknownCsv, 'bad.csv')
    )
    const cell = screen.getByRole('cell', { name: '15', exact: true })
    await expect.element(cell).toBeVisible()
    expect(cell.element().getAttribute('title')).toBe(
      t('mes.map.fileLine', { n: 23 })
    )
    await expect
      .element(
        screen.getByText(t('mes.map.errors.unknown_bin', { value: '9' }))
      )
      .toBeVisible()
    await expect
      .element(screen.getByRole('button', { name: t('mes.map.confirm') }))
      .toBeDisabled()
  })

  it('好文件：预览汇总后确认导入，列表出现两片基板的 v1', async () => {
    const screen = await setup([MES_PERM.mapImport])
    await userEvent.upload(
      screen.getByLabelText(t('mes.map.chooseFile')),
      csv(okCsv, 'map_ok.csv')
    )
    const confirm = screen.getByRole('button', { name: t('mes.map.confirm') })
    await expect.element(confirm).toBeEnabled()
    await confirm.click()
    await expect
      .element(screen.getByRole('cell', { name: 'map_ok.csv' }).first())
      .toBeVisible()
    expect(
      screen.getByRole('cell', { name: 'v1', exact: true }).elements().length
    ).toBeGreaterThanOrEqual(2)
  })

  it('没有 mes.map:import 权限时不能选择文件', async () => {
    const screen = await setup([])
    await expect.element(screen.getByText(t('mes.map.empty'))).toBeVisible()
    const btn = screen
      .getByRole('button', { name: t('mes.map.chooseFile') })
      .elements()
      .find((e) => e.tagName === 'BUTTON') as HTMLButtonElement
    expect(btn.disabled).toBe(true)
  })
})
