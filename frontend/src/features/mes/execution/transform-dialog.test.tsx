import { AxiosError, AxiosHeaders } from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { mesApi } from '@/lib/api/mes/common'
import { execApi, type TransformPreview } from '@/lib/api/mes/execution'
import { mapApi, type SubstrateMapDetail } from '@/lib/api/mes/map'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import { execCtx, makeQc, Providers } from './lot-console/test-utils'
import { TransformDialog } from './transform-dialog'
import {
  balance,
  draftErrors,
  emptyDraft,
  transformBody,
  transformErrorText,
  trfWarningText,
  type TrfDraft,
  type TrfWafer,
} from './transform-plan'
import { WipActionsCard } from './wip-actions'

function err(status: number, detail: unknown) {
  const e = new AxiosError(String(status))
  e.response = {
    status,
    data: { detail },
    statusText: '',
    headers: {},
    config: { headers: new AxiosHeaders() },
  }
  return e
}

const MAP = { total_qty: 36, good_qty: 30, excluded_qty: 4, map_version: 2 }
const WAFERS: TrfWafer[] = [
  { id: 'U1', code: 'W1', map: MAP },
  { id: 'U2', code: 'W2', map: null },
]
const out = {
  product_id: 'P1',
  product_label: 'DIE-A',
  route_id: 'R1',
  route_label: 'PKG',
  kind: 'die' as const,
  qty: '',
  alloc: {},
}
const draft = (p: Partial<TrfDraft> = {}): TrfDraft => ({
  ...emptyDraft(),
  outputs: [out],
  ...p,
})

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})
afterEach(async () => {
  vi.restoreAllMocks()
  await i18n.changeLanguage('zh-CN')
})

describe('F8 单位转换：纯函数', () => {
  it('单输出默认分配全部良品；人工良品带 manual_good 和原因码；无图未录入走 gross die', () => {
    const d = draft({
      manual: { U2: { good: '20', fail: '3' } },
      reason_id: 'RC1',
    })
    expect(transformBody('L1', WAFERS, d)).toEqual({
      transform_type: 'dicing',
      input_lot_ids: ['L1'],
      outputs: [
        {
          product_id: 'P1',
          route_id: 'R1',
          track_unit_kind: 'die',
          sources: [
            { wafer_id: 'U1', qty: 30 },
            { wafer_id: 'U2', qty: 20 },
          ],
        },
      ],
      manual_good: [{ wafer_id: 'U2', good_qty: 20, fail_qty: 3 }],
      reason_id: 'RC1',
    })
    expect(draftErrors(WAFERS, d)).toEqual([])
    // 不录人工良品：不发 manual_good，W2 的来源为空（后端用 gross die）
    const g = transformBody('L1', WAFERS, draft())
    expect(g.manual_good).toBeUndefined()
    expect(g.outputs[0].sources).toEqual([{ wafer_id: 'U1', qty: 30 }])
  })

  it('FE-F8-1 无坐标图留空：不拦“至少分配 1 颗”，有 gross die 时默认全分', () => {
    const only: TrfWafer[] = [{ id: 'U2', code: 'FX1074-W1', map: null }]
    // gross die 未知：本地不拦，交给后端预览判定
    expect(draftErrors(only, draft())).toEqual([])
    const g: TrfWafer[] = [{ ...only[0], gross: 25 }]
    expect(draftErrors(g, draft())).toEqual([])
    const b = transformBody('L1', g, draft())
    expect(b.manual_good).toBeUndefined()
    expect(b.outputs[0].sources).toEqual([{ wafer_id: 'U2', qty: 25 }])
    // 多输出都留空时 gross die 已知，仍提示未分配
    const two = draft({ outputs: [out, out] })
    expect(draftErrors(g, two)).toContain(t('mes.trf.e.noDie', { n: 1 }))
  })

  it('人工良品不带原因码、分配不守恒、条数缺失都在本地拦下', () => {
    const d = draft({
      manual: { U2: { good: '20', fail: '' } },
      outputs: [{ ...out, kind: 'strip', alloc: { U1: '25' } }],
    })
    const errs = draftErrors(WAFERS, d)
    expect(errs).toContain(t('mes.trf.e.reason'))
    expect(errs).toContain(t('mes.trf.e.strip', { n: 1 }))
    expect(errs).toContain(
      t('mes.trf.e.balance', { wafer: 'W1', allocated: 25, good: 30 })
    )
    expect(balance(WAFERS, d)[0].diff).toBe(-5)
  })

  it('守恒 422 写明期望数和实际数；字段 422 翻译；gross die 提示', () => {
    expect(
      transformErrorText(
        err(422, {
          code: 'map_qty_mismatch',
          children_qty: 30,
          excluded_qty: 4,
          total_qty: 36,
        })
      )
    ).toBe('数量不守恒：子批 30 + 排除 4 ≠ 坐标图总数 36')
    expect(
      transformErrorText(
        err(422, {
          code: 'transform_qty_mismatch',
          wafer: 'W2',
          allocated_qty: 18,
          good_qty: 20,
        })
      )
    ).toBe('W2：已分配 18 ≠ 良品数 20')
    expect(
      transformErrorText(
        err(422, [
          {
            loc: ['body', 'reason_id'],
            msg: 'reason required for manual good qty',
          },
          { loc: ['body', 'source'], msg: 'x', type: 'extra_forbidden' },
        ])
      )
    ).toBe(`${t('mes.trf.be.reason')}；${t('mes.trf.be.extra')}`)
    expect(trfWarningText({ code: 'no_map_gross_die', wafer: 'W2' })).toBe(
      'W2：没有坐标图，已按产品 gross die 计良品数'
    )
  })
})

