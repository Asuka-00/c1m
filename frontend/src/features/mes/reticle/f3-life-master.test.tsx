import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { t } from '@/i18n'
import { Toaster } from 'sonner'
import { beforeEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { mockReticleApi, resetReticleMock } from '@/lib/api/mes/reticle'
import { TooltipProvider } from '@/components/ui/tooltip'
import { PageEmbedContext } from '@/components/crud/page-embed'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import { ReticleLifeBar } from './life-bar'
import { init, masterBody, masterErrors } from './master-form'
import ReticlePage from './reticle-page'
import { reticleLifeLevel } from './reticle-rules'

const wrap = (perms: string[]) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  qc.setQueryData(['mes', 'meta', 'auto'], {
    modules: [],
    entities: [],
    enums: {},
    perms,
  })
  return (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <PageEmbedContext value={true}>
          <ReticlePage />
          <Toaster />
        </PageEmbedContext>
      </TooltipProvider>
    </QueryClientProvider>
  )
}
beforeEach(() => {
  resetReticleMock()
  // 上一个用例的 Radix 对话框卸载时可能留下 body pointer-events:none
  document.body.style.pointerEvents = ''
})

const R = (
  shot_count: string,
  max_shots: string | null,
  warn_ratio: string | null = null
) => ({
  shot_count,
  max_shots,
  warn_ratio,
})

describe('P3-F3 寿命等级（D54-5 / D76 定点）', () => {
  it('缺省预警比例 0.9；边界精确', () => {
    expect(reticleLifeLevel(R('89999', '100000'))).toBe('ok')
    expect(reticleLifeLevel(R('90000', '100000'))).toBe('warn')
    expect(reticleLifeLevel(R('99999.999999', '100000'))).toBe('warn')
    expect(reticleLifeLevel(R('100000', '100000'))).toBe('over')
    expect(reticleLifeLevel(R('100001', '100000'))).toBe('over')
    expect(reticleLifeLevel(R('5', null))).toBeNull()
  })
  it('warn_ratio 定点字符串；后端 life_state 优先', () => {
    expect(reticleLifeLevel(R('7999', '10000', '0.8000'))).toBe('ok')
    expect(reticleLifeLevel(R('8000', '10000', '0.8000'))).toBe('warn')
    expect(
      reticleLifeLevel({ ...R('1', '10000'), life_state: 'reached' })
    ).toBe('over')
  })
  it('寿命条：颜色等级与 tooltip（三语 key）', async () => {
    const s = await render(
      <>
        <ReticleLifeBar reticle={R('95000', '100000')} />
        <ReticleLifeBar reticle={R('100000', '100000')} />
        <ReticleLifeBar reticle={R('1', null)} />
      </>
    )
    const bars = s.getByTestId('reticle-life').elements()
    expect(bars.map((b) => b.getAttribute('data-level'))).toEqual([
      'warn',
      'over',
      'none',
    ])
    expect(bars[0].getAttribute('title')).toContain('90000')
    expect(bars[0].getAttribute('title')).toContain(
      t('mes.reticle.life.warnTip')
    )
    expect(bars[1].textContent).toContain(t('mes.reticle.life.over'))
    expect(bars[2].getAttribute('title')).toBe(t('mes.reticle.life.noLimitTip'))
  })
})

describe('P3-F3 主数据', () => {
  it('校验与请求体：定点字符串、编辑只发改动字段', async () => {
    const v = { ...init(null), code: '', max_shots: '1.5', warn_ratio: '1.2' }
    expect(Object.keys(masterErrors(v)).sort()).toEqual([
      'code',
      'max_shots',
      'warn_ratio',
    ])
    expect(
      masterBody(
        { ...init(null), code: 'X', max_shots: '0100000', warn_ratio: '0.90' },
        null
      )
    ).toEqual({
      code: 'X',
      max_shots: '100000',
      warn_ratio: '0.9',
      count_basis: 'track_out',
    })
    const r1 = await mockReticleApi.get('r1')
    expect(
      masterBody({ ...init(r1), max_shots: '100000.0', layer: 'M2' }, r1)
    ).toEqual({ layer: 'M2' })
  })
  it('页面新建：无写权限不显示按钮', async () => {
    const ro = await render(wrap([]))
    await expect.element(ro.getByTestId('reticle-row-RTC-M1-001')).toBeVisible()
    await expect
      .element(ro.getByTestId('reticle-create'))
      .not.toBeInTheDocument()
  })
  it('页面新建：保存后出现在列表', async () => {
    const s = await render(wrap([MES_PERM.reticleWrite]))
    await s.getByTestId('reticle-create').click()
    await s
      .getByLabelText(t('mes.reticle.master.field.code'))
      .fill('RTC-FE-NEW')
    await s.getByLabelText(t('mes.reticle.master.field.max_shots')).fill('1000')
    await s.getByTestId('reticle-master-save').click()
    await expect.element(s.getByTestId('reticle-row-RTC-FE-NEW')).toBeVisible()
    const row = s.getByTestId('reticle-row-RTC-FE-NEW')
    await expect
      .element(row.getByTestId('reticle-life'))
      .toHaveAttribute('data-level', 'ok')
  })
  it('页面编辑：改上限后寿命条变色', async () => {
    const s = await render(wrap([MES_PERM.reticleWrite]))
    await s.getByTestId('reticle-row-RTC-M1-002').click()
    await s.getByTestId('reticle-edit').click()
    const ms = s.getByLabelText(t('mes.reticle.master.field.max_shots'))
    await ms.fill('48000')
    await s.getByTestId('reticle-master-save').click()
    await expect
      .element(
        s.getByTestId('reticle-row-RTC-M1-002').getByTestId('reticle-life')
      )
      .toHaveAttribute('data-level', 'warn')
  })
})
