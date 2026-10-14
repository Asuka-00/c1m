import { AxiosError, AxiosHeaders } from 'axios'
import i18n, { t } from '@/i18n'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { execApi, type BinSplitPreview } from '@/lib/api/mes/execution'
import { mapApi, type SubstrateMapDetail } from '@/lib/api/mes/map'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import { BinSplitDialog } from './bin-split-dialog'
import {
  binDraftErrors,
  binSplitBody,
  binSplitErrorText,
  binSummary,
  emptyBinDraft,
  sortBins,
  type BinDraft,
} from './bin-split-plan'
import { execCtx, makeQc, Providers } from './lot-console/test-utils'
import type { TrfWafer } from './transform-plan'
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

const MAP = { total_qty: 36, good_qty: 24, excluded_qty: 4, map_version: 1 }
const WAFERS: TrfWafer[] = [
  { id: 'U1', code: 'WF001-01', map: MAP },
  { id: 'U2', code: 'WF009-01', map: null },
]

/** BIN-01：WF001-01 按 bin 1:24、2:4、3:4、E:4（E 排除），32 + 4 = 36。 */
const PREVIEW: BinSplitPreview = {
  inputs: [
    {
      lot: 'LOT1',
      wafer: 'WF001-01',
      wafer_id: 'U1',
      bin_source: 'map',
      substrate_map_id: 'M1',
      map_version: 1,
      bin_set: { code: 'BINSET-DEMO', version: 1 },
      total_qty: 36,
      excluded_qty: 4,
      bin_counts: { '1': 24, '2': 4, '3': 4, E: 4 },
      split_counts: { '1': 24, '2': 4, '3': 4 },
      children_qty: 32,
      conserved: true,
    },
  ],
  outputs: ['1', '2', '3'].map((b, i) => ({
    bin_code: b,
    bin_codes: [b],
    product_id: 'P1',
    route_id: null,
    qty: [24, 4, 4][i],
  })),
  warnings: [],
}

beforeEach(async () => {
  await i18n.changeLanguage('zh-CN')
})
afterEach(async () => {
  vi.restoreAllMocks()
  await i18n.changeLanguage('zh-CN')
})

describe('F7 按 bin 拆批：纯函数', () => {
  it('bin 分档汇总：排除 bin 标记，守恒通过；bin 码排序与后端一致', () => {
    const s = binSummary(PREVIEW)
    expect(s.bins.map((b) => [b.bin, b.total, b.excluded])).toEqual([
      ['1', 24, false],
      ['2', 4, false],
      ['3', 4, false],
      ['E', 4, true],
    ])
    expect(s.ok).toBe(true)
    expect(sortBins(['E', '10', '2', 'A'])).toEqual(['2', '10', 'A', 'E'])
    const bad = binSummary({
      ...PREVIEW,
      inputs: [{ ...PREVIEW.inputs[0], children_qty: 30, conserved: false }],
    })
    expect(bad.ok).toBe(false)
    expect(bad.wafers[0].diff).toBe(-2)
  })

  it('人工 bin：必须录入、bin 不重复、要原因码；请求体只带人工晶圆', () => {
    const d: BinDraft = {
      ...emptyBinDraft(),
      manual: {
        U2: [
          { bin: '1', qty: '40' },
          { bin: '1', qty: '5' },
        ],
      },
    }
    const errs = binDraftErrors(WAFERS, d)
    expect(errs).toContain(t('mes.bin.e.reason'))
    expect(errs).toContain(t('mes.bin.e.dup', { wafer: 'WF009-01', bin: '1' }))
    expect(binDraftErrors(WAFERS, emptyBinDraft())).toContain(
      t('mes.bin.e.need', { wafer: 'WF009-01' })
    )
    const ok: BinDraft = {
      ...d,
      manual: {
        U2: [
          { bin: '1', qty: '40' },
          { bin: '2', qty: '10' },
          { bin: '', qty: '' },
        ],
      },
      reason_id: 'RC1',
    }
    expect(binDraftErrors(WAFERS, ok)).toEqual([])
    expect(binSplitBody('L1', WAFERS, ok)).toEqual({
      input_lot_ids: ['L1'],
      manual_bins: [
        {
          wafer_id: 'U2',
          bins: [
            { bin_code: '1', qty: 40 },
            { bin_code: '2', qty: 10 },
          ],
        },
      ],
      reason_id: 'RC1',
    })
  })

  it('守恒 422 显示期望数、实际数和差额', () => {
    expect(
      binSplitErrorText(
        err(422, {
          code: 'map_qty_mismatch',
          children_qty: 30,
          excluded_qty: 4,
          total_qty: 36,
        })
      )
    ).toBe('数量不守恒：子批 30 + 排除 4 ≠ 坐标图总数 36（差额 -2）')
    expect(
      binSplitErrorText(
        err(422, {
          code: 'bin_split_qty_mismatch',
          wafer: 'WF009-01',
          bins_qty: 52,
          expected_qty: 50,
        })
      )
    ).toBe('WF009-01：bin 合计 52 ≠ 期望 50（差额 +2）')
    expect(
      binSplitErrorText(
        err(422, [
          {
            loc: ['body', 'manual_bins'],
            msg: 'WF009-01: no substrate map; enter bin quantities with a reason',
          },
        ])
      )
    ).toBe(`WF009-01: ${t('mes.bin.be.needManual')}`)
  })
})

