import { AxiosError, AxiosHeaders } from 'axios'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import i18n, { fmtDateTime, t } from '@/i18n'
import { toast } from 'sonner'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { http } from '@/lib/api/client'
import { bomApi, type Bom, type BomLine } from '@/lib/api/mes/bom'
import { DETAIL_TABS } from '@/features/mes/registry'
import { bomError, parseLoc } from './bom-errors'
import { BomTab } from './bom-tab'

// RefLink 依赖路由上下文；这里只验证链接目标
vi.mock('@/features/mes/common/ref-link', () => ({
  RefLink: ({
    target,
    id,
    label,
  }: {
    target: string
    id: string
    label: string
  }) => (
    <a data-testid='ref-link' data-target={target} data-id={id}>
      {label}
    </a>
  ),
}))

// 样例取自 fe-demo-examples.md §3（8011 种子 FED-FG）
const PID = '184aeb65-5185-4ef6-a0d9-2fd2762e69cb'
const bom = (v: number, status: Bom['status'], id: string): Bom => ({
  id,
  product_id: PID,
  version: v,
  status,
  effective_at:
    status === 'active' || status === 'superseded'
      ? '2026-10-14T05:58:05.980237Z'
      : null,
  confirmed_by: null,
  confirmed_at: null,
  copied_from_id: null,
  copied_from_label: v > 1 ? '2 · FED-FG' : null,
  description: `v${v}`,
  created_at: '2026-10-14T05:58:05.810151Z',
  updated_at: '2026-10-14T05:58:05.980237Z',
})
const V1 = bom(1, 'superseded', 'b1')
const V2 = bom(2, 'active', 'b2')
const V3 = bom(3, 'void', 'b3')
const V4 = bom(4, 'draft', 'b4')
const KG = 'c128c4ba-6940-460e-a209-459e755efb8f'
const G = 'd97a83fe-8b11-474f-b34e-4a05d0f07a8e'
const line = (n: number, qty: number, uom: string, label: string): BomLine => ({
  id: `l${n}`,
  bom_id: 'b4',
  line_no: n,
  component_type: 'material',
  material_id: 'm1',
  material_label: 'FED-WIRE · 金线',
  component_product_id: null,
  component_product_label: null,
  qty,
  uom_id: uom,
  uom_label: label,
  per_basis: 'die',
  scrap_rate: 0.02,
  consume_mode: 'issue',
  remark: null,
})
const LINES = [
  line(10, 0.000125, KG, 'FED-KG · 千克'),
  line(20, 0.3, G, 'FED-G · 克'),
]

function mockApi(list: Bom[] = [V1, V2, V3, V4]) {
  vi.spyOn(bomApi, 'list').mockResolvedValue(list)
  vi.spyOn(bomApi, 'tree').mockImplementation(async (id) => ({
    bom: list.find((b) => b.id === id)!,
    level: 1,
    lines: LINES,
  }))
  vi.spyOn(bomApi, 'conversions').mockResolvedValue([
    {
      id: 'c1',
      from_uom_id: KG,
      to_uom_id: G,
      from_uom_label: 'FED-KG · 千克',
      to_uom_label: 'FED-G · 克',
      factor: 1000,
    },
    {
      id: 'c2',
      from_uom_id: 'L',
      to_uom_id: 'ML',
      from_uom_label: 'FED-L · 升',
      to_uom_label: 'FED-ML · 毫升',
      factor: 1000,
    },
  ])
}

function setup(perms: string[], canWrite = perms.includes('mes.bom:write')) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  qc.setQueryDefaults(['mes', 'meta'], { staleTime: Infinity })
  qc.setQueryData(['mes', 'meta', 'auto'], {
    modules: [],
    entities: [
      {
        code: 'bom',
        can_write: canWrite,
        can_read: true,
        fields: [],
        children: [],
      },
    ],
    enums: {},
    perms,
  })
  return render(
    <QueryClientProvider client={qc}>
      <BomTab row={{ id: PID, code: 'FED-FG' }} />
    </QueryClientProvider>
  )
}