const PREVIEW: TransformPreview = {
  inputs: [
    {
      lot: 'LOT1',
      wafer: 'W1',
      wafer_id: 'U1',
      good_source: 'map',
      total_qty: 36,
      good_qty: 30,
      fail_qty: 2,
      excluded_qty: 4,
      allocated_qty: 30,
      substrate_map_id: 'M1',
      map_version: 2,
    },
    {
      lot: 'LOT1',
      wafer: 'W2',
      wafer_id: 'U2',
      good_source: 'manual',
      total_qty: 20,
      good_qty: 20,
      fail_qty: 0,
      excluded_qty: 0,
      allocated_qty: 20,
      substrate_map_id: null,
      map_version: null,
    },
  ],
  outputs: [
    {
      product_id: 'P1',
      route_id: 'R1',
      track_unit_kind: 'die',
      qty: 50,
      die_qty: 50,
    },
  ],
  warnings: [],
}

const waferCtx = () =>
  execCtx('waiting', false, {
    tracking_level: 'wafer',
    units: [
      { id: 'U1', code: 'W1', status: 'waiting', unit_kind: 'wafer' },
      { id: 'U2', code: 'W2', status: 'waiting', unit_kind: 'wafer' },
    ],
  } as never)

function mockMaps() {
  vi.spyOn(mapApi, 'bySubstrate').mockImplementation(async (code) => {
    if (code === 'W1') return MAP as unknown as SubstrateMapDetail
    throw err(404, 'not found')
  })
}

async function open(initial: Partial<TrfDraft>) {
  mockMaps()
  const s = await render(
    <Providers qc={makeQc(Object.values(MES_PERM))}>
      <TransformDialog
        cx={waferCtx()}
        open
        onOpenChange={() => {}}
        initial={{ outputs: [out], ...initial }}
      />
    </Providers>
  )
  await expect.element(s.getByTestId('trf-map-good')).toHaveTextContent('30')
  return s
}

const btn = (id: string) =>
  document.querySelector<HTMLButtonElement>(`[data-testid=${id}]`)!