const ctx = (withManual = false) =>
  execCtx('waiting', false, {
    tracking_level: 'wafer',
    units: [
      { id: 'U1', code: 'WF001-01', status: 'waiting', unit_kind: 'wafer' },
      ...(withManual
        ? [
            {
              id: 'U2',
              code: 'WF009-01',
              status: 'waiting',
              unit_kind: 'wafer',
            },
          ]
        : []),
    ],
  } as never)

async function open(withManual = false, initial: Partial<BinDraft> = {}) {
  vi.spyOn(mapApi, 'bySubstrate').mockImplementation(async (code) => {
    if (code === 'WF001-01') return MAP as unknown as SubstrateMapDetail
    throw err(404, 'not found')
  })
  const s = await render(
    <Providers qc={makeQc(Object.values(MES_PERM))}>
      <BinSplitDialog
        cx={ctx(withManual)}
        open
        onOpenChange={() => {}}
        initial={initial}
      />
    </Providers>
  )
  await expect.element(s.getByText('坐标图 v1（只读）')).toBeVisible()
  return s
}

const btn = (id: string) =>
  document.querySelector<HTMLButtonElement>(`[data-testid=${id}]`)!

describe('F7 按 bin 拆批对话框', () => {
  it('F7-01/02：预览显示各 bin 数量和守恒通过；提交后子批显示 bin_code', async () => {
    const pv = vi.spyOn(execApi, 'binSplitPreview').mockResolvedValue(PREVIEW)
    vi.spyOn(execApi, 'binSplit').mockResolvedValue({
      transform: { id: 'T1' },
      children: ['1', '2', '3'].map((b, i) => ({
        id: `C${b}`,
        code: `LOT1-B${b}`,
        bin_code: b,
        qty: [24, 4, 4][i],
      })),
      warnings: [],
    })
    const s = await open()
    expect(btn('bin-commit').disabled).toBe(true)
    await s.getByTestId('bin-preview').click()
    await expect.element(s.getByTestId('bin-summary')).toBeVisible()
    expect(pv.mock.calls[0][0]).toEqual({ input_lot_ids: ['L1'] })
    const rows = document.querySelectorAll('[data-testid=bin-row]')
    expect(rows.length).toBe(4)
    expect(rows[3].textContent).toContain(t('mes.bin.excluded'))
    await expect
      .element(s.getByTestId('bin-conserve'))
      .toHaveTextContent('通过WF001-01：子批 32 + 排除 4 / 总数 36')
    expect(document.querySelectorAll('[data-testid=bin-output]').length).toBe(3)
    expect(btn('bin-commit').disabled).toBe(false)
    await s.getByTestId('bin-commit').click()
    await expect.element(s.getByTestId('bin-done')).toBeVisible()
    expect(
      Array.from(
        document.querySelectorAll('[data-testid=bin-child-code]'),
        (x) => x.textContent
      )
    ).toEqual(['1', '2', '3'])
  })

  it('F7-03：守恒不通过时提交不可用并显示差额；预览 422 显示差额', async () => {
    vi.spyOn(execApi, 'binSplitPreview').mockResolvedValueOnce({
      ...PREVIEW,
      inputs: [{ ...PREVIEW.inputs[0], children_qty: 30, conserved: false }],
    })
    const s = await open()
    await s.getByTestId('bin-preview').click()
    await expect
      .element(s.getByTestId('bin-conserve'))
      .toHaveTextContent('不通过')
    await expect
      .element(s.getByTestId('bin-conserve'))
      .toHaveTextContent('差额 -2')
    expect(btn('bin-commit').disabled).toBe(true)
    vi.spyOn(execApi, 'binSplitPreview').mockRejectedValueOnce(
      err(422, {
        code: 'map_qty_mismatch',
        children_qty: 30,
        excluded_qty: 4,
        total_qty: 36,
      })
    )
    await s.getByTestId('bin-preview').click()
    await expect
      .element(s.getByTestId('bin-error'))
      .toHaveTextContent('差额 -2')
    expect(btn('bin-commit').disabled).toBe(true)
  })

  it('无坐标图晶圆要人工录入 bin 并选原因码才能预览', async () => {
    const s = await open(true)
    await expect
      .element(s.getByTestId('bin-local-errors'))
      .toHaveTextContent(t('mes.bin.e.need', { wafer: 'WF009-01' }))
    expect(btn('bin-preview').disabled).toBe(true)
    await s.getByText(t('mes.bin.addBin')).click()
    await userEvent.fill(
      s.getByLabelText(t('mes.bin.binOf', { wafer: 'WF009-01', n: 1 })),
      '1'
    )
    await userEvent.fill(
      s.getByLabelText(t('mes.bin.qtyOf', { wafer: 'WF009-01', n: 1 })),
      '50'
    )
    await expect
      .element(s.getByTestId('bin-local-errors'))
      .toHaveTextContent(t('mes.bin.e.reason'))
    expect(btn('bin-preview').disabled).toBe(true)
  })

  it('入口按钮与单位转换同权限：mes.exec:transform', async () => {
    const perms = Object.values(MES_PERM)
    const s = await render(
      <Providers qc={makeQc(perms)}>
        <WipActionsCard cx={ctx()} />
      </Providers>
    )
    await expect.element(s.getByTestId('open-bin-split')).toBeEnabled()
    const s2 = await render(
      <Providers qc={makeQc(perms.filter((p) => p !== MES_PERM.execTransform))}>
        <div data-testid='np'>
          <WipActionsCard cx={ctx()} />
        </div>
      </Providers>
    )
    await expect
      .element(s2.getByTestId('np').getByTestId('open-bin-split'))
      .toBeDisabled()
  })
})