const ALL = ['mes.bom:write', 'mes.bom:activate']
const tip = () =>
  [...document.querySelectorAll('[data-slot=tooltip-content]')]
    .map((x) => x.textContent)
    .join('|')

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

afterEach(async () => {
  vi.restoreAllMocks()
  await i18n.changeLanguage('zh-CN')
})

describe('F3 BOM 页签', () => {
  it('只挂在产品详情，物料详情没有（验收 1）', () => {
    expect(DETAIL_TABS.product?.map((x) => x.key)).toEqual(['bom'])
    expect(DETAIL_TABS.material).toBeUndefined()
  })

  it('四种状态都显示，时间按本地时区格式化（验收 2）', async () => {
    mockApi()
    const s = await setup(ALL)
    for (const [v, st] of [
      [1, 'superseded'],
      [2, 'active'],
      [3, 'void'],
      [4, 'draft'],
    ] as const)
      await expect
        .element(s.getByTestId(`bom-version-${v}`))
        .toHaveTextContent(t(`mes.bomTab.status.${st}`))
    await expect
      .element(s.getByTestId('bom-version-2'))
      .toHaveTextContent(fmtDateTime(V2.effective_at))
    await i18n.changeLanguage('zh-CN')
    expect(t('mes.bomTab.status.superseded')).toBe('已取代')
  })

  it('数量原样显示，不四舍五入（验收 3）', async () => {
    mockApi()
    const s = await setup(ALL)
    await expect
      .element(s.getByTestId('bom-line-10').getByTestId('bom-line-qty'))
      .toHaveTextContent('0.000125')
  })

  it('非草稿只读：编辑、生效置灰，聚焦显示原因（验收 4）', async () => {
    mockApi()
    const s = await setup(ALL)
    await s.getByRole('button', { name: 'v2' }).click()
    await expect
      .element(
        s.getByRole('button', { name: t('mes.bomTab.edit'), exact: true })
      )
      .toBeDisabled()
    await expect
      .element(
        s.getByRole('button', { name: t('mes.bomTab.activate'), exact: true })
      )
      .toBeDisabled()
    await expect
      .element(
        s.getByRole('button', { name: t('mes.bomTab.copy'), exact: true })
      )
      .toBeEnabled()
    const wrap = s.getByLabelText(new RegExp(`^${t('mes.bomTab.edit')}:`))
    ;(wrap.element() as HTMLElement).focus()
    await expect.poll(tip).toContain(
      t('mes.bomTab.reason.notDraft', {
        status: t('mes.bomTab.status.active'),
      })
    )
    // 已取代不能作废
    await s.getByRole('button', { name: 'v1' }).click()
    await expect
      .element(
        s.getByRole('button', { name: t('mes.bomTab.void'), exact: true })
      )
      .toBeDisabled()
  })

  it('生效 v4：请求体为空，刷新后 v2 变已取代（验收 5）', async () => {
    mockApi()
    const post = vi
      .spyOn(http, 'post')
      .mockResolvedValue({ data: { ...V4, status: 'active' } })
    const s = await setup(ALL)
    await expect
      .element(s.getByTestId('bom-version-4'))
      .toHaveAttribute('aria-selected', 'true')
    vi.mocked(bomApi.list).mockResolvedValue([
      V1,
      { ...V2, status: 'superseded' },
      V3,
      { ...V4, status: 'active' },
    ])
    await s
      .getByRole('button', { name: t('mes.bomTab.activate'), exact: true })
      .click()
    await s
      .getByRole('alertdialog')
      .getByRole('button', { name: t('mes.bomTab.activate') })
      .click()
    await expect.poll(() => post.mock.calls.length).toBe(1)
    expect(post.mock.calls[0]).toEqual(['/mes/bom/b4/activate'])
    await expect
      .element(s.getByTestId('bom-version-2'))
      .toHaveTextContent(t('mes.bomTab.status.superseded'))
  })

  it('作废、复制：请求体为空（验收 6）', async () => {
    mockApi()
    const post = vi
      .spyOn(http, 'post')
      .mockResolvedValue({ data: { ...V4, id: 'b5', version: 5 } })
    const s = await setup(ALL)
    await s
      .getByRole('button', { name: t('mes.bomTab.copy'), exact: true })
      .click()
    await expect.poll(() => post.mock.calls.length).toBe(1)
    expect(post.mock.calls[0]).toEqual(['/mes/bom/b4/copy'])
    await s.getByRole('button', { name: 'v4' }).click()
    await s
      .getByRole('button', { name: t('mes.bomTab.void'), exact: true })
      .click()
    await s
      .getByRole('alertdialog')
      .getByRole('button', { name: t('mes.bomTab.void') })
      .click()
    await expect.poll(() => post.mock.calls.length).toBe(2)
    expect(post.mock.calls[1]).toEqual(['/mes/bom/b4/void'])
  })

  it('编辑草稿：单位来自单位换算；422 按下标定位到字段（验收 3、7）', async () => {
    mockApi()
    vi.spyOn(bomApi, 'replaceLines').mockRejectedValue(
      axiosErr(422, [
        {
          loc: ['body', 'lines', 1, 'qty'],
          msg: 'qty: must be a whole number for a count unit',
          type: 'value_error',
        },
      ])
    )
    const s = await setup(ALL)
    await s
      .getByRole('button', { name: t('mes.bomTab.edit'), exact: true })
      .click()
    const uom = s.getByLabelText(t('mes.bomTab.col.uom')).first()
    const opts = [...(uom.element() as HTMLSelectElement).options].map(
      (o) => o.textContent
    )
    expect(opts).toEqual([
      t('mes.bomTab.pickUom'),
      'FED-G · 克',
      'FED-KG · 千克',
      'FED-L · 升',
      'FED-ML · 毫升',
    ])
    const qty1 = s
      .getByTestId('bom-edit-line-1')
      .getByLabelText(t('mes.bomTab.col.qty'))
    await qty1.fill('1.5')
    await s.getByRole('button', { name: t('common.save') }).click()
    await expect
      .element(s.getByTestId('bom-edit-line-1').getByTestId('bom-field-error'))
      .toHaveTextContent(t('mes.bomTab.err.wholeNumber'))
    expect(document.body.textContent).not.toContain('qty: must be')
    expect(vi.mocked(bomApi.replaceLines).mock.calls[0][1][1].qty).toBe('1.5')
    // 整单回滚：弹窗不关，输入保留
    await expect.element(qty1).toHaveValue('1.5')
  })

  it('没有权限：按钮全部置灰（验收 8）', async () => {
    mockApi()
    const s = await setup([])
    for (const k of ['create', 'edit', 'activate', 'void', 'copy'])
      await expect
        .element(
          s.getByRole('button', { name: t(`mes.bomTab.${k}`), exact: true })
        )
        .toBeDisabled()
    await userEvent.tab()
    await expect.poll(tip).toContain(t('mes.bomTab.reason.noPermission'))
  })

  it('英文 / 日文页签与状态名已翻译（验收 10）', async () => {
    await i18n.changeLanguage('en')
    expect(t('mes.bomTab.status.superseded')).toBe('Superseded')
    await i18n.changeLanguage('ja')
    expect(t('mes.bomTab.status.void')).toBe('無効')
  })
})

