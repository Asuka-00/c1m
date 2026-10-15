import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { t } from '@/i18n'
import { beforeEach, describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { apiError } from '@/lib/api/mes/mock-utils'
import { mockReticleApi, resetReticleMock } from '@/lib/api/mes/reticle'
import { TooltipProvider } from '@/components/ui/tooltip'
import { PageEmbedContext } from '@/components/crud/page-embed'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import { ReticleLifeBar } from './life-bar'
import ReticlePage from './reticle-page'
import {
  actionEnabled,
  actionHint,
  inspectionPending,
  reticleErrorMessage,
  reticleLifeLevel,
} from './reticle-rules'

beforeEach(() => resetReticleMock())

describe('D87 life_state', () => {
  it('接口给了 life_state 以接口为准（GET / 列表 / brief 同字段）', () => {
    const low = { shot_count: '1', max_shots: '1000', warn_ratio: null }
    expect(reticleLifeLevel({ ...low, life_state: 'warning' })).toBe('warn')
    expect(reticleLifeLevel({ ...low, life_state: 'reached' })).toBe('over')
    const high = { shot_count: '999', max_shots: '1000', warn_ratio: null }
    expect(reticleLifeLevel({ ...high, life_state: 'ok' })).toBe('ok')
  })
  it('没有 life_state 时自算，warn_ratio 空按 0.9', () => {
    const r = (s: string) => ({
      shot_count: s,
      max_shots: '1000',
      warn_ratio: null,
    })
    expect(reticleLifeLevel(r('899'))).toBe('ok')
    expect(reticleLifeLevel(r('900'))).toBe('warn')
    expect(reticleLifeLevel(r('1000'))).toBe('over')
  })
  it('寿命条按接口 life_state 着色', async () => {
    const s = await render(
      <ReticleLifeBar
        reticle={{
          shot_count: '1',
          max_shots: '1000',
          warn_ratio: null,
          life_state: 'warning',
        }}
      />
    )
    await expect
      .element(s.getByTestId('reticle-life'))
      .toHaveAttribute('data-level', 'warn')
  })
})

describe('D87 待检验与检验流程', () => {
  it('待检验只看 status + inspection_required', () => {
    expect(
      inspectionPending({ status_code: 'on_hold', inspection_required: true })
    ).toBe(true)
    expect(
      inspectionPending({
        status_code: 'available',
        inspection_required: false,
      })
    ).toBe(false)
    expect(
      inspectionPending({ status_code: 'scrapped', inspection_required: true })
    ).toBe(false)
  })
  it('available 时出检验结果禁用并提示先开始检验', async () => {
    const r1 = await mockReticleApi.get('r1')
    expect(r1.status_code).toBe('available')
    expect(actionEnabled(r1, 'inspection')).toBe(false)
    expect(actionHint(r1, 'inspection')).toBe(
      t('mes.reticle.inspectStartFirst')
    )
    expect(actionHint(r1, 'mount')).toBeUndefined()
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    qc.setQueryData(['mes', 'meta', 'auto'], {
      modules: [],
      entities: [],
      enums: {},
      perms: [MES_PERM.reticleWrite],
    })
    const s = await render(
      <QueryClientProvider client={qc}>
        <TooltipProvider>
          <PageEmbedContext value={true}>
            <ReticlePage />
          </PageEmbedContext>
        </TooltipProvider>
      </QueryClientProvider>
    )
    await s.getByTestId('reticle-row-RTC-M1-001').click()
    const btn = s.getByTestId('reticle-act-inspection')
    await expect.element(btn).toBeDisabled()
    await expect
      .element(btn)
      .toHaveAttribute('title', t('mes.reticle.inspectStartFirst'))
  })
  it('409 invalid_transition（available 出结果）兜底提示', () => {
    const e = apiError(409, {
      code: 'invalid_transition',
      message: 'inspection pass not allowed from available',
      status_code: 'available',
      hold_reason: null,
    })
    expect(reticleErrorMessage(e, 'inspection')).toBe(
      t('mes.reticle.inspectStartFirst')
    )
    // 其他状态 / 动作仍是通用 invalid_transition 文案
    const e2 = apiError(409, {
      code: 'invalid_transition',
      message: 'x',
      status_code: 'dirty',
    })
    expect(reticleErrorMessage(e2, 'inspection')).toBe(
      t('mes.reticle.code.invalid_transition', {
        action: t('mes.reticle.action.inspection'),
      })
    )
  })
})
