import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'
import { render } from 'vitest-browser-react'
import { userEvent } from 'vitest/browser'
import type { ExecContext } from '@/lib/api/mes/execution'
import { MES_PERM } from '@/features/mes/common/mes-perm'
import { SplitMergeCard } from './split-merge'

function makeQc() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, enabled: false } },
  })
  qc.setQueryData(['mes', 'meta', 'auto'], {
    modules: [],
    entities: [],
    enums: {},
    perms: Object.values(MES_PERM),
  })
  return qc
}
const qc = makeQc()
function W({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

const cx = {
  lot: {
    id: 'L1',
    code: 'LOT1',
    qty: 10,
    lot_status: 'waiting',
    on_hold: false,
  },
  next_stage: 'move_in',
  tracking_level: 'quantity',
  units: [],
  holds: [],
  reasons: {
    hold: [],
    release: [],
    scrap: [],
    rework: [],
    jump: [],
    bonus: [],
  },
  stack: [],
  exec_ctx: {},
  sm: {
    allowed: true,
    priority: null,
    rule: {
      code: 'R',
      allow_split: true,
      allow_merge: true,
      max_children: 9,
      min_qty: 1,
      child_id_mode: 'suffix',
      merge_same_wo: false,
      children: 0,
    },
    candidates: [],
    genealogy: [],
  },
} as unknown as ExecContext

describe('拆批对话框（P13）', () => {
  it('子批合计等于母批数量时禁止提交、不显示 0 剩余', async () => {
    const s = await render(
      <W>
        <SplitMergeCard cx={cx} />
      </W>
    )
    await s.getByTestId('open-split').click()
    const qty = () => document.querySelector<HTMLInputElement>('#split-qty-0')!
    await expect.poll(() => !!document.querySelector('#split-qty-0')).toBe(true)
    await userEvent.fill(qty(), '10')
    await expect.element(s.getByTestId('split-too-many')).toBeVisible()
    await expect.element(s.getByTestId('do-split')).toBeDisabled()
    await userEvent.fill(qty(), '4')
    await expect.element(s.getByTestId('do-split')).toBeEnabled()
    expect(document.body.textContent).toContain('6 / 10')
  })
})