describe('F3 v1.1 半成品与替代料', () => {
  const prodLine: BomLine = {
    ...line(30, 1, 'EA', 'FED-EA · 颗'),
    id: 'l30',
    component_type: 'product',
    material_id: null,
    material_label: null,
    component_product_id: 'p-die',
    component_product_label: 'FED-DIE',
    child: {
      bom: bom(3, 'active', 'cb3'),
      level: 2,
      lines: [
        {
          ...line(10, 2, KG, 'FED-KG · 千克'),
          id: 'c10',
          material_label: 'FED-WAFER',
        },
      ],
    },
  }
  const subLine: BomLine = {
    ...LINES[0],
    substitutes: [
      {
        id: 's1',
        bom_line_id: 'l10',
        material_id: 'm2',
        material_label: 'FED-WIRE-CU',
        priority: 1,
      },
    ],
  }
  const mockTree = (lines: BomLine[]) =>
    vi.spyOn(bomApi, 'tree').mockImplementation(async (id) => ({
      bom: [V1, V2, V3, V4].find((b) => b.id === id)!,
      level: 1,
      lines,
    }))

  it('两级树：半成品行展开只读显示当前生效版本，带去该产品维护的入口（验收 11）', async () => {
    mockApi()
    mockTree([
      subLine,
      prodLine,
      { ...prodLine, id: 'l40', line_no: 40, child: { bom: null, lines: [] } },
    ])
    const s = await setup(ALL)
    await expect
      .element(s.getByTestId('bom-line-subs'))
      .toHaveTextContent('1. FED-WIRE-CU')
    await s
      .getByRole('button', {
        name: t('mes.bomTab.expand', { name: 'FED-DIE' }),
      })
      .first()
      .click()
    const child = s.getByTestId('bom-child-30')
    await expect
      .element(child)
      .toHaveTextContent(t('mes.bomTab.childActive', { version: 3 }))
    await expect.element(child).toHaveTextContent('FED-WAFER')
    const link = child.getByTestId('ref-link')
    expect(link.element().getAttribute('data-id')).toBe('p-die')
    expect(link.element().getAttribute('data-target')).toBe('product')
    // 第二级只读：没有再展开或编辑的按钮
    expect(child.element().querySelectorAll('button')).toHaveLength(0)
    await s
      .getByRole('button', {
        name: t('mes.bomTab.expand', { name: 'FED-DIE' }),
      })
      .click()
    await expect
      .element(s.getByTestId('bom-child-40'))
      .toHaveTextContent(t('mes.bomTab.childNone'))
  })

  it('草稿编辑：可切换组件类型；替代料增删改优先级（验收 11、12）', async () => {
    mockApi()
    mockTree([subLine])
    const put = vi.spyOn(bomApi, 'replaceLines').mockResolvedValue({} as never)
    const s = await setup(ALL)
    await s
      .getByRole('button', { name: t('mes.bomTab.edit'), exact: true })
      .click()
    const type = s.getByLabelText(t('mes.bomTab.col.componentType')).first()
    const opts = [...(type.element() as HTMLSelectElement).options].map(
      (o) => o.value
    )
    expect(opts).toEqual(['material', 'product'])
    const pri = s
      .getByTestId('bom-edit-sub-0-0')
      .getByLabelText(t('mes.bomTab.subPriority'))
    await pri.fill('3')
    await s.getByRole('button', { name: t('common.save') }).click()
    await expect.poll(() => put.mock.calls.length).toBe(1)
    expect(put.mock.calls[0][1][0].substitutes).toContainEqual({
      material_id: 'm2',
      priority: 3,
    })
  })

  it('编辑框 qty 超 6 位小数：输入框下提示、不提交（D49）', async () => {
    mockApi()
    const put = vi.spyOn(bomApi, 'replaceLines')
    const s = await setup(ALL)
    await s
      .getByRole('button', { name: t('mes.bomTab.edit'), exact: true })
      .click()
    const qty1 = s
      .getByTestId('bom-edit-line-1')
      .getByLabelText(t('mes.bomTab.col.qty'))
    await qty1.fill('1e-7')
    await s.getByRole('button', { name: t('common.save') }).click()
    await expect
      .element(s.getByTestId('bom-edit-line-1').getByTestId('bom-field-error'))
      .toHaveTextContent(t('mes.bomTab.err.tooManyDecimals', { n: 6 }))
    expect(put).not.toHaveBeenCalled()
  })

  it('整单 422 bom_cycle：标在对应行的半成品输入框下', async () => {
    mockApi()
    mockTree([prodLine])
    vi.spyOn(bomApi, 'replaceLines').mockRejectedValue(
      axiosErr(422, [
        {
          loc: ['body', 'lines', 0, 'component_product_id'],
          msg: 'component_product: circular reference',
          type: 'bom_cycle',
          code: 'bom_cycle',
        },
      ])
    )
    const s = await setup(ALL)
    await s
      .getByRole('button', { name: t('mes.bomTab.edit'), exact: true })
      .click()
    await s.getByRole('button', { name: t('common.save') }).click()
    await expect
      .element(s.getByTestId('bom-edit-line-0').getByTestId('bom-field-error'))
      .toHaveTextContent(t('mes.bomTab.err.bomCycleField'))
  })

  it('生效 409 bom_depth_exceeded：提示里列出导致问题的产品和版本（D47）', async () => {
    mockApi()
    const err = vi.spyOn(toast, 'error')
    vi.spyOn(http, 'post').mockRejectedValue(
      axiosErr(409, {
        code: 'bom_depth_exceeded',
        message: 'x',
        details: [
          {
            product_id: 'pa',
            product: 'FG-A',
            product_version: 2,
            bom_id: 'ba',
            bom_version: 3,
          },
        ],
      })
    )
    const s = await setup(ALL)
    await s
      .getByRole('button', { name: t('mes.bomTab.activate'), exact: true })
      .click()
    await s
      .getByRole('alertdialog')
      .getByRole('button', { name: t('mes.bomTab.activate') })
      .click()
    await expect.poll(() => err.mock.calls.length).toBe(1)
    expect(err.mock.calls[0][0]).toBe(
      t('mes.bomTab.err.bomDepth', {
        items: t('mes.bomTab.err.refItem', { product: 'FG-A v2', bom: 3 }),
      })
    )
  })

  it('半成品行没有替代料编辑区（验收 12）', async () => {
    mockApi()
    mockTree([prodLine])
    const s = await setup(ALL)
    await s
      .getByRole('button', { name: t('mes.bomTab.edit'), exact: true })
      .click()
    await expect.element(s.getByTestId('bom-edit-line-0')).toBeInTheDocument()
    expect(document.querySelector('[data-testid=bom-edit-subs-0]')).toBeNull()
  })
})

