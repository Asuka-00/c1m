import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@/styles/index.css'
import { describe, expect, it, vi } from 'vitest'
import { render } from 'vitest-browser-react'
import { Input } from '@/components/ui/input'
import { RefSelect } from './ref-select'

vi.mock('@/lib/api/hooks', () => ({ useTenantKey: () => 't1' }))
vi.mock('@/lib/api/mes/common', () => ({
  mesApi: { list: vi.fn(async () => ({ data: [] })) },
}))

const LONG = 'DM261001-QA-LONG-LOT-CODE-0000000000001'

async function setup(value: string | null, onChange = vi.fn()) {
  const s = await render(
    <QueryClientProvider client={new QueryClient()}>
      <div
        style={{ display: 'grid', gridTemplateColumns: '202px 202px', gap: 12 }}
      >
        <div data-testid='cell-ref'>
          <RefSelect
            id='rs'
            target='lot'
            value={value}
            label={value ? LONG : null}
            onChange={onChange}
          />
        </div>
        <div>
          <Input data-testid='num' type='number' />
        </div>
      </div>
    </QueryClientProvider>
  )
  const cell = s.getByTestId('cell-ref').element() as HTMLElement
  const trigger = cell.querySelector('[role=combobox]') as HTMLButtonElement
  const clear = cell.querySelector(
    'button.absolute'
  ) as HTMLButtonElement | null
  return { s, cell, trigger, clear, onChange }
}

describe('RefSelect 宽度与清除按钮', () => {
  it('和同一网格里的数字框一样宽', async () => {
    const { s, trigger } = await setup('1')
    const num = s.getByTestId('num').element() as HTMLElement
    expect(Math.round(trigger.getBoundingClientRect().width)).toBe(
      Math.round(num.getBoundingClientRect().width)
    )
  })

  it('长值时文字在 × 左边结束，× 不压箭头', async () => {
    const { trigger, clear } = await setup('1')
    expect(clear).not.toBeNull()
    const span = trigger.querySelector('span')!
    // 文字实际结束位置 = span 右边缘减去右内边距（给 × 留的空白）
    const textEnd =
      span.getBoundingClientRect().right -
      parseFloat(getComputedStyle(span).paddingRight)
    const x = clear!.getBoundingClientRect()
    const arrow = trigger.querySelector('svg')!.getBoundingClientRect()
    expect(textEnd).toBeLessThanOrEqual(x.left + 0.5)
    expect(x.right).toBeLessThanOrEqual(arrow.left + 0.5)
  })

  it('点 × 清空并把焦点放回触发框', async () => {
    const { trigger, clear, onChange } = await setup('1')
    clear!.click()
    expect(onChange).toHaveBeenCalledWith(null, null)
    expect(document.activeElement).toBe(trigger)
  })

  it('没有值时不显示 ×，也不留空白', async () => {
    const { trigger, clear } = await setup(null)
    expect(clear).toBeNull()
    expect(trigger.querySelector('span')!.className).not.toContain('pe-6')
  })
})
