import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import { execCtx, makeQc, Providers } from './lot-console/test-utils'
import { WipActionsCard } from './wip-actions'

async function openAdjust(status: string) {
  const s = await render(
    <Providers qc={makeQc(Object.values(MES_PERM))}>
      <WipActionsCard cx={execCtx(status)} />
    </Providers>
  )
  await s.getByTestId('open-adjust').click()
  await expect
    .poll(() => !!document.querySelector('[data-testid=do-adjust]'))
    .toBe(true)
  const qty = document.querySelector<HTMLInputElement>(
    '[role=dialog] input[inputmode=numeric], [role=dialog] input[type=number], [role=dialog] input#adjust-qty'
  )!
  return { s, qty }
}

describe('在制调整：running 批次不能报废到 0（S5 / decisions #3）', () => {
  it('running 批次报废数量 = 批次数量时提示并禁止提交', async () => {
    const { qty } = await openAdjust('running')
    await userEvent.fill(qty, '10')
    await expect
      .poll(() => !!document.querySelector('[data-testid=scrap-all-running]'))
      .toBe(true)
    expect(
      document.querySelector<HTMLButtonElement>('[data-testid=do-adjust]')!
        .disabled
    ).toBe(true)
    await userEvent.fill(qty, '3')
    await expect
      .poll(() => !!document.querySelector('[data-testid=scrap-all-running]'))
      .toBe(false)
  })

  it('waiting 批次报废到 0 不提示（由状态机允许）', async () => {
    const { qty } = await openAdjust('waiting')
    await userEvent.fill(qty, '10')
    expect(document.querySelector('[data-testid=scrap-all-running]')).toBeNull()
  })
})