describe('F8 单位转换对话框', () => {
  it('有坐标图只读显示良品数；无图可人工录入，录入后不选原因码不能预览', async () => {
    const s = await open({})
    expect(document.querySelectorAll('[data-testid=trf-map-good]').length).toBe(
      1
    )
    expect(btn('trf-commit').disabled).toBe(true)
    await userEvent.fill(s.getByLabelText(`W2 ${t('mes.trf.good')}`), '20')
    await expect
      .element(s.getByTestId('trf-local-errors'))
      .toHaveTextContent(t('mes.trf.e.reason'))
    expect(btn('trf-preview').disabled).toBe(true)
  })

  it('预览成功才可提交；改动后预览失效；提交后列出子批', async () => {
    const pv = vi.spyOn(execApi, 'transformPreview').mockResolvedValue(PREVIEW)
    const cm = vi.spyOn(execApi, 'transform').mockResolvedValue({
      transform: { id: 'T1' },
      children: [{ id: 'C1', code: 'LOT1-T1', qty: 50 }],
      warnings: [],
    })
    const s = await open({ reason_id: 'RC1', reason_label: 'MAN' })
    await userEvent.fill(s.getByLabelText(`W2 ${t('mes.trf.good')}`), '20')
    expect(btn('trf-commit').disabled).toBe(true)
    await s.getByTestId('trf-preview').click()
    await expect.element(s.getByTestId('trf-preview-result')).toBeVisible()
    expect(pv.mock.calls[0][0].manual_good).toEqual([
      { wafer_id: 'U2', good_qty: 20, fail_qty: 0 },
    ])
    expect(pv.mock.calls[0][0].outputs[0].sources).toEqual([
      { wafer_id: 'U1', qty: 30 },
      { wafer_id: 'U2', qty: 20 },
    ])
    await expect
      .element(s.getByTestId('trf-preview-result').getByText('坐标图 v2'))
      .toBeVisible()
    expect(btn('trf-commit').disabled).toBe(false)
    // 改动输入 → 预览失效
    await userEvent.fill(s.getByLabelText(`W2 ${t('mes.trf.good')}`), '21')
    await expect.element(s.getByTestId('trf-stale')).toBeVisible()
    expect(btn('trf-commit').disabled).toBe(true)
    await userEvent.fill(s.getByLabelText(`W2 ${t('mes.trf.good')}`), '20')
    await expect.poll(() => btn('trf-commit').disabled).toBe(false)
    await s.getByTestId('trf-commit').click()
    await expect.element(s.getByTestId('trf-done')).toHaveTextContent('LOT1-T1')
    expect(cm).toHaveBeenCalledTimes(1)
  })

  it('无坐标图留空按产品 gross die 分配可预览；提交后先显示子批，关闭时才刷新', async () => {
    vi.spyOn(mesApi, 'get').mockResolvedValue({ id: 'P0', gross_die: 25 })
    const pv = vi.spyOn(execApi, 'transformPreview').mockResolvedValue(PREVIEW)
    vi.spyOn(execApi, 'transform').mockResolvedValue({
      transform: { id: 'T1' },
      children: [{ id: 'C1', code: 'LOT1-T1', qty: 55 }],
      warnings: [],
    })
    mockMaps()
    const qc = makeQc(Object.values(MES_PERM))
    const inv = vi.spyOn(qc, 'invalidateQueries')
    const onOpenChange = vi.fn()
    const cx = waferCtx()
    ;(cx.lot as Record<string, unknown>).product_id = 'P0'
    const s = await render(
      <Providers qc={qc}>
        <TransformDialog
          cx={cx}
          open
          onOpenChange={onOpenChange}
          initial={{ outputs: [out] }}
        />
      </Providers>
    )
    await expect.poll(() => btn('trf-preview')?.disabled).toBe(false)
    await s.getByTestId('trf-preview').click()
    await expect.element(s.getByTestId('trf-preview-result')).toBeVisible()
    expect(pv.mock.lastCall![0].manual_good).toBeUndefined()
    expect(pv.mock.lastCall![0].outputs[0].sources).toEqual([
      { wafer_id: 'U1', qty: 30 },
      { wafer_id: 'U2', qty: 25 },
    ])
    await s.getByTestId('trf-commit').click()
    await expect.element(s.getByTestId('trf-done')).toHaveTextContent('LOT1-T1')
    expect(inv).not.toHaveBeenCalled()
    expect(onOpenChange).not.toHaveBeenCalled()
    await s
      .getByRole('button', { name: t('common.close') })
      .first()
      .click()
    expect(inv).toHaveBeenCalledWith({ queryKey: ['mes'] })
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('预览 422 守恒错误在对话框内显示，不能提交', async () => {
    vi.spyOn(execApi, 'transformPreview').mockRejectedValue(
      err(422, {
        code: 'map_qty_mismatch',
        children_qty: 30,
        excluded_qty: 4,
        total_qty: 36,
      })
    )
    const s = await open({})
    await s.getByTestId('trf-preview').click()
    await expect
      .element(s.getByTestId('trf-error'))
      .toHaveTextContent('子批 30 + 排除 4 ≠ 坐标图总数 36')
    expect(btn('trf-commit').disabled).toBe(true)
  })

  it('入口按钮：需 mes.exec:transform，Hold 或非晶圆批不可用', async () => {
    const perms = Object.values(MES_PERM)
    const s = await render(
      <Providers qc={makeQc(perms)}>
        <WipActionsCard cx={waferCtx()} />
      </Providers>
    )
    await expect.element(s.getByTestId('open-transform')).toBeEnabled()
    const s2 = await render(
      <Providers qc={makeQc(perms.filter((p) => p !== MES_PERM.execTransform))}>
        <div data-testid='no-perm'>
          <WipActionsCard cx={waferCtx()} />
        </div>
      </Providers>
    )
    await expect
      .element(s2.getByTestId('no-perm').getByTestId('open-transform'))
      .toBeDisabled()
    const s3 = await render(
      <Providers qc={makeQc(perms)}>
        <div data-testid='qty'>
          <WipActionsCard cx={execCtx('waiting')} />
        </div>
      </Providers>
    )
    await expect
      .element(s3.getByTestId('qty').getByTestId('open-transform'))
      .toBeDisabled()
  })
})