describe('bomError', () => {
  it('替代料 422 路径与 409 重复', () => {
    expect(
      parseLoc(['body', 'lines', 2, 'substitutes', 1, 'priority'])
    ).toEqual({
      line: 2,
      field: 'sub.1.priority',
    })
    const e = bomError(axiosErr(409, { code: 'duplicate', field: 'priority' }))
    expect(e.message).toBe(t('mes.bomTab.err.dupSubPriority'))
    expect(e.fields[0].field).toBe('priority')
  })

  it('422 路径从 0 开始定位明细（D38）', () => {
    expect(parseLoc(['body', 'lines', 0, 'qty'])).toEqual({
      line: 0,
      field: 'qty',
    })
    expect(parseLoc(['body', 'consume_mode'])).toEqual({
      line: null,
      field: 'consume_mode',
    })
    const r = bomError(
      axiosErr(422, [
        {
          loc: ['body', 'lines', 2, 'uom_id'],
          msg: 'uom_id: required',
          type: 'value_error',
        },
      ])
    )
    expect(r.fields).toEqual([
      { line: 2, field: 'uom_id', message: t('mes.bomTab.err.required') },
    ])
  })

  it('403 只提示无权限（D34）', () => {
    const r = bomError(axiosErr(403, 'Not enough permissions'))
    expect(r).toEqual({ message: t('mes.bomTab.noPermission'), fields: [] })
  })

  it('409 翻译成本地提示，不展示原始英文', () => {
    expect(
      bomError(axiosErr(409, 'BOM v1 is already superseded')).message
    ).toBe(t('mes.bomTab.err.superseded'))
    expect(
      bomError(
        axiosErr(
          409,
          'BOM v1 is active; only draft BOMs can be changed (copy it to a new version)'
        )
      ).message
    ).toBe(t('mes.bomTab.err.readOnly'))
    expect(bomError(axiosErr(409, 'something else')).message).toBe(
      t('mes.bomTab.err.conflict')
    )
  })

  it('结构校验：422 按 code 标在半成品字段，逐行路径也能解析', () => {
    expect(parseLoc(['body', 'component_product_id'])).toEqual({
      line: null,
      field: 'component_product_id',
    })
    const r = bomError(
      axiosErr(422, [
        {
          loc: ['body', 'lines', 3, 'component_product_id'],
          msg: 'component_product: its active BOM already contains semi-finished lines',
          type: 'bom_depth_exceeded',
          code: 'bom_depth_exceeded',
        },
      ])
    )
    expect(r.fields).toEqual([
      {
        line: 3,
        field: 'component_product_id',
        message: t('mes.bomTab.err.bomDepthField'),
      },
    ])
  })

  it('409 结构 / 引用校验按 details 列出产品和版本（D47、D48），中英日都有', async () => {
    const ref = (p: string, v: number, b: number) => ({
      product_id: p,
      product: p,
      product_version: v,
      bom_id: `b-${p}`,
      bom_version: b,
    })
    const two = [ref('FG-A', 1, 2), ref('FG-B', 3, 4)]
    for (const lng of ['zh-CN', 'en', 'ja']) {
      await i18n.changeLanguage(lng)
      for (const code of [
        'bom_cycle',
        'bom_depth_exceeded',
        'bom_component_no_active',
        'bom_referenced',
      ]) {
        const m = bomError(
          axiosErr(409, { code, message: 'x', details: two })
        ).message
        expect(m).toContain('FG-A v1')
        expect(m).toContain('FG-B v3')
        expect(m).not.toContain('mes.bomTab')
      }
    }
    await i18n.changeLanguage('zh-CN')
    expect(
      bomError(
        axiosErr(409, {
          code: 'bom_referenced',
          message: 'x',
          details: [ref('FG-A', 1, 2)],
        })
      ).message
    ).toBe(t('mes.bomTab.err.referenced', { items: 'FG-A v1（BOM v2）' }))
  })

  it('422 too_many_decimals 标在 qty / scrap_rate（D49）', () => {
    const r = bomError(
      axiosErr(422, [
        {
          loc: ['body', 'lines', 1, 'scrap_rate'],
          msg: 'scrap_rate: too many decimals',
          type: 'too_many_decimals',
          code: 'too_many_decimals',
        },
      ])
    )
    expect(r.fields).toEqual([
      {
        line: 1,
        field: 'scrap_rate',
        message: t('mes.bomTab.err.tooManyDecimals', { n: 4 }),
      },
    ])
    const q = bomError(
      axiosErr(422, [
        {
          loc: ['body', 'lines', 0, 'qty'],
          msg: 'x',
          type: 'too_many_decimals',
        },
      ])
    )
    expect(q.fields[0]).toMatchObject({
      line: 0,
      field: 'qty',
      message: t('mes.bomTab.err.tooManyDecimals', { n: 6 }),
    })
  })

  it('无明细生效 422 提示至少一行', () => {
    const r = bomError(
      axiosErr(422, [
        {
          loc: ['body', 'bom_line'],
          msg: 'bom_line: a BOM needs at least one line',
          type: 'value_error',
        },
      ])
    )
    expect(r.message).toBe(t('mes.bomTab.err.noLines'))
  })
})
