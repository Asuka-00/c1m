import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import { execCtx, makeQc, Providers } from '../lot-console/test-utils'
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

describe('在制调整边界：晶圆级 running 批次', () => {
  it('勾选全部未报废晶圆时提示并禁止提交，少选一片则不提示', async () => {
    const cx = execCtx('running', false, {
      tracking_level: 'wafer',
      units: [
        { id: 'U1', code: 'W1', status: 'processing' },
        { id: 'U2', code: 'W2', status: 'processing' },
        { id: 'U3', code: 'W3', status: 'scrapped' },
      ],
    } as never)
    const s = await render(
      <Providers qc={makeQc(Object.values(MES_PERM))}>
        <WipActionsCard cx={cx} />
      </Providers>
    )
    await s.getByTestId('open-adjust').click()
    const boxes = () =>
      Array.from(
        document.querySelectorAll<HTMLElement>('[role=dialog] [role=checkbox]')
      ).filter((b) => /^W\d$/.test(b.parentElement?.textContent ?? ''))
    await expect.poll(() => boxes().length).toBe(2)
    await userEvent.click(boxes()[0])
    expect(document.querySelector('[data-testid=scrap-all-running]')).toBeNull()
    await userEvent.click(boxes()[1])
    await expect
      .poll(() => !!document.querySelector('[data-testid=scrap-all-running]'))
      .toBe(true)
    expect(
      document.querySelector<HTMLButtonElement>('[data-testid=do-adjust]')!
        .disabled
    ).toBe(true)
  })
})
