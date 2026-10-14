import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import { Console } from './console'
import { execCtx, makeQc, Providers } from './test-utils'

const ALL = Object.values(MES_PERM)

async function show(status: string, onHold: boolean, perms = ALL) {
  return render(
    <Providers qc={makeQc(perms)}>
      <Console cx={execCtx(status, onHold)} />
    </Providers>
  )
}

describe('Console / ActionPanel：执行按钮 = 权限 + canRunStage', () => {
  it('Hold 中的 running 批次可以 Track Out（D2）', async () => {
    const s = await show('running', true)
    await expect.element(s.getByTestId('run-stage')).toBeEnabled()
    await expect.element(s.getByTestId('action-panel')).toBeVisible()
  })

  it('Hold 中的 tracked_out 批次不能 Move Out', async () => {
    const s = await show('tracked_out', true)
    await expect.element(s.getByTestId('run-stage')).toBeDisabled()
  })

  it('Hold 中的 waiting 批次不能 Move In', async () => {
    const s = await show('waiting', true)
    await expect.element(s.getByTestId('run-stage')).toBeDisabled()
  })

  it('没有 mes.exec:write 时禁用，预检仍可用', async () => {
    const s = await show('waiting', false, [])
    await expect.element(s.getByTestId('run-stage')).toBeDisabled()
    await expect.element(s.getByTestId('preview-stage')).toBeEnabled()
  })

  it('终态批次不显示作业面板', async () => {
    const s = await show('completed', false)
    expect(s.container.querySelector('[data-testid=action-panel]')).toBeNull()
    expect(s.container.querySelector('[data-testid=run-stage]')).toBeNull()
  })

  it('Track Out 面板含量测与报废录入', async () => {
    const s = await show('running', false)
    await expect.element(s.getByTestId('dc-entry')).toBeVisible()
    await expect.element(s.getByTestId('scrap-entry')).toBeVisible()
  })
})
