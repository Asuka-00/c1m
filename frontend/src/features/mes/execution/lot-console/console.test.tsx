import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router'
import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import { Console } from './console'
import { execCtx, makeQc, Providers } from './test-utils'

const ALL = Object.values(MES_PERM)

async function show(status: string, onHold: boolean, perms: string[] = ALL) {
  const router = createRouter({
    routeTree: createRootRoute({
      component: () => <Console cx={execCtx(status, onHold)} />,
    }),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  return render(
    <Providers qc={makeQc(perms)}>
      <RouterProvider router={router} />
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
    await expect.element(s.getByTestId('to-bank')).toBeVisible()
    expect(s.container.querySelector('[data-testid=action-panel]')).toBeNull()
    expect(s.container.querySelector('[data-testid=run-stage]')).toBeNull()
  })

  it('完工批次按权限给出 Bank 入库 / 成品入库入口，Bank 带上批次', async () => {
    const s = await show('completed', false, [...ALL, 'mes.wh:write'])
    await expect
      .element(s.getByTestId('to-bank'))
      .toHaveAttribute('href', expect.stringContaining('lot=L1'))
    await expect.element(s.getByTestId('to-receipt')).toBeVisible()
    await s.unmount()

    const bankOnly = await show('completed', false)
    await expect.element(bankOnly.getByTestId('to-bank')).toBeVisible()
    expect(
      bankOnly.container.querySelector('[data-testid=to-receipt]')
    ).toBeNull()
    await bankOnly.unmount()

    const held = await show('completed', true, [...ALL, 'mes.wh:write'])
    await expect.element(held.getByText('LOT1').first()).toBeVisible()
    expect(held.container.querySelector('[data-testid=to-bank]')).toBeNull()
  })

  it('Track Out 面板含量测与报废录入', async () => {
    const s = await show('running', false)
    await expect.element(s.getByTestId('dc-entry')).toBeVisible()
    await expect.element(s.getByTestId('scrap-entry')).toBeVisible()
  })
})
